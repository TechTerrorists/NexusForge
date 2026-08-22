from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Any
from uuid import UUID, uuid4
from datetime import datetime

from ..database import get_db
from ..models import Workflow, WorkflowRun, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    domain: str = "custom"
    graph_json: dict = {}


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    domain: str | None = None
    graph_json: dict | None = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    version: int
    graph_json: dict
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    current_node: str | None
    total_cost_cents: int
    created_at: str


@router.post("/", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    req: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    from packages.memory.durable_facts import derive_workflow_status

    wf = Workflow(
        id=uuid4(), name=req.name, description=req.description, domain=req.domain,
        version=1, manifest_json={}, graph_json=req.graph_json, tenant_id=user.tenant_id,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description, domain=wf.domain,
        version=wf.version, graph_json=wf.graph_json,
        created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(
    domain: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    q = select(Workflow).where(Workflow.tenant_id == user.tenant_id)
    if domain:
        q = q.where(Workflow.domain == domain)
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    workflows = result.scalars().all()
    return [
        WorkflowResponse(
            id=str(w.id), name=w.name, description=w.description, domain=w.domain,
            version=w.version, graph_json=w.graph_json,
            created_at=w.created_at.isoformat(), updated_at=w.updated_at.isoformat(),
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
        id=str(wf.id), name=wf.name, description=wf.description, domain=wf.domain,
        version=wf.version, graph_json=wf.graph_json,
        created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str, req: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
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
    if req.domain is not None:
        wf.domain = req.domain
    if req.graph_json is not None:
        wf.graph_json = req.graph_json
    wf.version += 1
    wf.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(wf)
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description, domain=wf.domain,
        version=wf.version, graph_json=wf.graph_json,
        created_at=wf.created_at.isoformat(), updated_at=wf.updated_at.isoformat(),
    )


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
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
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = WorkflowRun(
        id=uuid4(), workflow_id=wf.id, activity_state="planning",
        is_terminated=False, current_node=None, last_heartbeat=datetime.utcnow(),
        total_cost_cents=0, state_json={"messages": []}, checkpoint_json=None,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return RunResponse(
        id=str(run.id), workflow_id=str(run.workflow_id), status="planning",
        current_node=None, total_cost_cents=0, created_at=run.created_at.isoformat(),
    )


@router.get("/{workflow_id}/runs", response_model=list[RunResponse])
async def list_runs(
    workflow_id: str, limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    from packages.memory.durable_facts import derive_workflow_status

    result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id).order_by(WorkflowRun.created_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [
        RunResponse(
            id=str(r.id), workflow_id=str(r.workflow_id),
            status=derive_workflow_status(r), current_node=r.current_node,
            total_cost_cents=r.total_cost_cents, created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    from packages.memory.durable_facts import derive_workflow_status
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(
        id=str(run.id), workflow_id=str(run.workflow_id),
        status=derive_workflow_status(run), current_node=run.current_node,
        total_cost_cents=run.total_cost_cents, created_at=run.created_at.isoformat(),
    )


@router.post("/runs/{run_id}/approve")
async def approve_run(
    run_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.activity_state = "executing"
    run.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "approved", "run_id": run_id}


@router.post("/runs/{run_id}/reject")
async def reject_run(
    run_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.is_terminated = True
    run.activity_state = "completed"
    run.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "rejected", "run_id": run_id}
