"""Background plan executor with worktree isolation, Redis messaging, and coordinator."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm_runtime import get_tenant_llm_config
from app.models import (
    ExecutionStatus,
    Repository,
    RunArtifact,
    RunEvent,
    TaskPlan,
    TaskPlanStatus,
    TaskStep,
    WorkflowRun,
)
from packages.handoff.redis_streams import RedisMessageBus
from packages.task_runtime.coordinator import CoordinatorAgent
from packages.task_runtime.opencode import OpenCodeRunner

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Executes one approved plan at a time with Redis-based inter-agent messaging."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        message_bus: RedisMessageBus | None = None,
    ) -> None:
        self.sessions = sessions
        self.runner = OpenCodeRunner()
        self._cancelled: set[str] = set()
        self.message_bus = message_bus
        self._coordinators: dict[str, CoordinatorAgent] = {}

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    async def emit(self, db: AsyncSession, run_id: uuid.UUID, event_type: str, actor: str, payload: dict) -> None:
        sequence = (await db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)) or 0) + 1
        db.add(RunEvent(run_id=run_id, sequence=sequence, event_type=event_type, actor=actor, payload=payload))
        await db.flush()

    async def execute(self, plan_id: str, run_id: str) -> None:
        logger.info("Scheduler.execute started for plan=%s run=%s", plan_id, run_id)
        async with self.sessions() as db:
            plan = await db.get(TaskPlan, uuid.UUID(plan_id))
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            if plan is None or run is None or plan.status != TaskPlanStatus.APPROVED:
                logger.warning("Plan or run not found, or plan not approved: plan=%s run=%s", plan_id, run_id)
                return
            repository = await db.get(Repository, plan.repository_id)
            if repository is None:
                run.status, run.error = ExecutionStatus.FAILED, "Repository is unavailable"
                await db.commit()
                logger.error("Repository unavailable for plan=%s", plan_id)
                return
            run.status, run.started_at = ExecutionStatus.RUNNING, datetime.utcnow()
            await self.emit(db, run.id, "run_started", "manager", {"plan_id": plan_id, "repository": repository.name})
            await db.commit()
            logger.info("Run %s set to RUNNING", run_id)

        if self.message_bus:
            try:
                await self.message_bus.create_run_channel(run_id)
            except Exception as exc:
                logger.warning("Could not create Redis channel for run %s: %s", run_id, exc)

        try:
            logger.info("Starting _execute_steps for run=%s", run_id)
            await self._execute_steps(plan_id, run_id)
            logger.info("Finished _execute_steps for run=%s", run_id)
        except Exception as exc:
            logger.exception("Scheduler.execute failed for run=%s: %s", run_id, exc)
            async with self.sessions() as db:
                run = await db.get(WorkflowRun, uuid.UUID(run_id))
                if run is not None:
                    run.status, run.error, run.completed_at = ExecutionStatus.FAILED, str(exc), datetime.utcnow()
                    await self.emit(db, run.id, "run_failed", "system", {"message": str(exc)})
                    await db.commit()

        if self.message_bus and run_id in self._coordinators:
            await self._coordinators[run_id].stop()
            del self._coordinators[run_id]

    async def _execute_steps(self, plan_id: str, run_id: str) -> None:
        async with self.sessions() as db:
            plan = await db.get(TaskPlan, uuid.UUID(plan_id))
            assert plan is not None
            repository = await db.get(Repository, plan.repository_id)
            assert repository is not None
            steps = list((await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan.id).order_by(TaskStep.created_at))).all())
            repo_path = Path(repository.local_path).resolve()
            logger.info("Executing %d steps for run=%s repo=%s", len(steps), run_id, repo_path)
            if not (repo_path / ".git").exists():
                raise RuntimeError("Registered repository is not a Git checkout")
            run_root = Path(os.getenv("NEXUSFORGE_WORKTREE_ROOT", "/tmp/nexusforge-runs")) / run_id
            run_root.mkdir(parents=True, exist_ok=True)
            integration_branch = f"nexusforge/run-{run_id[:8]}"
            integration = run_root / "integration"
            await self._git(repo_path, "worktree", "add", "-b", integration_branch, str(integration), repository.default_branch)
            db.add(RunArtifact(run_id=uuid.UUID(run_id), kind="branch", name="integration", content=integration_branch, metadata_={"worktree": str(integration)}))
            await self.emit(db, uuid.UUID(run_id), "worktree_ready", "system", {"branch": integration_branch})
            await db.commit()

        step_dicts = [
            {
                "id": str(s.id),
                "key": s.key,
                "title": s.title,
                "depends_on": s.depends_on or [],
                "max_retries": s.max_retries,
                "skill_slug": s.skill_slug,
            }
            for s in steps
        ]

        if self.message_bus:
            coordinator = CoordinatorAgent(
                bus=self.message_bus,
                run_id=run_id,
                steps=step_dicts,
            )
            self._coordinators[run_id] = coordinator
            await coordinator.start()

        completed: set[str] = set()
        parallel_groups: dict[str | None, list] = {}
        for step in steps:
            group = getattr(step, "parallel_group", None)
            parallel_groups.setdefault(group, []).append(step)

        for step in steps:
            if run_id in self._cancelled:
                await self._finish_cancelled(run_id)
                return
            if not set(step.depends_on or []).issubset(completed):
                raise RuntimeError(f"Step '{step.key}' has unmet dependencies")
            await self._run_step(step.id, run_id, integration)
            async with self.sessions() as db:
                refreshed = await db.get(TaskStep, step.id)
                if refreshed is None or refreshed.status != ExecutionStatus.COMPLETED:
                    raise RuntimeError(refreshed.error if refreshed else "Task step disappeared")
            completed.add(step.key)

        async with self.sessions() as db:
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            assert run is not None
            diff = await self._git_output(integration, "diff", "--stat", "HEAD")
            patch = await self._git_output(
                integration,
                "diff",
                "--no-ext-diff",
                "HEAD",
            )
            run.status, run.completed_at = ExecutionStatus.NEEDS_REVIEW, datetime.utcnow()
            run.output_data = {"branch": integration_branch, "summary": "All worker steps completed; review the branch before merge."}
            db.add(RunArtifact(run_id=run.id, kind="diff_summary", name="git diff --stat", content=diff, metadata_={"branch": integration_branch}))
            db.add(
                RunArtifact(
                    run_id=run.id,
                    kind="git_diff",
                    name="git diff",
                    content=patch[:200_000],
                    metadata_={
                        "branch": integration_branch,
                        "truncated": len(patch) > 200_000,
                        "total_characters": len(patch),
                    },
                )
            )
            await self.emit(db, run.id, "run_ready_for_review", "reviewer", {"branch": integration_branch})
            await db.commit()

    async def _run_step(self, step_id: uuid.UUID, run_id: str, worktree: Path) -> None:
        async with self.sessions() as db:
            step = await db.get(TaskStep, step_id)
            assert step is not None
            plan = await db.get(TaskPlan, step.plan_id)
            assert plan is not None
            llm_config = await get_tenant_llm_config(db, plan.tenant_id)
            step.status, step.started_at = ExecutionStatus.RUNNING, datetime.utcnow()
            await self.emit(db, uuid.UUID(run_id), "step_started", step.skill_slug, {"step": step.key, "title": step.title})
            await db.commit()
            prompt = step.instructions
            nexus_phase = getattr(step, "nexus_phase", "build")
            role = getattr(step, "role", "")
            logger.info("Running step=%s skill=%s for run=%s", step.key, step.skill_slug, run_id)

        if self.message_bus:
            await self.message_bus.publish_status(
                run_id, step.skill_slug, step.key, "started",
                {"title": step.title, "nexus_phase": nexus_phase, "role": role},
            )

        try:
            env_extras: dict[str, str] = {}
            if self.message_bus:
                env_extras["REDIS_URL"] = self.message_bus._redis_url
                env_extras["AGENT_INBOX"] = self.message_bus.agent_inbox(run_id, step.key)
                env_extras["COORDINATOR_INBOX"] = self.message_bus.coordinator_inbox(run_id)

            result = await self.runner.run(
                prompt=prompt, workdir=worktree, agent=step.skill_slug,
                env_extras=env_extras if env_extras else None,
                provider=llm_config.provider,
                adapter=llm_config.adapter,
                base_url=llm_config.endpoint,
                api_key=llm_config.api_key,
                model=llm_config.model,
                custom_provider=llm_config.source == "database",
            )
            logger.info("Step=%s completed, output length=%d", step.key, len(result.text))
            async with self.sessions() as db:
                step = await db.get(TaskStep, step_id)
                assert step is not None
                step.status, step.completed_at = ExecutionStatus.COMPLETED, datetime.utcnow()
                step.output = {"summary": result.text[-8000:], "event_count": len(result.events)}
                db.add(RunArtifact(run_id=uuid.UUID(run_id), kind="agent_output", name=step.key, content=result.text[-16000:], metadata_={"skill": step.skill_slug}))
                await self.emit(db, uuid.UUID(run_id), "step_completed", step.skill_slug, {"step": step.key})
                await db.commit()

            if self.message_bus:
                await self.message_bus.publish_findings(
                    run_id, step.skill_slug, result.text[-2000:],
                    artifact_refs=[f"artifact:{step.key}"],
                )

        except Exception as exc:
            logger.exception("Step=%s failed for run=%s: %s", step.key if step else "unknown", run_id, exc)
            async with self.sessions() as db:
                step = await db.get(TaskStep, step_id)
                if step is not None:
                    step.status, step.error, step.completed_at = ExecutionStatus.FAILED, str(exc), datetime.utcnow()
                    await self.emit(db, uuid.UUID(run_id), "step_failed", step.skill_slug, {"step": step.key, "message": str(exc)})
                    await db.commit()

            if self.message_bus:
                await self.message_bus.publish_status(
                    run_id, step.skill_slug, step.key, "failed",
                    {"error": str(exc)},
                )
            raise

    async def _finish_cancelled(self, run_id: str) -> None:
        async with self.sessions() as db:
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            if run is not None:
                run.status, run.completed_at = ExecutionStatus.CANCELLED, datetime.utcnow()
                await self.emit(db, run.id, "run_cancelled", "user", {})
                await db.commit()

    async def _git(self, cwd: Path, *args: str) -> None:
        result = await asyncio.create_subprocess_exec("git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await result.communicate()
        if result.returncode:
            raise RuntimeError(stderr.decode("utf-8", "replace")[-2000:])

    async def _git_output(self, cwd: Path, *args: str) -> str:
        result = await asyncio.create_subprocess_exec("git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await result.communicate()
        if result.returncode:
            return stderr.decode("utf-8", "replace")
        return stdout.decode("utf-8", "replace")
