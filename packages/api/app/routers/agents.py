from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from ..database import get_db
from ..models import Agent, AgentType, User, UserRole
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    agent_type: str = "llm"
    system_prompt: str = ""
    model_config: dict = {}
    tools: list = []
    skills: list = []
    parameters: dict = {}


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_type: str | None = None
    system_prompt: str | None = None
    model_config: dict | None = None
    tools: list | None = None
    skills: list | None = None
    parameters: dict | None = None
    is_active: bool | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    agent_type: str
    system_prompt: str
    model_config: dict
    tools: list
    skills: list
    is_active: bool
    version: int
    created_at: str
    updated_at: str


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(
    req: AgentCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    agent = Agent(
        id=uuid4(),
        name=req.name,
        description=req.description,
        agent_type=AgentType(req.agent_type),
        system_prompt=req.system_prompt,
        model_config=req.model_config,
        tools=req.tools,
        skills=req.skills,
        parameters=req.parameters,
        tenant_id=user.tenant_id,
        created_by=user.id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse(
        id=str(agent.id), name=agent.name, description=agent.description,
        agent_type=agent.agent_type.value, system_prompt=agent.system_prompt or "",
        model_config=agent.model_config or {}, tools=agent.tools or [],
        skills=agent.skills or [], is_active=agent.is_active, version=agent.version,
        created_at=agent.created_at.isoformat(), updated_at=agent.updated_at.isoformat(),
    )


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    agent_type: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    q = select(Agent).where(Agent.tenant_id == user.tenant_id)
    if agent_type:
        q = q.where(Agent.agent_type == agent_type)
    q = q.order_by(Agent.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    agents = result.scalars().all()
    return [
        AgentResponse(
            id=str(a.id), name=a.name, description=a.description,
            agent_type=a.agent_type.value, system_prompt=a.system_prompt or "",
            model_config=a.model_config or {}, tools=a.tools or [],
            skills=a.skills or [], is_active=a.is_active, version=a.version,
            created_at=a.created_at.isoformat(), updated_at=a.updated_at.isoformat(),
        )
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse(
        id=str(agent.id), name=agent.name, description=agent.description,
        agent_type=agent.agent_type.value, system_prompt=agent.system_prompt or "",
        model_config=agent.model_config or {}, tools=agent.tools or [],
        skills=agent.skills or [], is_active=agent.is_active, version=agent.version,
        created_at=agent.created_at.isoformat(), updated_at=agent.updated_at.isoformat(),
    )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str, req: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if req.name is not None:
        agent.name = req.name
    if req.description is not None:
        agent.description = req.description
    if req.agent_type is not None:
        agent.agent_type = AgentType(req.agent_type)
    if req.system_prompt is not None:
        agent.system_prompt = req.system_prompt
    if req.model_config is not None:
        agent.model_config = req.model_config
    if req.tools is not None:
        agent.tools = req.tools
    if req.skills is not None:
        agent.skills = req.skills
    if req.parameters is not None:
        agent.parameters = req.parameters
    if req.is_active is not None:
        agent.is_active = req.is_active
    agent.version += 1
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return AgentResponse(
        id=str(agent.id), name=agent.name, description=agent.description,
        agent_type=agent.agent_type.value, system_prompt=agent.system_prompt or "",
        model_config=agent.model_config or {}, tools=agent.tools or [],
        skills=agent.skills or [], is_active=agent.is_active, version=agent.version,
        created_at=agent.created_at.isoformat(), updated_at=agent.updated_at.isoformat(),
    )


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
