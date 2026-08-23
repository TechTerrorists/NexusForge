from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from ..database import get_db
from ..models import Skill, User, UserRole
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    skill_type: str = "general"
    config: dict = {}


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    skill_type: str | None = None
    config: dict | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    skill_type: str
    config: dict
    created_at: str
    updated_at: str


@router.post("/", response_model=SkillResponse, status_code=201)
async def create_skill(
    req: SkillCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    skill = Skill(
        id=uuid4(), name=req.name, description=req.description,
        skill_type=req.skill_type, config=req.config,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return SkillResponse(
        id=str(skill.id), name=skill.name, description=skill.description or "",
        skill_type=skill.skill_type, config=skill.config or {},
        created_at=skill.created_at.isoformat(), updated_at=skill.updated_at.isoformat(),
    )


@router.get("/", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(Skill).order_by(Skill.created_at.desc()))
    skills = result.scalars().all()
    return [
        SkillResponse(
            id=str(s.id), name=s.name, description=s.description or "",
            skill_type=s.skill_type, config=s.config or {},
            created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(),
        )
        for s in skills
    ]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(
        id=str(skill.id), name=skill.name, description=skill.description or "",
        skill_type=skill.skill_type, config=skill.config or {},
        created_at=skill.created_at.isoformat(), updated_at=skill.updated_at.isoformat(),
    )


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str, req: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    skill.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(skill)
    return SkillResponse(
        id=str(skill.id), name=skill.name, description=skill.description or "",
        skill_type=skill.skill_type, config=skill.config or {},
        created_at=skill.created_at.isoformat(), updated_at=skill.updated_at.isoformat(),
    )


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER))):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
