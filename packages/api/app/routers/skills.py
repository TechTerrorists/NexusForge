from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime

from ..database import get_db
from ..models import Skill, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    protocol_json: dict = {}
    source_type: str = "file"
    source_content: str = ""


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    source_type: str
    created_at: str


@router.post("/", response_model=SkillResponse, status_code=201)
async def create_skill(
    req: SkillCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    skill = Skill(
        id=uuid4(), name=req.name, description=req.description,
        protocol_json=req.protocol_json, source_type=req.source_type,
        source_content=req.source_content, tenant_id=user.tenant_id,
        created_at=datetime.utcnow(),
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return SkillResponse(
        id=str(skill.id), name=skill.name, description=skill.description,
        source_type=skill.source_type, created_at=skill.created_at.isoformat(),
    )


@router.get("/", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(Skill).where(Skill.tenant_id == user.tenant_id))
    skills = result.scalars().all()
    return [
        SkillResponse(
            id=str(s.id), name=s.name, description=s.description,
            source_type=s.source_type, created_at=s.created_at.isoformat(),
        )
        for s in skills
    ]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(Skill).where(Skill.id == skill_id, Skill.tenant_id == user.tenant_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(
        id=str(skill.id), name=skill.name, description=skill.description,
        source_type=skill.source_type, created_at=skill.created_at.isoformat(),
    )


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("admin", "manager"))):
    result = await db.execute(select(Skill).where(Skill.id == skill_id, Skill.tenant_id == user.tenant_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
