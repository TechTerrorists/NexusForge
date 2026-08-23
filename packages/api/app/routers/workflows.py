from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from ..database import get_db
from ..models import Workflow, WorkflowRun, WorkflowStatus, ExecutionStatus, UserRole, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    graph_config: dict = {}
    config: dict = {}
    tags: list[str] = []


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    graph_config: dict | None = None
    config: dict | None = None
    tags: list[str] | None = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    version: int
    graph_config: dict
    tags: list
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    tokens_used: int
    cost_usd: float
    started_at: str | None
    completed_at: str | None
    created_at: str


@router.post("/", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    req: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    wf = Workflow(
        id=uuid4(),
        name=req.name,
        description=req.description,
        status=WorkflowStatus.DRAFT,
        graph_config=req.graph_config,
        config=req.config,
        tags=req.tags,
        tenant_id=user.tenant_id,
        created_by=user.id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description,
        status=wf.status.value, version=wf.version, graph_config=wf.graph_config or {},
        tags=wf.tags or [], created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    q = select(Workflow).where(Workflow.tenant_id == user.tenant_id)
    if status:
        q = q.where(Workflow.status == status)
    q = q.order_by(Workflow.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    workflows = result.scalars().all()
    return [
        WorkflowResponse(
            id=str(w.id), name=w.name, description=w.description,
            status=w.status.value, version=w.version, graph_config=w.graph_config or {},
            tags=w.tags or [], created_at=w.created_at.isoformat(), updated_at=w.updated_at.isoformat(),
        )
        for w in workflows
    ]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description,
        status=wf.status.value, version=wf.version, graph_config=wf.graph_config or {},
        tags=wf.tags or [], created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str, req: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if req.name is not None:
        wf.name = req.name
    if req.description is not None:
        wf.description = req.description
    if req.status is not None:
        wf.status = WorkflowStatus(req.status)
    if req.graph_config is not None:
        wf.graph_config = req.graph_config
    if req.config is not None:
        wf.config = req.config
    if req.tags is not None:
        wf.tags = req.tags
    wf.version += 1
    wf.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(wf)
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description,
        status=wf.status.value, version=wf.version, graph_config=wf.graph_config or {},
        tags=wf.tags or [], created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(wf)
    await db.commit()


@router.post("/{workflow_id}/runs", response_model=RunResponse, status_code=201)
async def start_run(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = WorkflowRun(
        id=uuid4(),
        workflow_id=wf.id,
        status=ExecutionStatus.PENDING,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return RunResponse(
        id=str(run.id), workflow_id=str(run.workflow_id), status=run.status.value,
        tokens_used=run.tokens_used, cost_usd=run.cost_usd,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat(),
    )


@router.get("/{workflow_id}/runs", response_model=list[RunResponse])
async def list_runs(
    workflow_id: str, limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id).order_by(WorkflowRun.created_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [
        RunResponse(
            id=str(r.id), workflow_id=str(r.workflow_id), status=r.status.value,
            tokens_used=r.tokens_used, cost_usd=r.cost_usd,
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(
        id=str(run.id), workflow_id=str(run.workflow_id), status=run.status.value,
        tokens_used=run.tokens_used, cost_usd=run.cost_usd,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat(),
    )
