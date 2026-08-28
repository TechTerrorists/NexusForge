from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, require_role
from app.database import get_db
from app.llm_runtime import get_tenant_llm_config
from app.models import (
    AgentInstance, AgentMessageRecord, ChatMessage, ChatSession, DelegationRequest,
    ExecutionJob, ExecutionStatus, Repository, RoleTemplateVersion, RunArtifact,
    RunEvent, TaskPlan, TaskPlanStatus, TaskStep, User, UserRole, Workflow,
    WorkflowRun, WorkflowStatus,
)
from packages.task_runtime.planner import PlannedStep, llm_create_plan
from packages.task_runtime.scheduler import TaskScheduler
from packages.task_runtime.skill_retriever import retrieve_roles
from packages.task_runtime.workflow_graph import GraphValidationError, compile_graph, validate_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["collaborative tasks"])


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    local_path: str
    default_branch: str = "main"
    allowed_commands: list[list[str] | str] = Field(default_factory=list, max_length=5)


class SessionCreate(BaseModel):
    repository_id: uuid.UUID | None = None
    title: str = "New software task"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class PlanDecision(BaseModel):
    approved: bool


class PlanStepUpdate(BaseModel):
    id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=20000)
    role_slug: str = Field(min_length=1, max_length=255)
    depends_on: list[str] = Field(default_factory=list)
    writes_code: bool = False
    nexus_phase: str = "build"
    role: str = ""
    parallel_group: str | None = None
    max_retries: int = Field(default=2, ge=0, le=5)
    acceptance_criteria: str = Field(default="", max_length=4000)
    expected_artifacts: list[str] = Field(default_factory=list)
    tool_grants: list[str] = Field(default_factory=list)
    side_effect_class: str = "workspace"


class PlanUpdate(BaseModel):
    goal: str | None = Field(default=None, min_length=1, max_length=20000)
    constraints: dict | None = None
    limits: dict | None = None
    steps: list[PlanStepUpdate] | None = None


class RunReview(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=4000)


class RunMerge(BaseModel):
    target_branch: str | None = Field(default=None, max_length=255)
    expected_base_revision: str


class DelegationCreate(BaseModel):
    requester_step_id: uuid.UUID
    role_slug: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=12000)
    acceptance_criteria: str = Field(default="", max_length=4000)


class WorkflowValidate(BaseModel):
    graph_config: dict


LIMIT_RANGES: dict[str, tuple[float, float]] = {
    "max_agents": (1, 32),
    "max_concurrent_agents": (1, 8),
    "max_delegation_depth": (0, 4),
    "max_replans": (0, 4),
    "max_runtime_seconds": (60, 14_400),
    "max_total_cost_usd": (0, 1_000),
    "per_agent_budget_usd": (0, 100),
}


def _repository_response(repository: Repository) -> dict:
    return {
        "id": str(repository.id),
        "name": repository.name,
        "local_path": repository.local_path,
        "managed_path": repository.managed_path,
        "default_branch": repository.default_branch,
        "allowed_commands": repository.allowed_commands or [],
    }


def _normalize_allowed_commands(commands: list[list[str] | str]) -> list[list[str]]:
    normalized: list[list[str]] = []
    for command in commands:
        parts = shlex.split(command) if isinstance(command, str) else command
        if not parts or len(parts) > 32 or any(not isinstance(part, str) or not part or "\x00" in part for part in parts):
            raise HTTPException(status_code=422, detail="Each acceptance command must contain 1-32 safe arguments")
        normalized.append(parts)
    return normalized


def _validate_repository_root(path: Path) -> None:
    configured_root = os.getenv("NEXUSFORGE_PROJECTS_ROOT")
    if not configured_root:
        return
    root = Path(configured_root).expanduser().resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=422, detail=f"Repository must be inside the configured projects root: {root}")


async def _git_capture(cwd: Path, *args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode("utf-8", "replace").strip()


async def _repository_preflight(repository: Repository, *, require_tool_runner: bool = True) -> dict:
    path = Path(repository.local_path).resolve()
    checks: list[dict] = []
    checks.append({"key": "path", "ok": path.is_dir(), "detail": str(path)})
    checks.append({"key": "git", "ok": (path / ".git").exists(), "detail": "Git checkout required"})
    checks.append({"key": "writable", "ok": os.access(path, os.W_OK), "detail": "Required for explicit merge only"})
    if (path / ".git").exists():
        branch_code, branch = await _git_capture(path, "branch", "--show-current")
        head_code, head = await _git_capture(path, "rev-parse", repository.default_branch)
        status_code, status_output = await _git_capture(path, "status", "--porcelain")
        checks.extend(
            [
                {"key": "default_branch", "ok": head_code == 0, "detail": repository.default_branch},
                {"key": "current_branch", "ok": branch_code == 0, "detail": branch or "detached"},
                {"key": "clean", "ok": status_code == 0 and not status_output, "detail": "Clean working tree" if not status_output else "Local changes present; planning is allowed but merge will be blocked"},
            ]
        )
    runner_mode = os.getenv("NEXUSFORGE_RUNNER_MODE", "docker")
    checks.append({"key": "runner", "ok": not require_tool_runner or runner_mode == "docker", "detail": runner_mode if runner_mode == "docker" else "Advisory-only runner; v1 code execution requires Docker"})
    ready = all(check["ok"] for check in checks if check["key"] not in {"clean", "current_branch"})
    return {
        "ok": ready,
        "ready": ready,
        "checks": {
            check["key"]: {"ok": check["ok"], "message": check["detail"]}
            for check in checks
        },
    }


async def _owned_repository(db: AsyncSession, user: User, repository_id: uuid.UUID) -> Repository:
    repository = await db.scalar(select(Repository).where(Repository.id == repository_id, Repository.tenant_id == user.tenant_id, Repository.is_active.is_(True)))
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


async def _owned_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> WorkflowRun:
    run = await db.scalar(
        select(WorkflowRun).join(Workflow).where(WorkflowRun.id == run_id, Workflow.tenant_id == user.tenant_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _apply_run_review(
    run: WorkflowRun,
    *,
    approved: bool,
    feedback: str,
    reviewer_id: uuid.UUID,
) -> dict:
    normalized_feedback = feedback.strip()
    if not approved and not normalized_feedback:
        raise ValueError("Feedback is required when rejecting a result")

    reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    decision = "approved" if approved else "rejected"
    output = dict(run.output_data or {})
    output["review"] = {
        "decision": decision,
        "feedback": normalized_feedback,
        "reviewed_by": str(reviewer_id),
        "reviewed_at": reviewed_at.isoformat(),
    }
    run.output_data = output
    run.status = ExecutionStatus.COMPLETED if approved else ExecutionStatus.CHANGES_REQUESTED
    return output


@router.post("/repositories", status_code=status.HTTP_201_CREATED)
async def register_repository(req: RepositoryCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    path = Path(req.local_path).expanduser().resolve()
    _validate_repository_root(path)
    if not path.is_dir() or not (path / ".git").exists():
        raise HTTPException(status_code=422, detail="local_path must be an existing Git checkout")
    existing = await db.scalar(select(Repository.id).where(Repository.tenant_id == user.tenant_id, Repository.local_path == str(path)))
    if existing is not None:
        raise HTTPException(status_code=409, detail="This repository is already registered")
    branch_code, _ = await _git_capture(path, "rev-parse", "--verify", req.default_branch)
    if branch_code:
        raise HTTPException(status_code=422, detail=f"Default branch '{req.default_branch}' does not exist")
    repository = Repository(tenant_id=user.tenant_id, name=req.name, local_path=str(path), default_branch=req.default_branch, allowed_commands=_normalize_allowed_commands(req.allowed_commands))
    db.add(repository)
    await db.flush()
    return _repository_response(repository)


@router.get("/repositories")
async def list_repositories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    repositories = (await db.scalars(select(Repository).where(Repository.tenant_id == user.tenant_id, Repository.is_active.is_(True)).order_by(Repository.name))).all()
    return [_repository_response(repository) for repository in repositories]


@router.get("/repositories/{repository_id}/preflight")
async def repository_preflight(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    repository = await _owned_repository(db, user, repository_id)
    return await _repository_preflight(repository)


@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(req: SessionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    if req.repository_id is not None:
        await _owned_repository(db, user, req.repository_id)
    session = ChatSession(tenant_id=user.tenant_id, repository_id=req.repository_id, created_by=user.id, title=req.title)
    db.add(session)
    await db.flush()
    return {"id": str(session.id), "title": session.title, "repository_id": str(session.repository_id) if session.repository_id else None}


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    session = await db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.tenant_id == user.tenant_id))
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    messages = (await db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at))).all()
    return {"id": str(session.id), "title": session.title, "repository_id": str(session.repository_id) if session.repository_id else None, "messages": [{"id": str(message.id), "role": message.role, "content": message.content, "created_at": message.created_at.isoformat()} for message in messages]}


@router.post("/chat/sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(session_id: uuid.UUID, req: MessageCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    session = await db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.tenant_id == user.tenant_id))
    if session is None or session.repository_id is None:
        raise HTTPException(status_code=422, detail="Choose a repository before planning a software task")
    await _owned_repository(db, user, session.repository_id)
    db.add(ChatMessage(session_id=session.id, role="user", content=req.content))
    await db.flush()

    roles = list((await db.scalars(
        select(RoleTemplateVersion)
        .where(
            RoleTemplateVersion.is_active.is_(True),
            RoleTemplateVersion.is_executable.is_(True),
            or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
        )
        .order_by(RoleTemplateVersion.slug, RoleTemplateVersion.version.desc())
    )).all())
    candidates = retrieve_roles(req.content, roles, limit=14)
    if not candidates:
        raise HTTPException(status_code=422, detail="No executable workforce roles are available; import the Agency Agents catalog first")

    llm_config = await get_tenant_llm_config(db, user.tenant_id)
    steps = await llm_create_plan(
        req.content,
        candidates,
        model_provider=llm_config.adapter,
        model_name=llm_config.model,
        api_key=llm_config.api_key,
        base_url=llm_config.endpoint,
        custom_provider=llm_config.source == "database",
    )

    plan = TaskPlan(
        tenant_id=user.tenant_id, session_id=session.id,
        repository_id=session.repository_id, goal=req.content,
        status=TaskPlanStatus.AWAITING_APPROVAL,
        plan_data={"version": 3, "planner": "llm", "candidate_roles": [item.slug for item in candidates]},
        constraints={"repository_scope": "registered_repository", "requires_final_review": True},
        limits={"max_agents": 8, "max_concurrent_agents": 4, "max_delegation_depth": 2, "max_replans": 2, "max_runtime_seconds": 1800, "max_total_cost_usd": 10.0, "per_agent_budget_usd": 2.0},
        estimated_cost_usd=0.0, created_by=user.id,
    )
    db.add(plan)
    await db.flush()

    role_lookup = {role.slug: role for role in roles}
    for item in steps:
        role_template = role_lookup.get(item.skill_slug)
        db.add(TaskStep(
            plan_id=plan.id, key=item.key, title=item.title,
            instructions=item.instructions, skill_slug=item.skill_slug,
            role_template_version_id=role_template.id if role_template else None,
            depends_on=item.depends_on, writes_code=item.writes_code,
            nexus_phase=item.nexus_phase, role=item.role,
            parallel_group=item.parallel_group, max_retries=item.max_retries,
            acceptance_criteria=item.acceptance_criteria,
            expected_artifacts=list(item.expected_artifacts),
            tool_grants=list(item.tool_grants),
            side_effect_class=item.side_effect_class,
        ))
    await db.flush()

    phase_summary = ", ".join(sorted({s.nexus_phase for s in steps}))
    assistant = (
        f"I analyzed your task and created a {len(steps)}-step plan "
        f"across NEXUS phases: {phase_summary}. "
        f"Review the roles and subtasks, then approve to start isolated workers."
    )
    db.add(ChatMessage(session_id=session.id, role="assistant", content=assistant))
    await db.flush()
    return {"message": assistant, "plan": await _plan_response(db, plan)}


async def _plan_response(db: AsyncSession, plan: TaskPlan) -> dict:
    steps = (await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan.id).order_by(TaskStep.created_at))).all()
    return {
        "id": str(plan.id),
        "goal": plan.goal,
        "status": plan.status.value,
        "estimated_cost_usd": plan.estimated_cost_usd,
        "constraints": plan.constraints or {},
        "limits": plan.limits or {},
        "steps": [
            {
                "id": str(step.id),
                "key": step.key,
                "title": step.title,
                "instructions": step.instructions,
                "skill": step.skill_slug,
                "role_slug": step.skill_slug,
                "depends_on": step.depends_on or [],
                "writes_code": step.writes_code,
                "status": step.status.value,
                "nexus_phase": getattr(step, "nexus_phase", "build"),
                "role": getattr(step, "role", ""),
                "parallel_group": getattr(step, "parallel_group", None),
                "acceptance_criteria": getattr(step, "acceptance_criteria", ""),
                "expected_artifacts": getattr(step, "expected_artifacts", []) or [],
                "tool_grants": getattr(step, "tool_grants", []) or [],
                "side_effect_class": getattr(step, "side_effect_class", "workspace"),
                "delegation_depth": getattr(step, "delegation_depth", 0),
            }
            for step in steps
        ],
    }


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    plan = await db.scalar(select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.tenant_id == user.tenant_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="Task plan not found")
    return await _plan_response(db, plan)


def _validate_step_updates(steps: list[PlanStepUpdate]) -> None:
    ids = [str(step.id) for step in steps]
    # Dependencies use stable step keys, so validate against the submitted role-independent keys below.
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Plan contains duplicate step IDs")
    allowed_effects = {"read_only", "workspace", "external", "privileged"}
    for step in steps:
        if step.side_effect_class not in allowed_effects:
            raise HTTPException(status_code=422, detail=f"Invalid side-effect class for {step.title}")


def _validate_limits(limits: dict) -> dict[str, float | int]:
    unknown = sorted(set(limits) - set(LIMIT_RANGES))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown execution limits: {', '.join(unknown)}")
    validated: dict[str, float | int] = {}
    for key, value in limits.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise HTTPException(status_code=422, detail=f"Execution limit '{key}' must be numeric")
        minimum, maximum = LIMIT_RANGES[key]
        if not minimum <= float(value) <= maximum:
            raise HTTPException(status_code=422, detail=f"Execution limit '{key}' must be between {minimum:g} and {maximum:g}")
        validated[key] = int(value) if key not in {"max_total_cost_usd", "per_agent_budget_usd"} else float(value)
    return validated


def _validate_dependency_dag(dependencies: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise HTTPException(status_code=422, detail=f"Dependency cycle detected at '{key}'")
        if key in visited:
            return
        visiting.add(key)
        for dependency in dependencies.get(key, []):
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in dependencies:
        visit(key)


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: uuid.UUID,
    req: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    plan = await db.scalar(
        select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.tenant_id == user.tenant_id)
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Task plan not found")
    if plan.status != TaskPlanStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Only plans awaiting approval can be edited")
    if req.goal is not None:
        plan.goal = req.goal
    if req.constraints is not None:
        plan.constraints = req.constraints
    if req.limits is not None:
        plan.limits = _validate_limits(req.limits)
    if req.steps is not None:
        _validate_step_updates(req.steps)
        existing = {
            step.id: step
            for step in (await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan.id))).all()
        }
        if set(existing) != {step.id for step in req.steps}:
            raise HTTPException(status_code=422, detail="Plan editing cannot add or remove steps; request a replan instead")
        submitted_keys = {existing[item.id].key for item in req.steps}
        dependency_map = {existing[item.id].key: item.depends_on for item in req.steps}
        _validate_dependency_dag(dependency_map)
        for item in req.steps:
            unknown = sorted(set(item.depends_on) - submitted_keys)
            if unknown:
                raise HTTPException(status_code=422, detail=f"Unknown dependencies for {item.title}: {', '.join(unknown)}")
            role_template = await db.scalar(
                select(RoleTemplateVersion).where(
                    RoleTemplateVersion.slug == item.role_slug,
                    RoleTemplateVersion.is_active.is_(True),
                    RoleTemplateVersion.is_executable.is_(True),
                    or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
                )
            )
            if role_template is None:
                raise HTTPException(status_code=422, detail=f"Role '{item.role_slug}' is not executable")
            step = existing[item.id]
            step.title = item.title
            step.instructions = item.instructions
            step.skill_slug = item.role_slug
            step.role_template_version_id = role_template.id
            step.depends_on = item.depends_on
            step.writes_code = item.writes_code
            step.nexus_phase = item.nexus_phase
            step.role = item.role
            step.parallel_group = item.parallel_group
            step.max_retries = item.max_retries
            step.acceptance_criteria = item.acceptance_criteria
            step.expected_artifacts = item.expected_artifacts
            step.tool_grants = item.tool_grants
            step.side_effect_class = item.side_effect_class
    await db.flush()
    return await _plan_response(db, plan)


@router.post("/plans/{plan_id}/decision")
async def decide_plan(plan_id: uuid.UUID, req: PlanDecision, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    plan = await db.scalar(select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.tenant_id == user.tenant_id))
    if plan is None or plan.status != TaskPlanStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Task plan is not awaiting approval")
    if not req.approved:
        plan.status = TaskPlanStatus.REJECTED
        return {"status": plan.status.value}
    plan.status, plan.approved_by, plan.approved_at = TaskPlanStatus.APPROVED, user.id, datetime.utcnow()
    workflow = Workflow(tenant_id=user.tenant_id, name=f"AI Team: {plan.goal[:100]}", description="Ad-hoc collaborative coding task", status=WorkflowStatus.ACTIVE, graph_config=plan.plan_data, created_by=user.id)
    db.add(workflow)
    await db.flush()
    plan_steps = list((await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan.id))).all())
    if len(plan_steps) > int((plan.limits or {}).get("max_agents", 8)):
        raise HTTPException(status_code=422, detail="The plan exceeds its maximum agent limit")
    preflight = await _repository_preflight(
        await _owned_repository(db, user, plan.repository_id),
        require_tool_runner=any(step.writes_code for step in plan_steps),
    )
    if not preflight["ok"]:
        raise HTTPException(status_code=422, detail={"message": "Repository preflight failed", "checks": preflight["checks"]})
    run = WorkflowRun(
        workflow_id=workflow.id,
        status=ExecutionStatus.QUEUED,
        run_kind="agentic_task",
        input_data={"plan_id": str(plan.id), "repository_id": str(plan.repository_id)},
    )
    db.add(run)
    await db.flush()
    db.add(
        ExecutionJob(
            run_id=run.id,
            plan_id=plan.id,
            job_type="agentic_task",
            status="queued",
            idempotency_key=f"plan:{plan.id}:run:{run.id}",
        )
    )
    await db.commit()
    return {"status": plan.status.value, "run_id": str(run.id), "workflow_id": str(workflow.id)}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    run = await _owned_run(db, user, run_id)
    scheduler: TaskScheduler = request.app.state.task_scheduler
    if run.status in {ExecutionStatus.PENDING, ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.BLOCKED, ExecutionStatus.AWAITING_INPUT}:
        run.status, run.completed_at = ExecutionStatus.CANCELLED, datetime.utcnow()
        jobs = (await db.scalars(select(ExecutionJob).where(ExecutionJob.run_id == run.id))).all()
        for job in jobs:
            if job.status in {"queued", "leased", "running"}:
                job.status = "cancelled"
        await scheduler.emit(db, run.id, "run_cancelled", "user", {"durable": True})
        await db.commit()
        return {"status": "cancelled"}
    return {"status": run.status.value}


@router.post("/runs/{run_id}/review")
async def review_run(
    run_id: uuid.UUID,
    req: RunReview,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)
    ),
):
    run = await _owned_run(db, user, run_id)
    if run.status not in {ExecutionStatus.NEEDS_REVIEW, ExecutionStatus.AWAITING_REVIEW}:
        raise HTTPException(status_code=409, detail="Run is not awaiting review")

    try:
        output = _apply_run_review(
            run,
            approved=req.approved,
            feedback=req.feedback,
            reviewer_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    scheduler: TaskScheduler = request.app.state.task_scheduler
    await scheduler.emit(
        db,
        run.id,
        "run_review_approved" if req.approved else "run_review_rejected",
        "reviewer",
        {"feedback": req.feedback.strip()},
    )
    if not req.approved:
        plan_id = (run.input_data or {}).get("plan_id")
        plan = await db.get(TaskPlan, uuid.UUID(plan_id)) if plan_id else None
        if plan is None:
            raise HTTPException(status_code=409, detail="Run has no resumable task plan")
        existing_steps = list((await db.scalars(select(TaskStep).where(TaskStep.plan_id == plan.id))).all())
        completed_keys = [step.key for step in existing_steps if step.status == ExecutionStatus.COMPLETED]
        role_source = next((step for step in reversed(existing_steps) if step.writes_code), existing_steps[-1] if existing_steps else None)
        if role_source is None:
            raise HTTPException(status_code=409, detail="Run has no workforce role for corrections")
        correction_index = sum(step.key.startswith("correction-") for step in existing_steps) + 1
        if correction_index > int((plan.limits or {}).get("max_replans", 2)):
            raise HTTPException(status_code=409, detail="The approved corrective-pass limit has been reached")
        if len(existing_steps) >= int((plan.limits or {}).get("max_agents", 8)):
            raise HTTPException(status_code=409, detail="The approved agent limit leaves no capacity for a corrective step")
        correction = TaskStep(
            plan_id=plan.id,
            key=f"correction-{correction_index}",
            title=f"Apply review corrections #{correction_index}",
            instructions=(
                "The user requested changes to the completed run. Inspect the existing integration branch, "
                "apply the feedback precisely, add or update tests, and report each verification command.\n\n"
                f"Review feedback:\n{req.feedback.strip()}"
            ),
            skill_slug=role_source.skill_slug,
            role_template_version_id=role_source.role_template_version_id,
            depends_on=completed_keys,
            writes_code=True,
            nexus_phase="build",
            role="correction engineer",
            max_retries=2,
            acceptance_criteria=f"The review feedback is resolved and relevant checks pass: {req.feedback.strip()}",
            expected_artifacts=["source changes", "verification results"],
            tool_grants=["repository_read", "repository_write", "command_execute"],
            side_effect_class="workspace",
        )
        db.add(correction)
        await db.flush()
        run.status = ExecutionStatus.QUEUED
        run.completed_at = None
        db.add(
            ExecutionJob(
                run_id=run.id,
                plan_id=plan.id,
                job_type="agentic_task",
                status="queued",
                idempotency_key=f"run:{run.id}:correction:{correction_index}",
            )
        )
        await scheduler.emit(
            db,
            run.id,
            "correction_queued",
            "orchestrator",
            {"step": correction.key, "feedback": req.feedback.strip()},
        )
    await db.commit()
    return {"status": run.status.value, "output": output}


@router.post("/runs/{run_id}/merge")
async def merge_run(
    run_id: uuid.UUID,
    req: RunMerge,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    run = await _owned_run(db, user, run_id)
    review = (run.output_data or {}).get("review", {})
    if run.status != ExecutionStatus.COMPLETED or review.get("decision") != "approved":
        raise HTTPException(status_code=409, detail="Approve the run before merging")
    if (run.output_data or {}).get("merge", {}).get("status") == "merged":
        return {"status": "merged", "output": run.output_data}

    plan_id = (run.input_data or {}).get("plan_id")
    plan = await db.get(TaskPlan, uuid.UUID(plan_id)) if plan_id else None
    repository = await db.get(Repository, plan.repository_id) if plan else None
    if plan is None or repository is None:
        raise HTTPException(status_code=409, detail="Run repository is unavailable")
    target = req.target_branch or repository.default_branch
    repo_path = Path(repository.local_path).resolve()
    status_code, dirty = await _git_capture(repo_path, "status", "--porcelain")
    branch_code, current_branch = await _git_capture(repo_path, "branch", "--show-current")
    base_code, current_base = await _git_capture(repo_path, "rev-parse", target)
    if status_code or branch_code or base_code:
        raise HTTPException(status_code=409, detail="Unable to inspect the target repository")
    if dirty:
        raise HTTPException(status_code=409, detail="Target repository has local changes; preserve them before merging")
    if current_branch != target:
        raise HTTPException(status_code=409, detail=f"Check out target branch '{target}' before merging")
    if current_base != req.expected_base_revision:
        raise HTTPException(status_code=409, detail={"message": "Target branch advanced since the run started", "current_revision": current_base})

    integration_path = Path(str((run.output_data or {}).get("integration_path", "")))
    integration_branch = str((run.output_data or {}).get("branch", ""))
    if not integration_path.is_dir() or not integration_branch:
        raise HTTPException(status_code=409, detail="Managed integration branch is unavailable")

    run.status = ExecutionStatus.MERGING
    await db.flush()
    fetch_code, fetch_output = await _git_capture(repo_path, "fetch", str(integration_path), integration_branch)
    if fetch_code:
        run.status = ExecutionStatus.COMPLETED
        raise HTTPException(status_code=409, detail=f"Unable to fetch the integration branch: {fetch_output[-1000:]}")
    merge_code, merge_output = await _git_capture(repo_path, "merge", "--ff-only", "FETCH_HEAD")
    if merge_code:
        run.status = ExecutionStatus.COMPLETED
        db.add(RunArtifact(run_id=run.id, kind="merge_conflict", name="Merge blocked", content=merge_output[-8000:], metadata_={"target": target}))
        await db.commit()
        raise HTTPException(status_code=409, detail="The target can no longer be fast-forwarded; the run branch was preserved")
    _, merged_revision = await _git_capture(repo_path, "rev-parse", "HEAD")
    output = dict(run.output_data or {})
    output["merge"] = {"status": "merged", "target_branch": target, "revision": merged_revision, "merged_at": datetime.now(UTC).replace(tzinfo=None).isoformat()}
    run.output_data = output
    run.status = ExecutionStatus.COMPLETED
    scheduler: TaskScheduler = request.app.state.task_scheduler
    await scheduler.emit(db, run.id, "run_merged", "user", output["merge"])
    await db.commit()
    return {"status": "merged", "output": output}


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: uuid.UUID, after: int = 0, request: Request = None, user: User = Depends(get_current_active_user)):  # type: ignore[assignment]
    from app.database import async_session_factory

    async def events() -> AsyncIterator[str]:
        sequence = after
        while True:
            pending_events: list[str] = []
            is_done = False
            async with async_session_factory() as db:
                run = await db.get(WorkflowRun, run_id)
                if run is None:
                    return
                owner_run = await db.scalar(
                    select(WorkflowRun).join(Workflow).where(
                        WorkflowRun.id == run_id, Workflow.tenant_id == user.tenant_id
                    )
                )
                if owner_run is None:
                    return

                rows = (await db.scalars(
                    select(RunEvent).where(
                        RunEvent.run_id == run_id, RunEvent.sequence > sequence
                    ).order_by(RunEvent.sequence)
                )).all()
                for row in rows:
                    sequence = row.sequence
                    pending_events.append(
                        f"id: {row.sequence}\nevent: {row.event_type}\ndata: {json.dumps({'sequence': row.sequence, 'actor': row.actor, 'payload': row.payload}, default=str)}\n\n"
                    )
                if run.status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.TIMEOUT, ExecutionStatus.NEEDS_REVIEW, ExecutionStatus.AWAITING_REVIEW}:
                    is_done = True

            for event in pending_events:
                yield event
            if is_done:
                return
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/runs/{run_id}/messages")
async def get_run_messages(run_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    await _owned_run(db, user, run_id)
    messages = (await db.scalars(
        select(AgentMessageRecord)
        .where(AgentMessageRecord.run_id == run_id)
        .order_by(AgentMessageRecord.created_at)
    )).all()
    return {
        "messages": [
            {
                "id": str(msg.id),
                "sender": msg.sender,
                "recipient": msg.recipient,
                "type": msg.message_type,
                "payload": msg.payload or {},
                "artifact_refs": msg.artifact_refs or [],
                "timestamp": msg.created_at.timestamp(),
                "reply_to": str(msg.reply_to) if msg.reply_to else None,
            }
            for msg in messages
        ]
    }


@router.post("/runs/{run_id}/delegations", status_code=status.HTTP_201_CREATED)
async def request_delegation(
    run_id: uuid.UUID,
    req: DelegationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    run = await _owned_run(db, user, run_id)
    if run.status not in {ExecutionStatus.RUNNING, ExecutionStatus.BLOCKED, ExecutionStatus.AWAITING_INPUT}:
        raise HTTPException(status_code=409, detail="Run is not accepting delegations")
    plan_id = (run.input_data or {}).get("plan_id")
    plan = await db.get(TaskPlan, uuid.UUID(plan_id)) if plan_id else None
    requester = await db.get(TaskStep, req.requester_step_id)
    if plan is None or requester is None or requester.plan_id != plan.id:
        raise HTTPException(status_code=404, detail="Requester step not found")
    limits = plan.limits or {}
    max_depth = int(limits.get("max_delegation_depth", 2))
    max_agents = int(limits.get("max_agents", 8))
    total_steps = await db.scalar(select(func.count()).select_from(TaskStep).where(TaskStep.plan_id == plan.id))
    role = await db.scalar(
        select(RoleTemplateVersion).where(
            RoleTemplateVersion.slug == req.role_slug,
            RoleTemplateVersion.is_active.is_(True),
            RoleTemplateVersion.is_executable.is_(True),
            or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
        )
    )
    delegation = DelegationRequest(
        run_id=run.id,
        requester_step_id=requester.id,
        requested_role_slug=req.role_slug,
        objective=req.objective,
        acceptance_criteria=req.acceptance_criteria,
    )
    db.add(delegation)
    if requester.delegation_depth + 1 > max_depth:
        delegation.status = "rejected"
        delegation.decision_reason = "Delegation depth limit reached"
    elif int(total_steps or 0) >= max_agents:
        delegation.status = "rejected"
        delegation.decision_reason = "Agent limit reached"
    elif role is None:
        delegation.status = "rejected"
        delegation.decision_reason = "Requested role is unavailable or not executable"
    else:
        child = TaskStep(
            plan_id=plan.id,
            key=f"delegated-{uuid.uuid4().hex[:8]}",
            title=f"Delegated: {req.objective[:120]}",
            instructions=req.objective,
            skill_slug=role.slug,
            role_template_version_id=role.id,
            depends_on=[requester.key],
            writes_code=False,
            nexus_phase=requester.nexus_phase,
            role=role.name,
            max_retries=2,
            acceptance_criteria=req.acceptance_criteria,
            expected_artifacts=["delegated findings"],
            tool_grants=role.compatible_tools or [],
            side_effect_class="read_only",
            delegation_depth=requester.delegation_depth + 1,
        )
        db.add(child)
        await db.flush()
        delegation.status = "approved"
        delegation.child_step_id = child.id
        delegation.decision_reason = "Within role, depth, and workforce limits"
    delegation.decided_at = datetime.utcnow()
    await db.flush()
    scheduler: TaskScheduler = request.app.state.task_scheduler
    await scheduler.emit(
        db,
        run.id,
        "delegation_approved" if delegation.status == "approved" else "delegation_rejected",
        "orchestrator",
        {"request_id": str(delegation.id), "role": req.role_slug, "reason": delegation.decision_reason, "child_step_id": str(delegation.child_step_id) if delegation.child_step_id else None},
    )
    await db.commit()
    return {"id": str(delegation.id), "status": delegation.status, "reason": delegation.decision_reason, "child_step_id": str(delegation.child_step_id) if delegation.child_step_id else None}


@router.get("/runs/{run_id}/artifacts")
async def list_artifacts(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    await _owned_run(db, user, run_id)
    artifacts = (await db.scalars(select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at))).all()
    return [{"id": str(artifact.id), "kind": artifact.kind, "name": artifact.name, "content": artifact.content, "metadata": artifact.metadata_ or {}} for artifact in artifacts]


@router.post("/workflow-graphs/validate")
async def validate_workflow(req: WorkflowValidate, user: User = Depends(get_current_active_user)):
    errors = validate_graph(req.graph_config)
    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True, "steps": [step.__dict__ for step in compile_graph(req.graph_config)]}


@router.get("/runs")
async def list_task_runs(limit: int = 30, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    rows = (await db.execute(
        select(WorkflowRun, Workflow).join(Workflow).where(Workflow.tenant_id == user.tenant_id).order_by(WorkflowRun.created_at.desc()).limit(min(limit, 100))
    )).all()
    return [{"id": str(run.id), "workflow": workflow.name, "status": run.status.value, "tokens_used": run.tokens_used, "cost_usd": run.cost_usd, "started_at": run.started_at.isoformat() if run.started_at else None, "completed_at": run.completed_at.isoformat() if run.completed_at else None, "created_at": run.created_at.isoformat(), "error": run.error, "output": run.output_data} for run, workflow in rows]


@router.get("/runs/{run_id}/detail")
async def get_run_detail(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    run = await _owned_run(db, user, run_id)
    plan_data = run.input_data or {}
    plan = await db.get(TaskPlan, uuid.UUID(plan_data["plan_id"])) if plan_data.get("plan_id") else None
    events = (await db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence))).all()
    agents = (await db.scalars(select(AgentInstance).where(AgentInstance.run_id == run_id).order_by(AgentInstance.created_at))).all()
    return {
        "id": str(run.id),
        "trace_id": run.trace_id,
        "run_kind": run.run_kind,
        "status": run.status.value,
        "error": run.error,
        "output": run.output_data,
        "plan": await _plan_response(db, plan) if plan else None,
        "agents": [
            {"id": str(agent.id), "task_step_id": str(agent.task_step_id) if agent.task_step_id else None, "name": agent.name, "role_slug": agent.role_slug, "status": agent.status.value, "model": agent.model_snapshot, "tool_grants": agent.tool_grants or []}
            for agent in agents
        ],
        "events": [{"sequence": event.sequence, "type": event.event_type, "actor": event.actor, "payload": event.payload, "trace_id": event.trace_id or run.trace_id, "agent_instance_id": str(event.agent_instance_id) if event.agent_instance_id else None, "task_step_id": str(event.task_step_id) if event.task_step_id else None, "created_at": event.created_at.isoformat()} for event in events],
    }


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    runs = (await db.execute(select(WorkflowRun).join(Workflow).where(Workflow.tenant_id == user.tenant_id))).scalars().all()
    total = len(runs)
    active = sum(run.status in {ExecutionStatus.PLANNING, ExecutionStatus.PENDING, ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.BLOCKED, ExecutionStatus.AWAITING_INPUT, ExecutionStatus.AWAITING_APPROVAL, ExecutionStatus.MERGING} for run in runs)
    completed = sum(run.status in {ExecutionStatus.COMPLETED, ExecutionStatus.NEEDS_REVIEW, ExecutionStatus.AWAITING_REVIEW} for run in runs)
    return {"total_runs": total, "active_runs": active, "completed_runs": completed, "success_rate": round(completed / total * 100, 1) if total else 0, "total_cost_usd": round(sum(run.cost_usd for run in runs), 4)}
