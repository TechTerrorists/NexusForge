"""Durable executor for the bounded, zero-token-by-default workflow DSL."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm_runtime import get_tenant_llm_config
from app.models import (
    AgentInstance,
    ExecutionStatus,
    RoleTemplateVersion,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowVersion,
)
from packages.task_runtime.opencode import OpenCodeRunner
from packages.task_runtime.scheduler import TaskScheduler
from packages.task_runtime.workflow_graph import CompiledStep, GraphValidationError, compile_graph

_TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


class DeterministicWorkflowExecutor:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], scheduler: TaskScheduler) -> None:
        self.sessions = sessions
        self.scheduler = scheduler
        self.runner = OpenCodeRunner()

    async def execute(self, run_id: uuid.UUID) -> None:
        async with self.sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            if not run or not run.workflow_version_id:
                raise RuntimeError("Workflow run has no immutable version")
            version = await db.get(WorkflowVersion, run.workflow_version_id)
            workflow = await db.get(Workflow, run.workflow_id)
            if not version or not workflow:
                raise RuntimeError("Workflow version is unavailable")
            steps = compile_graph(version.graph_config or {})
            run.status = ExecutionStatus.RUNNING
            run.started_at = run.started_at or datetime.utcnow()
            run.error = None
            await self.scheduler.emit(db, run.id, "workflow_started", "workflow", {"version": version.version, "test_mode": bool((run.input_data or {}).get("test_mode"))})
            await db.commit()
            tenant_id = workflow.tenant_id
            context: dict[str, Any] = {"input": (run.input_data or {}).get("payload", {}), "nodes": {}}
            test_mode = bool((run.input_data or {}).get("test_mode"))

        previous_node_runs = await self._node_runs(run_id)
        completed = {item.node_key for item in previous_node_runs if item.status == ExecutionStatus.COMPLETED}
        context["nodes"] = {
            item.node_key: item.output_data
            for item in previous_node_runs
            if item.status == ExecutionStatus.COMPLETED
        }
        while len(completed) < len(steps):
            ready = [step for step in steps if step.key not in completed and set(step.depends_on).issubset(completed)]
            if not ready:
                raise RuntimeError("Workflow is blocked by unresolved dependencies")
            for step in ready:
                existing = next((item for item in await self._node_runs(run_id) if item.node_key == step.key), None)
                if existing and existing.status == ExecutionStatus.AWAITING_APPROVAL:
                    async with self.sessions() as db:
                        run = await db.get(WorkflowRun, run_id)
                        assert run is not None
                        run.status = ExecutionStatus.AWAITING_APPROVAL
                        await db.commit()
                    return
                skip_reason = _skip_reason(step, context)
                if skip_reason:
                    output = {"skipped": True, "reason": skip_reason}
                    await self._complete_skipped(run_id, step, output)
                    context["nodes"][step.key] = output
                    completed.add(step.key)
                    continue
                try:
                    output = await self._execute_node(run_id, tenant_id, step, context, test_mode)
                except ApprovalRequired:
                    return
                context["nodes"][step.key] = output
                completed.add(step.key)

        async with self.sessions() as db:
            run = await db.get(WorkflowRun, run_id)
            assert run is not None
            run.status = ExecutionStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            node_runs = await self._node_runs(run_id)
            run.tokens_used = sum(int((item.output_data or {}).get("tokens_used", 0)) for item in node_runs)
            run.cost_usd = sum(float((item.output_data or {}).get("cost_usd", 0.0)) for item in node_runs)
            run.output_data = {"nodes": context["nodes"], "test_mode": test_mode, "llm_tokens": run.tokens_used, "cost_usd": run.cost_usd}
            await self.scheduler.emit(db, run.id, "workflow_completed", "workflow", {"node_count": len(completed), "llm_tokens": run.tokens_used, "cost_usd": run.cost_usd})
            await db.commit()

    async def _execute_node(
        self,
        run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        step: CompiledStep,
        context: dict[str, Any],
        test_mode: bool,
    ) -> dict[str, Any]:
        async with self.sessions() as db:
            node_run = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == step.key))
            if not node_run:
                node_run = WorkflowNodeRun(run_id=run_id, node_key=step.key, node_type=step.node_type, input_data=_bounded(context), status=ExecutionStatus.RUNNING, started_at=datetime.utcnow())
                db.add(node_run)
            else:
                node_run.status, node_run.started_at, node_run.error = ExecutionStatus.RUNNING, datetime.utcnow(), None
            await self.scheduler.emit(db, run_id, "node_started", "workflow", {"node": step.key, "type": step.node_type})
            await db.commit()

        try:
            output = await self._dispatch(run_id, tenant_id, step, context, test_mode)
        except ApprovalRequired:
            async with self.sessions() as db:
                node_run = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == step.key))
                run = await db.get(WorkflowRun, run_id)
                assert node_run is not None and run is not None
                node_run.status = ExecutionStatus.AWAITING_APPROVAL
                run.status = ExecutionStatus.AWAITING_APPROVAL
                await self.scheduler.emit(db, run_id, "node_approval_required", "workflow", {"node": step.key, "label": step.title})
                await db.commit()
            raise
        except Exception as exc:
            async with self.sessions() as db:
                node_run = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == step.key))
                assert node_run is not None
                node_run.status, node_run.error, node_run.completed_at = ExecutionStatus.FAILED, str(exc), datetime.utcnow()
                await self.scheduler.emit(db, run_id, "node_failed", "workflow", {"node": step.key, "message": str(exc)})
                await db.commit()
            raise

        async with self.sessions() as db:
            node_run = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == step.key))
            assert node_run is not None
            node_run.status, node_run.output_data, node_run.completed_at = ExecutionStatus.COMPLETED, _bounded(output), datetime.utcnow()
            await self.scheduler.emit(db, run_id, "node_completed", "workflow", {"node": step.key, "type": step.node_type, "output": _bounded(output)})
            await db.commit()
        return output

    async def _dispatch(self, run_id: uuid.UUID, tenant_id: uuid.UUID, step: CompiledStep, context: dict[str, Any], test_mode: bool) -> dict[str, Any]:
        config = step.config
        kind = step.node_type
        if kind in {"task", "map"}:
            mapping = config.get("mapping", {"value": config.get("value", "{{ input }}")})
            return {str(key): _render(value, context) for key, value in mapping.items()}
        if kind == "condition":
            left = _resolve(str(config.get("left", "")), context)
            right = config.get("right")
            operator = str(config.get("operator", "equals"))
            operations = {
                "equals": left == right,
                "not_equals": left != right,
                "contains": right in left if isinstance(left, (str, list, dict)) else False,
                "exists": left is not None,
            }
            if operator not in operations:
                raise RuntimeError(f"Unsupported condition operator: {operator}")
            return {"matched": operations[operator], "value": left}
        if kind == "foreach":
            items = _resolve(str(config.get("items", "input.items")), context)
            if not isinstance(items, list):
                raise RuntimeError("foreach input must resolve to an array")
            maximum = int(config.get("max_items", 25))
            if len(items) > maximum:
                raise RuntimeError(f"foreach input exceeds its {maximum}-item bound")
            return {"items": items, "count": len(items)}
        if kind == "approval":
            if test_mode:
                return {"approved": True, "simulated": True}
            raise ApprovalRequired()
        if kind == "http_request":
            url = str(_render(config.get("url", ""), context))
            await _validate_url(url, [str(domain) for domain in config.get("allowed_domains", [])])
            if test_mode:
                return {"simulated": True, "method": config.get("method", "GET"), "url": url}
            async with httpx.AsyncClient(timeout=min(float(config.get("timeout_seconds", 15)), 30), follow_redirects=False) as client:
                response = await client.request(str(config.get("method", "GET")).upper(), url, json=_render(config.get("body"), context) if config.get("body") is not None else None)
            return {"status_code": response.status_code, "body": response.text[:100_000], "headers": {key: value for key, value in response.headers.items() if key.lower() in {"content-type", "etag", "location"}}}
        if kind == "command":
            argv = [str(_render(part, context)) for part in config.get("argv", [])]
            allowed = {item.strip() for item in os.getenv("NEXUSFORGE_WORKFLOW_COMMANDS", "").split(",") if item.strip()}
            if not argv or argv[0] not in allowed:
                raise RuntimeError("Command is not in the workflow allowlist")
            if test_mode:
                return {"simulated": True, "argv": argv}
            return await _sandbox_command(argv, min(int(config.get("timeout_seconds", 30)), 60))
        if kind == "notification":
            url = str(_render(config.get("url", ""), context))
            message = _render(config.get("message", ""), context)
            await _validate_url(url, [str(domain) for domain in config.get("allowed_domains", [])])
            if test_mode:
                return {"simulated": True, "url": url, "message": message}
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(url, json={"message": message})
            return {"status_code": response.status_code, "delivered": 200 <= response.status_code < 300}
        if kind in {"llm", "agent"}:
            if test_mode:
                return {"simulated": True, "model_call": kind, "tokens_used": 0, "cost_usd": 0.0}
            async with self.sessions() as db:
                llm = await get_tenant_llm_config(db, tenant_id)
                role = None
                agent_id = None
                if kind == "agent":
                    role_slug = str(config.get("role", ""))
                    role = await db.scalar(select(RoleTemplateVersion).where(
                        RoleTemplateVersion.slug == role_slug,
                        RoleTemplateVersion.is_active.is_(True),
                        RoleTemplateVersion.is_executable.is_(True),
                        or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == tenant_id),
                    ))
                    if role is None:
                        raise RuntimeError(f"Workflow agent role '{role_slug}' is unavailable or not executable")
                    instance = AgentInstance(
                        run_id=run_id,
                        name=f"{role.name} · {step.title}",
                        role_template_version_id=role.id,
                        role_slug=role.slug,
                        role_snapshot={"name": role.name, "prompt": role.prompt, "capabilities": role.capabilities, "version": role.version},
                        model_snapshot={"provider": llm.provider, "model": llm.model, "endpoint": llm.endpoint},
                        tool_grants=list(config.get("tool_grants", [])),
                        budget_usd=float(config.get("budget_usd", 1.0)),
                        status=ExecutionStatus.RUNNING,
                        started_at=datetime.utcnow(),
                    )
                    db.add(instance)
                    await db.flush()
                    agent_id = instance.id
                    await self.scheduler.emit(db, run_id, "agent_started", role.slug, {"node": step.key, "title": step.title}, agent_instance_id=agent_id)
                    await db.commit()
            prompt = str(_render(config.get("prompt", ""), context))
            if role is not None:
                prompt = f"{role.prompt}\n\nBOUNDED WORKFLOW TASK:\n{prompt}"
            with tempfile.TemporaryDirectory(prefix="nexusforge-advisory-") as directory:
                try:
                    result = await self.runner.run(
                        prompt=prompt,
                        workdir=Path(directory),
                        agent=role.slug if role else "workflow-llm",
                        provider=llm.provider,
                        adapter=llm.adapter,
                        base_url=llm.endpoint,
                        api_key=llm.api_key,
                        model=llm.model,
                        custom_provider=llm.source == "database",
                        mode="http",
                    )
                except Exception as exc:
                    if agent_id is not None:
                        async with self.sessions() as db:
                            instance = await db.get(AgentInstance, agent_id)
                            if instance:
                                instance.status, instance.completed_at = ExecutionStatus.FAILED, datetime.utcnow()
                                await self.scheduler.emit(db, run_id, "agent_failed", role.slug if role else "workflow-agent", {"node": step.key, "message": str(exc)}, agent_instance_id=agent_id)
                                await db.commit()
                    raise
            if agent_id is not None:
                async with self.sessions() as db:
                    instance = await db.get(AgentInstance, agent_id)
                    if instance:
                        instance.status, instance.completed_at = ExecutionStatus.COMPLETED, datetime.utcnow()
                        if result.cost_usd > instance.budget_usd:
                            instance.status = ExecutionStatus.FAILED
                            await self.scheduler.emit(db, run_id, "agent_budget_exceeded", role.slug if role else "workflow-agent", {"node": step.key, "cost_usd": result.cost_usd, "budget_usd": instance.budget_usd}, agent_instance_id=agent_id)
                            await db.commit()
                            raise RuntimeError("Workflow agent exceeded its node budget")
                        await self.scheduler.message(db, run_id, role.slug if role else "workflow-agent", "orchestrator", "result", {"node": step.key, "summary": result.text[-2000:]})
                        await self.scheduler.emit(db, run_id, "agent_completed", role.slug if role else "workflow-agent", {"node": step.key, "tokens": result.tokens_used, "cost_usd": result.cost_usd}, agent_instance_id=agent_id)
                        await db.commit()
            return {"text": result.text, "tokens_used": result.tokens_used, "cost_usd": result.cost_usd, "model": llm.model}
        raise GraphValidationError(f"Unsupported workflow node: {kind}")

    async def _node_runs(self, run_id: uuid.UUID) -> list[WorkflowNodeRun]:
        async with self.sessions() as db:
            return list((await db.scalars(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id))).all())

    async def _complete_skipped(self, run_id: uuid.UUID, step: CompiledStep, output: dict[str, Any]) -> None:
        async with self.sessions() as db:
            node_run = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == step.key))
            if not node_run:
                node_run = WorkflowNodeRun(run_id=run_id, node_key=step.key, node_type=step.node_type)
                db.add(node_run)
            node_run.status, node_run.output_data, node_run.completed_at = ExecutionStatus.COMPLETED, output, datetime.utcnow()
            await self.scheduler.emit(db, run_id, "node_skipped", "workflow", {"node": step.key, **output})
            await db.commit()


class ApprovalRequired(RuntimeError):
    pass


def _resolve(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    normalized = path[2:-2].strip() if path.startswith("{{") and path.endswith("}}") else path
    for part in normalized.split("."):
        if part == "":
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _skip_reason(step: CompiledStep, context: dict[str, Any]) -> str | None:
    for rule in step.config.get("_incoming_conditions", []):
        result = context.get("nodes", {}).get(str(rule.get("source")), {})
        if isinstance(result, dict) and bool(result.get("matched")) != bool(rule.get("when")):
            return f"Condition {rule.get('source')} did not select this branch"
    return None


def _render(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, context) for item in value]
    if not isinstance(value, str):
        return value
    exact = _TEMPLATE.fullmatch(value)
    if exact:
        return _resolve(exact.group(1), context)
    return _TEMPLATE.sub(lambda match: str(_resolve(match.group(1), context) or ""), value)


async def _validate_url(url: str, allowed_domains: list[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("Only absolute HTTP(S) URLs are supported")
    hostname = parsed.hostname.lower()
    if not any(hostname == domain.lower() or hostname.endswith(f".{domain.lower()}") for domain in allowed_domains):
        raise RuntimeError("HTTP target is outside the node domain allowlist")
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise RuntimeError("HTTP target resolves to a non-public address")


def _bounded(value: Any) -> Any:
    encoded = json.dumps(value, default=str)
    if len(encoded) <= 100_000:
        return json.loads(encoded)
    return {"truncated": True, "preview": encoded[:100_000]}


async def _sandbox_command(argv: list[str], timeout_seconds: int) -> dict[str, Any]:
    image = os.getenv("NEXUSFORGE_RUNNER_IMAGE", "nexusforge-opencode-runner:latest")
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--entrypoint", argv[0],
        image, *argv[1:],
    ]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    result = {"argv": argv, "exit_code": process.returncode, "stdout": stdout.decode("utf-8", "replace")[-50_000:], "stderr": stderr.decode("utf-8", "replace")[-50_000:]}
    if process.returncode:
        raise RuntimeError(f"Sandboxed command failed with exit code {process.returncode}: {result['stderr'][-1000:]}")
    return result
