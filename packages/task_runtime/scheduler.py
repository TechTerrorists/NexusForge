"""Durable, observable execution of approved software task DAGs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm_runtime import get_tenant_llm_config
from app.models import (
    AgentInstance,
    AgentMessageRecord,
    ExecutionStatus,
    Repository,
    RoleTemplateVersion,
    RunArtifact,
    RunEvent,
    TaskPlan,
    TaskPlanStatus,
    TaskStep,
    WorkflowRun,
)
from packages.handoff.redis_streams import RedisMessageBus
from packages.task_runtime.git_process import git_capture
from packages.task_runtime.opencode import OpenCodeResult, OpenCodeRunner

logger = logging.getLogger(__name__)
_SECRET_KEYS = re.compile(
    r"(?:^|[_-])(?:api[-_]?key|authorization|password|secret|token)(?:$|[_-])",
    re.I,
)


class TaskScheduler:
    """Runs dependency-ready steps concurrently and keeps Postgres authoritative."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        message_bus: RedisMessageBus | None = None,
    ) -> None:
        self.sessions = sessions
        self.runner = OpenCodeRunner()
        self.message_bus = message_bus
        self._cancelled: set[str] = set()

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    async def emit(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        *,
        agent_instance_id: uuid.UUID | None = None,
        task_step_id: uuid.UUID | None = None,
        visibility: str = "user",
    ) -> None:
        # Several agents can report simultaneously. The transaction-scoped lock
        # makes the per-run sequence collision-free without making Redis stateful.
        if db.bind and db.bind.dialect.name == "postgresql":
            await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(run_id)})
        sequence = (await db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)) or 0) + 1
        run = await db.get(WorkflowRun, run_id)
        db.add(
            RunEvent(
                run_id=run_id,
                trace_id=run.trace_id if run else "",
                sequence=sequence,
                event_type=event_type,
                actor=actor,
                payload=_redact(payload),
                agent_instance_id=agent_instance_id,
                task_step_id=task_step_id,
                visibility=visibility,
            )
        )
        await db.flush()

    async def message(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        sender: str,
        recipient: str,
        message_type: str,
        payload: dict[str, Any],
        artifact_refs: list[str] | None = None,
    ) -> None:
        db.add(
            AgentMessageRecord(
                run_id=run_id,
                sender=sender,
                recipient=recipient,
                message_type=message_type,
                payload=_redact(payload),
                artifact_refs=artifact_refs or [],
            )
        )
        await self.emit(db, run_id, "agent_message", sender, {"recipient": recipient, "message_type": message_type, **payload})

    async def execute(self, plan_id: str, run_id: str) -> None:
        run_uuid, plan_uuid = uuid.UUID(run_id), uuid.UUID(plan_id)
        try:
            async with self.sessions() as db:
                plan = await db.get(TaskPlan, plan_uuid)
                run = await db.get(WorkflowRun, run_uuid)
                if not plan or not run or plan.status != TaskPlanStatus.APPROVED:
                    raise RuntimeError("Approved plan and run are required")
                repository = await db.get(Repository, plan.repository_id)
                if not repository:
                    raise RuntimeError("Repository is unavailable")
                run.status = ExecutionStatus.RUNNING
                run.started_at = run.started_at or datetime.utcnow()
                run.error = None
                await self.emit(db, run_uuid, "run_started", "orchestrator", {"plan_id": plan_id, "repository": repository.name})
                await db.commit()
                max_runtime_seconds = max(60, min(int((plan.limits or {}).get("max_runtime_seconds", 1800)), 14_400))

            await asyncio.wait_for(self._execute_steps(plan_uuid, run_uuid), timeout=max_runtime_seconds)
        except TimeoutError:
            async with self.sessions() as db:
                run = await db.get(WorkflowRun, run_uuid)
                if run and run.status != ExecutionStatus.CANCELLED:
                    run.status = ExecutionStatus.TIMEOUT
                    run.error = "Run exceeded its approved time limit"
                    run.completed_at = datetime.utcnow()
                    await self.emit(db, run_uuid, "run_timed_out", "system", {"limit_seconds": max_runtime_seconds})
                    await db.commit()
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            async with self.sessions() as db:
                run = await db.get(WorkflowRun, run_uuid)
                if run and run.status != ExecutionStatus.CANCELLED:
                    run.status = ExecutionStatus.FAILED
                    run.error = str(exc)
                    run.completed_at = datetime.utcnow()
                    await self.emit(db, run_uuid, "run_failed", "system", {"message": str(exc)})
                    await db.commit()

    async def _execute_steps(self, plan_id: uuid.UUID, run_id: uuid.UUID) -> None:
        async with self.sessions() as db:
            plan = await db.get(TaskPlan, plan_id)
            assert plan is not None
            repository = await db.get(Repository, plan.repository_id)
            assert repository is not None
            steps = list((await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan_id).order_by(TaskStep.created_at))).all())
            if not steps:
                raise RuntimeError("Plan has no executable steps")
            integration, branch, base_revision = await self._prepare_integration(repository, run_id)
            run = await db.get(WorkflowRun, run_id)
            assert run is not None
            output = dict(run.output_data or {})
            output.update({"branch": branch, "integration_path": str(integration), "base_revision": base_revision})
            run.output_data = output
            db.add(RunArtifact(run_id=run_id, kind="branch", name="Managed integration branch", content=branch, metadata_={"path": str(integration), "base_revision": base_revision}))
            await self.emit(db, run_id, "workspace_ready", "system", {"branch": branch, "base_revision": base_revision})
            await db.commit()
            max_concurrency = max(
                1,
                min(
                    int(
                        (plan.limits or {}).get(
                            "max_concurrent_agents",
                            (plan.limits or {}).get("concurrent_agents", 3),
                        )
                    ),
                    8,
                ),
            )

        completed: set[str] = set()
        failed: set[str] = set()
        by_key = {step.key: step for step in steps}
        # Recovery and change-request passes reuse already integrated work. If
        # a worker died after committing but before fan-in, finish that
        # idempotent cherry-pick before scheduling new dependency-ready work.
        for step in steps:
            if step.status != ExecutionStatus.COMPLETED:
                continue
            commit = str((step.output or {}).get("commit") or "")
            if commit:
                ancestor_code, _ = await self._git_capture(integration, "merge-base", "--is-ancestor", commit, "HEAD")
                if ancestor_code:
                    code, merge_output = await self._git_capture(integration, "cherry-pick", commit)
                    if code:
                        await self._git_capture(integration, "cherry-pick", "--abort")
                        raise RuntimeError(f"Could not recover integrated step '{step.key}': {merge_output[-1000:]}")
            recovered_worktree = integration.parent / f"step-{str(step.id)[:8]}"
            if recovered_worktree.exists():
                await self._remove_worktree(integration, recovered_worktree)
            completed.add(step.key)
        while True:
            # Managed delegations append immutable child steps while a run is
            # active. Re-read the ledger between batches so approved work is
            # scheduled without making Redis or an in-memory graph authoritative.
            async with self.sessions() as db:
                steps = list((await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan_id).order_by(TaskStep.created_at))).all())
            by_key = {step.key: step for step in steps}
            if len(completed) >= len(steps):
                break
            if str(run_id) in self._cancelled or await self._is_cancelled(run_id):
                await self._finish_cancelled(run_id)
                return
            ready = [step for step in steps if step.key not in completed and step.key not in failed and set(step.depends_on or []).issubset(completed)]
            if not ready:
                waiting = [step.key for step in steps if step.key not in completed and step.key not in failed]
                raise RuntimeError(f"No dependency-ready steps remain: {', '.join(waiting)}")
            for offset in range(0, len(ready), max_concurrency):
                batch = ready[offset : offset + max_concurrency]
                batch_base = await self._git_output(integration, "rev-parse", "HEAD")
                results = await asyncio.gather(
                    *(self._run_step(step.id, run_id, integration.parent, batch_base, by_key) for step in batch),
                    return_exceptions=True,
                )
                for step, result in zip(batch, results, strict=True):
                    if isinstance(result, BaseException):
                        failed.add(step.key)
                        raise RuntimeError(f"{step.title}: {result}") from result
                    commit, worktree = result
                    if commit:
                        code, merge_output = await self._git_capture(integration, "cherry-pick", commit)
                        if code:
                            await self._git_capture(integration, "cherry-pick", "--abort")
                            async with self.sessions() as db:
                                db.add(RunArtifact(run_id=run_id, kind="merge_conflict", name=f"Conflict after {step.title}", content=merge_output[-16_000:], metadata_={"step": step.key, "commit": commit, "worktree": str(worktree)}))
                                await self.emit(db, run_id, "merge_conflict", "orchestrator", {"step": step.key, "commit": commit})
                                await db.commit()
                            raise RuntimeError(f"Integration conflict after step '{step.key}'")
                    completed.add(step.key)
                    await self._remove_worktree(integration, worktree)

        checks = await self._run_acceptance_checks(integration, base_revision, repository.allowed_commands or [])
        if any(check["status"] != "passed" for check in checks):
            raise RuntimeError("Objective acceptance checks failed")
        diff_stat = await self._git_output(integration, "diff", "--stat", f"{base_revision}..HEAD")
        patch = await self._git_output(integration, "diff", "--no-ext-diff", f"{base_revision}..HEAD")
        changed = [line for line in (await self._git_output(integration, "diff", "--name-only", f"{base_revision}..HEAD")).splitlines() if line]
        async with self.sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            assert run is not None
            run.status = ExecutionStatus.AWAITING_REVIEW
            run.completed_at = datetime.utcnow()
            output = dict(run.output_data or {})
            output.update({"summary": "Execution finished. Inspect the changes and checks, then approve or request changes.", "changed_files": changed, "checks": checks})
            run.output_data = output
            db.add(RunArtifact(run_id=run_id, kind="diff_summary", name="Changed files", content=diff_stat, metadata_={"branch": branch}))
            db.add(RunArtifact(run_id=run_id, kind="git_diff", name="Review patch", content=patch[:500_000], metadata_={"branch": branch, "truncated": len(patch) > 500_000, "changed_files": changed}))
            await self.emit(db, run_id, "run_ready_for_review", "orchestrator", {"branch": branch, "changed_files": changed, "checks": checks})
            await db.commit()

    async def _run_step(
        self,
        step_id: uuid.UUID,
        run_id: uuid.UUID,
        run_root: Path,
        base_revision: str,
        by_key: dict[str, TaskStep],
    ) -> tuple[str | None, Path]:
        worktree = run_root / f"step-{str(step_id)[:8]}"
        branch = f"step-{str(step_id)[:8]}"
        integration = run_root / "integration"
        # A worker can fail after registering a worktree but before completing
        # the step. A resumed ledger reuses completed commits and recreates only
        # failed/incomplete workspaces from the current integration revision.
        if worktree.exists():
            cleanup_code, cleanup_output = await self._git_capture(
                integration, "worktree", "remove", "--force", str(worktree)
            )
            if cleanup_code:
                raise RuntimeError(
                    f"Could not clean the previous workspace for '{branch}': "
                    f"{cleanup_output[-1000:]}"
                )
        await self._git_capture(integration, "branch", "-D", branch)
        await self._git(integration, "worktree", "add", "-b", branch, str(worktree), base_revision)
        if os.getenv("NEXUSFORGE_RUNNER_MODE", "http") == "docker":
            await asyncio.to_thread(_set_agent_ownership, worktree)
        async with self.sessions() as db:
            step = await db.get(TaskStep, step_id)
            assert step is not None
            plan = await db.get(TaskPlan, step.plan_id)
            assert plan is not None
            role = await db.get(RoleTemplateVersion, step.role_template_version_id) if step.role_template_version_id else None
            config = await get_tenant_llm_config(db, plan.tenant_id)
            agent = AgentInstance(
                run_id=run_id,
                task_step_id=step.id,
                role_template_version_id=role.id if role else None,
                name=f"{role.name if role else step.skill_slug} · {step.title}",
                role_slug=role.slug if role else step.skill_slug,
                role_snapshot={"name": role.name, "prompt": role.prompt, "capabilities": role.capabilities, "version": role.version} if role else {"slug": step.skill_slug},
                model_snapshot={"provider": config.provider, "model": config.model, "endpoint": config.endpoint},
                tool_grants=step.tool_grants or [],
                budget_usd=float((plan.limits or {}).get("per_agent_budget_usd", 1.0)),
                status=ExecutionStatus.RUNNING,
                started_at=datetime.utcnow(),
            )
            db.add(agent)
            step.status = ExecutionStatus.RUNNING
            step.started_at = datetime.utcnow()
            await db.flush()
            await self.emit(db, run_id, "agent_started", agent.role_slug, {"step": step.key, "title": step.title, "worktree": str(worktree)}, agent_instance_id=agent.id, task_step_id=step.id)
            await db.commit()
            prompt = self._build_prompt(plan, step, role, by_key)
            config_values = (config.provider, config.adapter, config.endpoint, config.api_key, config.model, config.source)
            agent_id, actor, max_retries = agent.id, agent.role_slug, max(0, step.max_retries)

        if step.writes_code and os.getenv("NEXUSFORGE_RUNNER_MODE", "http") != "docker":
            raise RuntimeError("The isolated Docker runner is required for code-writing steps")

        async def event_sink(event: dict[str, Any]) -> None:
            await self._persist_runner_event(run_id, step_id, agent_id, actor, event)

        last_error: Exception | None = None
        result: OpenCodeResult | None = None
        for attempt in range(max_retries + 1):
            try:
                result = await self.runner.run(
                    prompt=prompt,
                    workdir=worktree,
                    # NexusForge workforce roles are personas carried by the
                    # prompt and ledger, not OpenCode-native agent IDs.
                    agent=None,
                    provider=config_values[0],
                    adapter=config_values[1],
                    base_url=config_values[2],
                    api_key=config_values[3],
                    model=config_values[4],
                    custom_provider=config_values[5] == "database",
                    event_sink=event_sink,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                async with self.sessions() as db:
                    await self.emit(db, run_id, "step_retrying", actor, {"step": step.key, "attempt": attempt + 2, "message": str(exc)}, agent_instance_id=agent_id, task_step_id=step_id)
                    await db.commit()
        if result is None:
            await self._fail_step(step_id, run_id, agent_id, actor, str(last_error or "Agent failed"))
            raise last_error or RuntimeError("Agent failed")

        budget_error = await self._record_usage_and_check_budget(run_id, plan.id, step_id, agent_id, actor, result)
        if budget_error:
            await self._fail_step(step_id, run_id, agent_id, actor, budget_error)
            raise RuntimeError(budget_error)

        changed_files = await self._changed_files(worktree)
        if step.writes_code and not changed_files:
            message = "Code-writing step produced no repository changes"
            await self._fail_step(step_id, run_id, agent_id, actor, message)
            raise RuntimeError(message)
        if not result.text.strip() and not changed_files:
            message = "Agent returned neither a structured result nor an artifact"
            await self._fail_step(step_id, run_id, agent_id, actor, message)
            raise RuntimeError(message)

        commit: str | None = None
        if changed_files:
            await self._git(worktree, "add", "--all")
            await self._git(worktree, "-c", "user.name=NexusForge Agent", "-c", "user.email=agents@nexusforge.local", "commit", "-m", f"nexusforge: {step.title[:60]}")
            commit = await self._git_output(worktree, "rev-parse", "HEAD")
        summary = result.text[-16_000:]
        async with self.sessions() as db:
            refreshed = await db.get(TaskStep, step_id)
            agent = await db.get(AgentInstance, agent_id)
            assert refreshed is not None and agent is not None
            refreshed.status = ExecutionStatus.COMPLETED
            refreshed.completed_at = datetime.utcnow()
            refreshed.output = {"status": "completed", "summary": summary, "changed_files": changed_files, "commit": commit, "checks": [], "artifacts": [f"agent-output:{refreshed.key}"], "findings": [], "unresolved_questions": [], "confidence": 0.8, "recommended_next_action": "integrate"}
            agent.status = ExecutionStatus.COMPLETED
            agent.completed_at = datetime.utcnow()
            db.add(RunArtifact(run_id=run_id, kind="agent_output", name=refreshed.title, content=summary, metadata_={"step": refreshed.key, "agent_instance_id": str(agent_id), "changed_files": changed_files, "commit": commit}))
            await self.message(db, run_id, actor, "orchestrator", "result", {"step": refreshed.key, "summary": summary[-2000:], "changed_files": changed_files, "commit": commit}, [f"agent-output:{refreshed.key}"])
            await self.emit(db, run_id, "step_completed", actor, {"step": refreshed.key, "changed_files": changed_files, "commit": commit}, agent_instance_id=agent_id, task_step_id=step_id)
            await db.commit()
        return commit, worktree

    def _build_prompt(self, plan: TaskPlan, step: TaskStep, role: RoleTemplateVersion | None, by_key: dict[str, TaskStep]) -> str:
        dependency_context = []
        for key in step.depends_on or []:
            dependency = by_key.get(key)
            if dependency and dependency.output:
                dependency_context.append({"step": key, "summary": str(dependency.output.get("summary", ""))[-3000:]})
        return "\n\n".join(
            part for part in [
                role.prompt if role else f"You are the {step.skill_slug} agent.",
                f"SHARED GOAL:\n{plan.goal}",
                f"YOUR BOUNDED TASK:\n{step.title}\n{step.instructions}",
                f"ACCEPTANCE CRITERIA:\n{step.acceptance_criteria or 'Produce a verifiable result.'}",
                f"TOOL GRANTS:\n{json.dumps(step.tool_grants or [])}",
                f"CONSTRAINTS:\n{json.dumps(plan.constraints or {})}",
                f"DEPENDENCY FINDINGS:\n{json.dumps(dependency_context)}",
                "Work only inside the provided worktree. Report a concise summary, files changed, checks run, findings, unresolved questions, and the recommended next action.",
            ] if part
        )

    async def _persist_runner_event(self, run_id: uuid.UUID, step_id: uuid.UUID, agent_id: uuid.UUID, actor: str, event: dict[str, Any]) -> None:
        normalized = _normalize_runner_event(event)
        async with self.sessions() as db:
            await self.emit(db, run_id, normalized["type"], actor, normalized["payload"], agent_instance_id=agent_id, task_step_id=step_id)
            await db.commit()

    async def _record_usage_and_check_budget(
        self,
        run_id: uuid.UUID,
        plan_id: uuid.UUID,
        step_id: uuid.UUID,
        agent_id: uuid.UUID,
        actor: str,
        result: OpenCodeResult,
    ) -> str | None:
        async with self.sessions() as db:
            run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
            plan = await db.get(TaskPlan, plan_id)
            if run is None or plan is None:
                return "Run ledger disappeared while recording usage"
            run.tokens_used = int(run.tokens_used or 0) + max(0, result.tokens_used)
            run.cost_usd = float(run.cost_usd or 0) + max(0.0, result.cost_usd)
            await self.emit(
                db,
                run_id,
                "usage_recorded",
                actor,
                {"tokens": result.tokens_used, "cost_usd": result.cost_usd, "run_tokens": run.tokens_used, "run_cost_usd": run.cost_usd},
                agent_instance_id=agent_id,
                task_step_id=step_id,
            )
            limits = plan.limits or {}
            error = None
            if result.cost_usd > float(limits.get("per_agent_budget_usd", 2.0)):
                error = "Agent exceeded its approved cost budget"
            elif run.cost_usd > float(limits.get("max_total_cost_usd", 10.0)):
                error = "Run exceeded its approved total cost budget"
            await db.commit()
            return error

    async def _prepare_integration(self, repository: Repository, run_id: uuid.UUID) -> tuple[Path, str, str]:
        source = Path(repository.local_path).resolve()
        if not (source / ".git").exists():
            raise RuntimeError("Registered repository is not a Git checkout")
        root = Path(os.getenv("NEXUSFORGE_WORKTREE_ROOT", "/tmp/nexusforge-runs")) / str(run_id)
        root.mkdir(parents=True, exist_ok=True)
        integration = root / "integration"
        branch = f"nexusforge/run-{str(run_id)[:8]}"
        if integration.exists():
            current = await self._git_output(integration, "branch", "--show-current")
            return integration, current or branch, await self._git_output(integration, "merge-base", "HEAD", repository.default_branch)
        await self._git(root, "clone", "--no-hardlinks", "--branch", repository.default_branch, str(source), str(integration))
        base = await self._git_output(integration, "rev-parse", "HEAD")
        await self._git(integration, "checkout", "-b", branch)
        return integration, branch, base

    async def _run_acceptance_checks(self, worktree: Path, base: str, allowed_commands: list[Any]) -> list[dict[str, Any]]:
        commands: list[list[str]] = [["git", "diff", "--check", f"{base}..HEAD"]]
        for item in allowed_commands[:5]:
            if isinstance(item, list) and item and all(isinstance(part, str) for part in item):
                commands.append(item)
        checks = []
        for command in commands:
            if command[0] == "git":
                exit_code, output = await git_capture(worktree, *command[1:])
            else:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=worktree,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                exit_code = process.returncode or 0
                output = (stdout + stderr).decode("utf-8", "replace")
            output = output[-16_000:]
            check = {
                "command": command,
                "exit_code": exit_code,
                "status": "passed" if exit_code == 0 else "failed",
                "output": output,
            }
            checks.append(check)
        return checks

    async def _fail_step(self, step_id: uuid.UUID, run_id: uuid.UUID, agent_id: uuid.UUID, actor: str, message: str) -> None:
        async with self.sessions() as db:
            step = await db.get(TaskStep, step_id)
            agent = await db.get(AgentInstance, agent_id)
            if step:
                step.status, step.error, step.completed_at = ExecutionStatus.FAILED, message, datetime.utcnow()
            if agent:
                agent.status, agent.completed_at = ExecutionStatus.FAILED, datetime.utcnow()
            await self.emit(db, run_id, "step_failed", actor, {"step": step.key if step else str(step_id), "message": message}, agent_instance_id=agent_id, task_step_id=step_id)
            await db.commit()

    async def _is_cancelled(self, run_id: uuid.UUID) -> bool:
        async with self.sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            return bool(run and run.status == ExecutionStatus.CANCELLED)

    async def _finish_cancelled(self, run_id: uuid.UUID) -> None:
        async with self.sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            if run:
                run.status, run.completed_at = ExecutionStatus.CANCELLED, datetime.utcnow()
                await self.emit(db, run_id, "run_cancelled", "user", {})
                await db.commit()

    async def _changed_files(self, worktree: Path) -> list[str]:
        output = await self._git_output(worktree, "status", "--porcelain")
        return [line[3:].strip() for line in output.splitlines() if len(line) > 3]

    async def _remove_worktree(self, integration: Path, worktree: Path) -> None:
        await self._git_capture(integration, "worktree", "remove", "--force", str(worktree))

    async def _git(self, cwd: Path, *args: str) -> None:
        code, output = await self._git_capture(cwd, *args)
        if code:
            raise RuntimeError(output[-4000:] or f"git {' '.join(args)} failed")

    async def _git_capture(self, cwd: Path, *args: str) -> tuple[int, str]:
        return await git_capture(cwd, *args)

    async def _git_output(self, cwd: Path, *args: str) -> str:
        code, output = await self._git_capture(cwd, *args)
        if code:
            raise RuntimeError(output[-4000:])
        return output


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEYS.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(bearer\s+|(?:api[-_]?key|token|password|secret)[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    return value


def _normalize_runner_event(event: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(event.get("type") or event.get("event") or "runner_event").lower()
    if "command" in raw_type or "shell" in raw_type:
        event_type = "command"
    elif "tool" in raw_type:
        event_type = "tool_call"
    elif "file" in raw_type or "patch" in raw_type:
        event_type = "file_changed"
    elif "test" in raw_type or "check" in raw_type:
        event_type = "check"
    else:
        event_type = "agent_output"
    return {"type": event_type, "payload": _redact(event)}


def _set_agent_ownership(worktree: Path) -> None:
    """Grant only the sandbox UID ownership of its narrow managed worktree."""
    uid = int(os.getenv("NEXUSFORGE_RUNNER_UID", "10001"))
    gid = int(os.getenv("NEXUSFORGE_RUNNER_GID", "10001"))
    targets = [worktree]
    dot_git = worktree / ".git"
    if dot_git.is_file():
        value = dot_git.read_text().strip()
        if value.startswith("gitdir: "):
            git_dir = Path(value.removeprefix("gitdir: ")).resolve()
            if git_dir.parent.name == "worktrees":
                targets.append(git_dir.parent.parent)
    for target in targets:
        for root, directories, files in os.walk(target):
            os.chown(root, uid, gid)
            for name in directories:
                os.chown(Path(root) / name, uid, gid, follow_symlinks=False)
            for name in files:
                os.chown(Path(root) / name, uid, gid, follow_symlinks=False)
