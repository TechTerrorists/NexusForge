from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentCapability(str, Enum):
    TEXT_GENERATION = "text_generation"
    CODE_GENERATION = "code_generation"
    WEB_SEARCH = "web_search"
    DATA_ANALYSIS = "data_analysis"
    TOOL_EXECUTION = "tool_execution"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    HUMAN_APPROVAL = "human_approval"
    BROWSER_AUTOMATION = "browser_automation"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_HUMAN = "waiting_human"
    TERMINATED = "terminated"


class AgentConfig(BaseModel):
    name: str
    description: str = ""
    model_provider: str = "openai"
    model_name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    capabilities: list[AgentCapability] = Field(default_factory=list)


class AgentMetadata(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    config: AgentConfig
    status: AgentStatus = AgentStatus.IDLE
    run_count: int = 0
    last_heartbeat: float | None = None
