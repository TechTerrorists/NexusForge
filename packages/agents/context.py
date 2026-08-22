from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from packages.agents.base import BaseAgent
from packages.agents.session import AgentSession

context_var: ContextVar[AgentRunContext | None] = ContextVar(
    "nexusforge_agent_run_context", default=None
)


@dataclass
class AgentRunContext:
    agent: BaseAgent | None = None
    session: AgentSession | None = None
    request_messages: list[dict[str, Any]] = field(default_factory=list)
    run_options: dict[str, Any] = field(default_factory=dict)


def get_context() -> AgentRunContext | None:
    return context_var.get()


def set_context(ctx: AgentRunContext | None) -> None:
    context_var.set(ctx)
