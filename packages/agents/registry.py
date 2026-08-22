from __future__ import annotations

from typing import Any

from packages.agents.base import BaseAgent
from packages.agents.types.models import AgentCapability


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent_id: str, agent_instance: BaseAgent) -> None:
        self._agents[agent_id] = agent_instance

    def unregister(self, agent_id: str) -> bool:
        return self._agents.pop(agent_id, None) is not None

    def get(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "agent_id": agent_id,
                "name": agent.name,
                "model_name": getattr(agent, "model_name", "unknown"),
            }
            for agent_id, agent in self._agents.items()
        ]

    def discover(self, capability: AgentCapability) -> list[BaseAgent]:
        results: list[BaseAgent] = []
        for agent in self._agents.values():
            meta = getattr(agent, "_metadata", None)
            if meta is not None:
                cfg = getattr(meta, "config", None)
                if cfg is not None and capability in getattr(cfg, "capabilities", []):
                    results.append(agent)
        return results
