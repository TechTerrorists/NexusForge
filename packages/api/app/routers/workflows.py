from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, require_role
from app.config import get_settings
from app.database import get_db
from app.models import (
    ExecutionJob,
    ExecutionStatus,
    User,
    UserRole,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTrigger,
    WorkflowVersion,
)
from packages.task_runtime.workflow_graph import compile_graph, validate_graph
from packages.task_runtime.cron import next_cron_fire

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    graph_config: dict = Field(default_factory=dict)
    input_schema: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] | None = None


class VersionCreate(BaseModel):
    graph_config: dict
    input_schema: dict = Field(default_factory=dict)


class TriggerCreate(BaseModel):
    workflow_version_id: uuid.UUID
    trigger_type: str
    config: dict = Field(default_factory=dict)


class RunCreate(BaseModel):
    workflow_version_id: uuid.UUID | None = None
    payload: dict = Field(default_factory=dict)
    test_mode: bool = False
    idempotency_key: str | None = Field(default=None, max_length=255)


class ApprovalDecision(BaseModel):
    approve: bool
    feedback: str = Field(default="", max_length=4000)


def _workflow_payload(workflow: Workflow) -> dict:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description or "",
        "status": workflow.status.value,
        "version": workflow.version,
        "graph_config": workflow.graph_config or {},
        "tags": workflow.tags or [],
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


def _run_payload(run: WorkflowRun) -> dict:
    return {
        "id": str(run.id),
        "workflow_id": str(run.workflow_id),
        "workflow_version_id": str(run.workflow_version_id) if run.workflow_version_id else None,
        "trace_id": run.trace_id,
        "run_kind": run.run_kind,
        "status": run.status.value,
        "tokens_used": run.tokens_used,
        "cost_usd": run.cost_usd,
        "output": run.output_data,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat(),
    }


async def _owned_workflow(db: AsyncSession, user: User, workflow_id: uuid.UUID) -> Workflow:
    workflow = await db.scalar(select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == user.tenant_id))
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


async def _create_version(db: AsyncSession, workflow: Workflow, user_id: uuid.UUID, graph: dict, input_schema: dict) -> WorkflowVersion:
    errors = validate_graph(graph)
    number = int(await db.scalar(select(func.max(WorkflowVersion.version)).where(WorkflowVersion.workflow_id == workflow.id)) or 0) + 1
    compiled = []
    if not errors:
        compiled = [step.__dict__ for step in compile_graph(graph)]
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=number,
        status="validated" if not errors else "draft",
        graph_config=graph,
        input_schema=input_schema,
        compiled_plan={"steps": compiled, "validation_errors": errors},
        created_by=user_id,
    )
    db.add(version)
    workflow.version = number
    workflow.graph_config = graph
    return version


async def _queue_run(
    db: AsyncSession,
    workflow: Workflow,
    version: WorkflowVersion,
    request: RunCreate,
    *,
    trigger_id: uuid.UUID | None = None,
) -> WorkflowRun:
    if version.status != "active" and not request.test_mode:
        raise HTTPException(status_code=409, detail="Activate this workflow version before running it")
    _validate_input_payload(version.input_schema or {}, request.payload)
    if request.idempotency_key:
        existing = await db.scalar(select(WorkflowRun).where(WorkflowRun.workflow_id == workflow.id, WorkflowRun.idempotency_key == request.idempotency_key))
        if existing:
            return existing
    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        run_kind="deterministic_workflow",
        idempotency_key=request.idempotency_key,
        status=ExecutionStatus.QUEUED,
        input_data={"payload": request.payload, "test_mode": request.test_mode, "trigger_id": str(trigger_id) if trigger_id else None},
        tokens_used=0,
        cost_usd=0,
    )
    db.add(run)
    await db.flush()
    db.add(ExecutionJob(run_id=run.id, job_type="deterministic_workflow", status="queued", idempotency_key=f"workflow-run:{run.id}"))
    return run


def _validate_input_payload(schema: dict, payload: dict) -> None:
    if not schema:
        return
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [str(key) for key in required if key not in payload]
        if missing:
            raise HTTPException(status_code=422, detail=f"Workflow input is missing required fields: {', '.join(missing)}")
    properties = schema.get("properties", {})
    type_map = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict, "array": list}
    if isinstance(properties, dict):
        for key, definition in properties.items():
            if key not in payload or not isinstance(definition, dict) or "type" not in definition:
                continue
            expected = type_map.get(str(definition["type"]))
            if expected and (not isinstance(payload[key], expected) or definition["type"] in {"number", "integer"} and isinstance(payload[key], bool)):
                raise HTTPException(status_code=422, detail=f"Workflow input field '{key}' must be {definition['type']}")


@router.post("", status_code=201)
@router.post("/", status_code=201, include_in_schema=False)
async def create_workflow(req: WorkflowCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = Workflow(name=req.name, description=req.description, status=WorkflowStatus.DRAFT, graph_config=req.graph_config, tags=req.tags, tenant_id=user.tenant_id, created_by=user.id)
    db.add(workflow)
    await db.flush()
    if req.graph_config:
        await _create_version(db, workflow, user.id, req.graph_config, req.input_schema)
    await db.commit()
    await db.refresh(workflow)
    return _workflow_payload(workflow)


@router.get("")
@router.get("/", include_in_schema=False)
async def list_workflows(status: str | None = None, limit: int = Query(50, le=200), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    query = select(Workflow).where(Workflow.tenant_id == user.tenant_id)
    if status:
        query = query.where(Workflow.status == status)
    workflows = (await db.scalars(query.order_by(Workflow.updated_at.desc()).offset(offset).limit(limit))).all()
    return [_workflow_payload(workflow) for workflow in workflows]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    return _workflow_payload(await _owned_workflow(db, user, workflow_id))


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: uuid.UUID, req: WorkflowUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    for field in ("name", "description", "tags"):
        value = getattr(req, field)
        if value is not None:
            setattr(workflow, field, value)
    workflow.updated_at = datetime.utcnow()
    await db.commit()
    return _workflow_payload(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def archive_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    workflow.status = WorkflowStatus.ARCHIVED
    await db.commit()


@router.post("/{workflow_id}/versions", status_code=201)
async def create_version(workflow_id: uuid.UUID, req: VersionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    version = await _create_version(db, workflow, user.id, req.graph_config, req.input_schema)
    await db.commit()
    return {"id": str(version.id), "version": version.version, "status": version.status, "graph_config": version.graph_config, "input_schema": version.input_schema, "validation_errors": (version.compiled_plan or {}).get("validation_errors", [])}


@router.get("/{workflow_id}/versions")
async def list_versions(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    await _owned_workflow(db, user, workflow_id)
    versions = (await db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id).order_by(WorkflowVersion.version.desc()))).all()
    return [{"id": str(item.id), "version": item.version, "status": item.status, "graph_config": item.graph_config, "input_schema": item.input_schema, "validation_errors": (item.compiled_plan or {}).get("validation_errors", []), "created_at": item.created_at.isoformat()} for item in versions]


@router.post("/{workflow_id}/versions/{version_id}/activate")
async def activate_version(workflow_id: uuid.UUID, version_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    version = await db.get(WorkflowVersion, version_id)
    if not version or version.workflow_id != workflow.id:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    errors = validate_graph(version.graph_config or {})
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Workflow validation failed", "errors": errors})
    for item in (await db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.status == "active"))).all():
        item.status = "validated"
    version.status = "active"
    workflow.status = WorkflowStatus.ACTIVE
    workflow.graph_config = version.graph_config
    await db.commit()
    return {"status": "active", "version": version.version}


@router.post("/{workflow_id}/triggers", status_code=201)
async def create_trigger(workflow_id: uuid.UUID, req: TriggerCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    version = await db.get(WorkflowVersion, req.workflow_version_id)
    if not version or version.workflow_id != workflow.id or version.status != "active":
        raise HTTPException(status_code=409, detail="Trigger requires an active workflow version")
    if req.trigger_type not in {"manual", "cron", "webhook"}:
        raise HTTPException(status_code=422, detail="Trigger type must be manual, cron, or webhook")
    if req.trigger_type == "cron" and (not req.config.get("cron") or not req.config.get("timezone")):
        raise HTTPException(status_code=422, detail="Cron triggers require cron and timezone")
    if req.trigger_type == "cron" and req.config.get("misfire_policy", "skip") not in {"skip", "latest", "catch_up"}:
        raise HTTPException(status_code=422, detail="Cron misfire_policy must be skip, latest, or catch_up")
    next_fire_at = None
    if req.trigger_type == "cron":
        try:
            next_fire_at = next_cron_fire(str(req.config["cron"]), str(req.config["timezone"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    trigger_config = dict(req.config)
    if req.trigger_type == "cron":
        trigger_config.setdefault("misfire_policy", "skip")
    trigger = WorkflowTrigger(workflow_id=workflow.id, workflow_version_id=version.id, trigger_type=req.trigger_type, config=trigger_config, is_active=True, next_fire_at=next_fire_at)
    db.add(trigger)
    await db.flush()
    secret = _trigger_secret(trigger.id) if req.trigger_type == "webhook" else None
    trigger.secret_hash = hashlib.sha256(secret.encode()).hexdigest() if secret else None
    await db.commit()
    return {"id": str(trigger.id), "type": trigger.trigger_type, "config": trigger.config, "active": trigger.is_active, "webhook_secret": secret}


@router.get("/{workflow_id}/triggers")
async def list_triggers(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    workflow = await _owned_workflow(db, user, workflow_id)
    items = (await db.scalars(select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == workflow.id))).all()
    return [{"id": str(item.id), "type": item.trigger_type, "config": item.config, "active": item.is_active, "next_fire_at": item.next_fire_at.isoformat() if item.next_fire_at else None} for item in items]


@router.post("/{workflow_id}/runs", status_code=201)
async def start_run(workflow_id: uuid.UUID, req: RunCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    workflow = await _owned_workflow(db, user, workflow_id)
    if req.workflow_version_id:
        version = await db.get(WorkflowVersion, req.workflow_version_id)
    else:
        version = await db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.status == "active").order_by(WorkflowVersion.version.desc()))
    if not version or version.workflow_id != workflow.id:
        raise HTTPException(status_code=409, detail="No runnable workflow version exists")
    run = await _queue_run(db, workflow, version, req)
    await db.commit()
    return _run_payload(run)


@router.get("/{workflow_id}/runs")
async def list_runs(workflow_id: uuid.UUID, limit: int = Query(20, le=100), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    workflow = await _owned_workflow(db, user, workflow_id)
    runs = (await db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == workflow.id).order_by(WorkflowRun.created_at.desc()).limit(limit))).all()
    return [_run_payload(run) for run in runs]


@router.post("/runs/{run_id}/nodes/{node_key}/approval")
async def decide_node(run_id: uuid.UUID, node_key: str, req: ApprovalDecision, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))):
    run = await db.get(WorkflowRun, run_id)
    workflow = await db.get(Workflow, run.workflow_id) if run else None
    if not run or not workflow or workflow.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    node = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run.id, WorkflowNodeRun.node_key == node_key))
    if not node or node.status != ExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Node is not awaiting approval")
    if not req.approve:
        node.status, node.error, node.completed_at = ExecutionStatus.FAILED, req.feedback or "Approval rejected", datetime.utcnow()
        run.status, run.error, run.completed_at = ExecutionStatus.CANCELLED, node.error, datetime.utcnow()
        await db.commit()
        return {"status": "cancelled"}
    node.status, node.output_data, node.completed_at = ExecutionStatus.COMPLETED, {"approved": True, "feedback": req.feedback, "approved_by": str(user.id)}, datetime.utcnow()
    run.status = ExecutionStatus.QUEUED
    db.add(ExecutionJob(run_id=run.id, job_type="deterministic_workflow", status="queued", idempotency_key=f"workflow-run:{run.id}:resume:{node_key}"))
    await db.commit()
    return {"status": "queued"}


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    run = await db.get(WorkflowRun, run_id)
    workflow = await db.get(Workflow, run.workflow_id) if run else None
    if not run or not workflow or workflow.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    payload = _run_payload(run)
    payload["nodes"] = [{"key": item.node_key, "type": item.node_type, "status": item.status.value, "input": item.input_data, "output": item.output_data, "error": item.error} for item in (await db.scalars(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run.id).order_by(WorkflowNodeRun.created_at))).all()]
    return payload


@router.post("/hooks/{trigger_id}", status_code=202)
async def invoke_webhook(trigger_id: uuid.UUID, request: Request, x_nexusforge_signature: str = Header(default=""), x_idempotency_key: str = Header(default=""), db: AsyncSession = Depends(get_db)):
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds the 1 MB limit")
    trigger = await db.get(WorkflowTrigger, trigger_id)
    if not trigger or trigger.trigger_type != "webhook" or not trigger.is_active:
        raise HTTPException(status_code=404, detail="Webhook trigger not found")
    expected = hmac.new(_trigger_secret(trigger.id).encode(), body, hashlib.sha256).hexdigest()
    supplied = x_nexusforge_signature.removeprefix("sha256=")
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    workflow = await db.get(Workflow, trigger.workflow_id)
    version = await db.get(WorkflowVersion, trigger.workflow_version_id)
    assert workflow is not None and version is not None
    try:
        payload = await request.json()
    except ValueError:
        payload = {"raw": body.decode("utf-8", "replace")}
    key = x_idempotency_key or hashlib.sha256(body).hexdigest()
    run = await _queue_run(db, workflow, version, RunCreate(payload=payload, idempotency_key=f"webhook:{trigger.id}:{key}"), trigger_id=trigger.id)
    await db.commit()
    return {"run_id": str(run.id), "status": run.status.value}


def _trigger_secret(trigger_id: uuid.UUID) -> str:
    key = get_settings().auth.secret_key.get_secret_value().encode()
    return hmac.new(key, f"nexusforge-webhook:{trigger_id}".encode(), hashlib.sha256).hexdigest()
