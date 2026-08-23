from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from ..database import get_db
from ..models import ToolDefinition, User, UserRole
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolCreate(BaseModel):
    name: str
    description: str = ""
    tool_type: str = "function"
    endpoint_url: str | None = None
    auth_config: dict = {}
    rate_limit: int = 100


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tool_type: str | None = None
    endpoint_url: str | None = None
    auth_config: dict | None = None
    rate_limit: int | None = None
    is_active: bool | None = None


class ToolResponse(BaseModel):
    id: str
    name: str
    description: str
    tool_type: str
    endpoint_url: str | None
    rate_limit: int
    is_active: bool
    created_at: str
    updated_at: str


@router.post("/", response_model=ToolResponse, status_code=201)
async def create_tool(
    req: ToolCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    tool = ToolDefinition(
        id=uuid4(), name=req.name, description=req.description,
        tool_type=req.tool_type, endpoint_url=req.endpoint_url,
        auth_config=req.auth_config, rate_limit=req.rate_limit,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return ToolResponse(
        id=str(tool.id), name=tool.name, description=tool.description or "",
        tool_type=tool.tool_type, endpoint_url=tool.endpoint_url,
        rate_limit=tool.rate_limit, is_active=tool.is_active,
        created_at=tool.created_at.isoformat(), updated_at=tool.updated_at.isoformat(),
    )


@router.get("/", response_model=list[ToolResponse])
async def list_tools(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(ToolDefinition).order_by(ToolDefinition.created_at.desc()))
    tools = result.scalars().all()
    return [
        ToolResponse(
            id=str(t.id), name=t.name, description=t.description or "",
            tool_type=t.tool_type, endpoint_url=t.endpoint_url,
            rate_limit=t.rate_limit, is_active=t.is_active,
            created_at=t.created_at.isoformat(), updated_at=t.updated_at.isoformat(),
        )
        for t in tools
    ]


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolResponse(
        id=str(tool.id), name=tool.name, description=tool.description or "",
        tool_type=tool.tool_type, endpoint_url=tool.endpoint_url,
        rate_limit=tool.rate_limit, is_active=tool.is_active,
        created_at=tool.created_at.isoformat(), updated_at=tool.updated_at.isoformat(),
    )


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: str, req: ToolUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(tool, field, value)
    tool.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tool)
    return ToolResponse(
        id=str(tool.id), name=tool.name, description=tool.description or "",
        tool_type=tool.tool_type, endpoint_url=tool.endpoint_url,
        rate_limit=tool.rate_limit, is_active=tool.is_active,
        created_at=tool.created_at.isoformat(), updated_at=tool.updated_at.isoformat(),
    )


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER))):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()
