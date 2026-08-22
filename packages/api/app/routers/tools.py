from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime

from ..database import get_db
from ..models import ToolDefinition, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolCreate(BaseModel):
    name: str
    description: str = ""
    schema_json: dict = {}
    connector_type: str | None = None
    config_json: dict = {}


class ToolResponse(BaseModel):
    id: str
    name: str
    description: str
    schema_json: dict
    connector_type: str | None
    created_at: str


@router.post("/", response_model=ToolResponse, status_code=201)
async def create_tool(
    req: ToolCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    tool = ToolDefinition(
        id=uuid4(), name=req.name, description=req.description,
        schema_json=req.schema_json, connector_type=req.connector_type,
        config_json=req.config_json, created_at=datetime.utcnow(),
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return ToolResponse(
        id=str(tool.id), name=tool.name, description=tool.description,
        schema_json=tool.schema_json, connector_type=tool.connector_type,
        created_at=tool.created_at.isoformat(),
    )


@router.get("/", response_model=list[ToolResponse])
async def list_tools(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    result = await db.execute(select(ToolDefinition))
    tools = result.scalars().all()
    return [
        ToolResponse(
            id=str(t.id), name=t.name, description=t.description,
            schema_json=t.schema_json, connector_type=t.connector_type,
            created_at=t.created_at.isoformat(),
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
        id=str(tool.id), name=tool.name, description=tool.description,
        schema_json=tool.schema_json, connector_type=tool.connector_type,
        created_at=tool.created_at.isoformat(),
    )


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("admin", "manager"))):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()
