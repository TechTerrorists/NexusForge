from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, require_role
from app.database import get_db
from app.models import AgentInstance, RoleTemplateVersion, SkillDefinitionVersion, User, UserRole
from packages.task_runtime.skill_importer import import_skills


router = APIRouter(prefix="/api/v1/workforce", tags=["workforce"])


def _role_response(role: RoleTemplateVersion) -> dict:
    return {
        "id": str(role.id),
        "slug": role.slug,
        "name": role.name,
        "description": role.description,
        "division": role.division,
        "version": role.version,
        "capabilities": role.capabilities or [],
        "compatible_tools": role.compatible_tools or [],
        "source_path": role.source_path,
        "is_executable": role.is_executable,
        "is_active": role.is_active,
        "created_at": role.created_at.isoformat(),
    }


@router.get("/roles")
async def list_roles(
    search: str = "",
    division: str | None = None,
    executable_only: bool = False,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = select(RoleTemplateVersion).where(
        RoleTemplateVersion.is_active.is_(True),
        or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
    )
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                RoleTemplateVersion.name.ilike(pattern),
                RoleTemplateVersion.description.ilike(pattern),
                RoleTemplateVersion.slug.ilike(pattern),
            )
        )
    if division:
        query = query.where(RoleTemplateVersion.division == division)
    if executable_only:
        query = query.where(RoleTemplateVersion.is_executable.is_(True))
    rows = (await db.scalars(query.order_by(RoleTemplateVersion.division, RoleTemplateVersion.name).offset(offset).limit(limit))).all()
    total = await db.scalar(
        select(func.count()).select_from(RoleTemplateVersion).where(
            RoleTemplateVersion.is_active.is_(True),
            or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
        )
    )
    return {"items": [_role_response(row) for row in rows], "total": int(total or 0)}


@router.get("/roles/{role_id}")
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    role = await db.scalar(
        select(RoleTemplateVersion).where(
            RoleTemplateVersion.id == role_id,
            or_(RoleTemplateVersion.tenant_id.is_(None), RoleTemplateVersion.tenant_id == user.tenant_id),
        )
    )
    if role is None:
        raise HTTPException(status_code=404, detail="Role template not found")
    response = _role_response(role)
    response["prompt"] = role.prompt
    return response


@router.get("/agents")
async def list_agent_instances(
    run_id: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    from app.models import Workflow, WorkflowRun

    query = (
        select(AgentInstance)
        .join(WorkflowRun, WorkflowRun.id == AgentInstance.run_id)
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .where(Workflow.tenant_id == user.tenant_id)
    )
    if run_id:
        query = query.where(AgentInstance.run_id == run_id)
    agents = (await db.scalars(query.order_by(AgentInstance.created_at.desc()).limit(limit))).all()
    return [
        {
            "id": str(agent.id),
            "run_id": str(agent.run_id),
            "task_step_id": str(agent.task_step_id) if agent.task_step_id else None,
            "name": agent.name,
            "role_slug": agent.role_slug,
            "status": agent.status.value,
            "model": agent.model_snapshot,
            "tool_grants": agent.tool_grants or [],
            "budget_usd": agent.budget_usd,
            "started_at": agent.started_at.isoformat() if agent.started_at else None,
            "completed_at": agent.completed_at.isoformat() if agent.completed_at else None,
        }
        for agent in agents
    ]


@router.get("/skills")
async def list_skill_definitions(
    search: str = "",
    limit: int = Query(100, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = select(SkillDefinitionVersion).where(
        SkillDefinitionVersion.is_active.is_(True),
        or_(SkillDefinitionVersion.tenant_id.is_(None), SkillDefinitionVersion.tenant_id == user.tenant_id),
    )
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(SkillDefinitionVersion.name.ilike(pattern), SkillDefinitionVersion.description.ilike(pattern)))
    skills = (await db.scalars(query.order_by(SkillDefinitionVersion.name).limit(limit))).all()
    return [{"id": str(skill.id), "slug": skill.slug, "name": skill.name, "description": skill.description, "version": skill.version, "required_capabilities": skill.required_capabilities or [], "source_path": skill.source_path} for skill in skills]


@router.post("/import")
async def import_workforce(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER)),
):
    from app.database import async_session_factory

    source = Path(os.getenv("NEXUSFORGE_AGENCY_AGENTS_PATH", "/opt/agency-agents"))
    if not source.is_dir():
        raise HTTPException(status_code=422, detail="Agency Agents directory is unavailable")
    if async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database is not initialized")
    return await import_skills(async_session_factory, source)
