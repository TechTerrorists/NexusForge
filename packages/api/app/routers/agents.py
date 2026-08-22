from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime

from ..database import get_db
from ..models import Agent, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    prompt: str = ""
    personality: dict | None = None
    model_provider: str = "openai"
    model_name: str = "gpt-4o"
    llm_config: dict = {}
    tools: list = []
    knowledge_bases: list = []
    middleware: list = []
    skills: list = []


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    personality: dict | None = None
    model_provider: str | None = None
    model_name: str | None = None
    llm_config: dict | None = None
    tools: list | None = None
    knowledge_bases: list | None = None
    middleware: list | None = None
    skills: list | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    model_provider: str
    model_name: str
    tools: list
    created_at: str


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(
    req: AgentCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    agent = Agent(
        id=uuid4(), name=req.name, description=req.description, prompt=req.prompt,
        personality=req.personality, model_provider=req.model_provider,
        model_name=req.model_name, model_config=req.llm_config,
        tools=req.tools, knowledge_bases=req.knowledge_bases,
        middleware=req.middleware, skills=req.skills, graph_json=None,
        tenant_id=user.tenant_id, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse(
        id=str(agent.id), name=agent.name, description=agent.description,
        prompt=agent.prompt, model_provider=agent.model_provider,
        model_name=agent.model_name, tools=agent.tools,
        created_at=agent.created_at.isoformat(),
    )


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    limit: int = Query(50, le=200), offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Agent).where(Agent.tenant_id == user.tenant_id).offset(offset).limit(limit)
    )
    agents = result.scalars().all()
    return [
        AgentResponse(
            id=str(a.id), name=a.name, description=a.description, prompt=a.prompt,
            model_provider=a.model_provider, model_name=a.model_name, tools=a.tools,
            created_at=a.created_at.isoformat(),
        )
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str, db: AsyncSession = Depends(get_db),
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
        prompt=agent.prompt, model_provider=agent.model_provider,
        model_name=agent.model_name, tools=agent.tools,
        created_at=agent.created_at.isoformat(),
    )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str, req: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return AgentResponse(
        id=str(agent.id), name=agent.name, description=agent.description,
        prompt=agent.prompt, model_provider=agent.model_provider,
        model_name=agent.model_name, tools=agent.tools,
        created_at=agent.created_at.isoformat(),
    )


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
