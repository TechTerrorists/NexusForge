from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, require_role
from app.database import get_db
from app.llm_runtime import get_tenant_llm_config
from app.models import (
    ChatMessage, ChatSession, ExecutionStatus, Repository, RunArtifact, RunEvent,
    SkillVersion, TaskPlan, TaskPlanStatus, TaskStep, User, UserRole, Workflow, WorkflowRun, WorkflowStatus,
)
from packages.task_runtime.planner import PlannedStep, llm_create_plan
from packages.task_runtime.scheduler import TaskScheduler
from packages.task_runtime.workflow_graph import GraphValidationError, compile_graph, validate_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["collaborative tasks"])


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    local_path: str
    default_branch: str = "main"
    allowed_commands: list[str] = Field(default_factory=list)


class SessionCreate(BaseModel):
    repository_id: uuid.UUID | None = None
    title: str = "New software task"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class PlanDecision(BaseModel):
    approved: bool


class RunReview(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=4000)


class WorkflowValidate(BaseModel):
    graph_config: dict


def _repository_response(repository: Repository) -> dict:
    return {"id": str(repository.id), "name": repository.name, "local_path": repository.local_path, "default_branch": repository.default_branch, "allowed_commands": repository.allowed_commands or []}


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
    run.status = ExecutionStatus.COMPLETED if approved else ExecutionStatus.CANCELLED
    return output


@router.post("/repositories", status_code=status.HTTP_201_CREATED)
async def register_repository(req: RepositoryCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    path = Path(req.local_path).expanduser().resolve()
    if not path.is_dir() or not (path / ".git").exists():
        raise HTTPException(status_code=422, detail="local_path must be an existing Git checkout")
    repository = Repository(tenant_id=user.tenant_id, name=req.name, local_path=str(path), default_branch=req.default_branch, allowed_commands=req.allowed_commands)
    db.add(repository)
    await db.flush()
    return _repository_response(repository)


@router.get("/repositories")
async def list_repositories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    repositories = (await db.scalars(select(Repository).where(Repository.tenant_id == user.tenant_id, Repository.is_active.is_(True)).order_by(Repository.name))).all()
    return [_repository_response(repository) for repository in repositories]


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

    skills = list((await db.scalars(
        select(SkillVersion)
        .where(SkillVersion.is_active.is_(True))
        .order_by(SkillVersion.slug, SkillVersion.version.desc())
    )).all())

    llm_config = await get_tenant_llm_config(db, user.tenant_id)
    steps = await llm_create_plan(
        req.content,
        skills,
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
        plan_data={"version": 2, "planner": "llm"},
        estimated_cost_usd=0.0, created_by=user.id,
    )
    db.add(plan)
    await db.flush()

    skill_lookup = {skill.slug: skill for skill in skills}
    for item in steps:
        skill = skill_lookup.get(item.skill_slug)
        db.add(TaskStep(
            plan_id=plan.id, key=item.key, title=item.title,
            instructions=item.instructions, skill_slug=item.skill_slug,
            skill_version_id=skill.id if skill else None,
            depends_on=item.depends_on, writes_code=item.writes_code,
            nexus_phase=item.nexus_phase, role=item.role,
            parallel_group=item.parallel_group, max_retries=item.max_retries,
            acceptance_criteria=item.acceptance_criteria,
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
        "steps": [
            {
                "id": str(step.id),
                "key": step.key,
                "title": step.title,
                "skill": step.skill_slug,
                "depends_on": step.depends_on or [],
                "writes_code": step.writes_code,
                "status": step.status.value,
                "nexus_phase": getattr(step, "nexus_phase", "build"),
                "role": getattr(step, "role", ""),
                "parallel_group": getattr(step, "parallel_group", None),
                "acceptance_criteria": getattr(step, "acceptance_criteria", ""),
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
    run = WorkflowRun(workflow_id=workflow.id, status=ExecutionStatus.PENDING, input_data={"plan_id": str(plan.id), "repository_id": str(plan.repository_id)})
    db.add(run)
    await db.flush()
    await db.commit()
    scheduler: TaskScheduler = request.app.state.task_scheduler
    if not hasattr(request.app.state, '_scheduler_tasks'):
        request.app.state._scheduler_tasks: set[asyncio.Task] = set()
    task = asyncio.create_task(scheduler.execute(str(plan.id), str(run.id)))
    request.app.state._scheduler_tasks.add(task)
    task.add_done_callback(request.app.state._scheduler_tasks.discard)
    return {"status": plan.status.value, "run_id": str(run.id), "workflow_id": str(workflow.id)}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    run = await _owned_run(db, user, run_id)
    scheduler: TaskScheduler = request.app.state.task_scheduler
    if run.status == ExecutionStatus.PENDING:
        run.status, run.completed_at = ExecutionStatus.CANCELLED, datetime.utcnow()
        await scheduler.emit(db, run.id, "run_cancelled", "user", {"before_start": True})
        await db.commit()
        return {"status": "cancelled"}
    scheduler.cancel(str(run_id))
    return {"status": "cancellation_requested"}


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
    if run.status != ExecutionStatus.NEEDS_REVIEW:
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
    await db.commit()
    return {"status": run.status.value, "output": output}


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
                if run.status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.NEEDS_REVIEW}:
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
    message_bus = getattr(request.app.state, "message_bus", None)
    if message_bus is None:
        return {"messages": []}
    try:
        messages = await message_bus.get_run_log(str(run_id))
        return {
            "messages": [
                {
                    "id": msg.id,
                    "sender": msg.sender,
                    "recipient": msg.recipient,
                    "type": msg.type,
                    "payload": msg.payload,
                    "artifact_refs": msg.artifact_refs,
                    "timestamp": msg.timestamp,
                    "reply_to": msg.reply_to,
                }
                for msg in messages
            ]
        }
    except Exception:
        return {"messages": []}


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
    return {"id": str(run.id), "status": run.status.value, "error": run.error, "output": run.output_data, "plan": await _plan_response(db, plan) if plan else None, "events": [{"sequence": event.sequence, "type": event.event_type, "actor": event.actor, "payload": event.payload, "created_at": event.created_at.isoformat()} for event in events]}


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    runs = (await db.execute(select(WorkflowRun).join(Workflow).where(Workflow.tenant_id == user.tenant_id))).scalars().all()
    total = len(runs)
    active = sum(run.status in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.AWAITING_APPROVAL} for run in runs)
    completed = sum(run.status in {ExecutionStatus.COMPLETED, ExecutionStatus.NEEDS_REVIEW} for run in runs)
    return {"total_runs": total, "active_runs": active, "completed_runs": completed, "success_rate": round(completed / total * 100, 1) if total else 0, "total_cost_usd": round(sum(run.cost_usd for run in runs), 4)}
