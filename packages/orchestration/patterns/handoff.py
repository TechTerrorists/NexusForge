"""Handoff pattern — decentralised routing where agents decide their targets.

Supports two modes:
  - **routed**: Each agent picks the next agent; the pattern enforces the order.
  - **autonomous**: Agents can hand off to any other agent at any time,
    including themselves, creating emergent conversation flows.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


class HandoffCapableAgent:
    """Wraps an agent for the handoff pattern with a pluggable next-agent selector."""

    def __init__(
        self,
        agent: Any,
        handoff_selector: Callable[[dict, WorkflowState], str | None] | None = None,
    ) -> None:
        self.agent = agent
        self.name = getattr(agent, "name", "unknown")
        self.handoff_selector = handoff_selector

    async def safe_run(self, state: WorkflowState) -> dict:
        return await self.agent.safe_run(state)

    def select_next(self, patch: dict, state: WorkflowState) -> str | None:
        if self.handoff_selector:
            return self.handoff_selector(patch, state)
        return patch.get("next_agent")


class HandoffPattern:
    """Decentralised multi-agent pattern where agents choose who runs next."""

    def __init__(
        self,
        agents: list[Any],
        name: str = "handoff",
        autonomous: bool = False,
        max_rounds: int = 50,
        handoff_selectors: dict[str, Callable] | None = None,
        termination_condition: Callable[[WorkflowState], bool] | None = None,
    ) -> None:
        self.name = name
        self.autonomous = autonomous
        self.max_rounds = max_rounds
        self.termination_condition = termination_condition

        self.agents: dict[str, HandoffCapableAgent] = {}
        for agent in agents:
            agent_name = getattr(agent, "name", f"agent_{len(self.agents)}")
            selector = (handoff_selectors or {}).get(agent_name)
            self.agents[agent_name] = HandoffCapableAgent(agent, selector)

        self._history: list[dict[str, Any]] = []

    async def run(
        self,
        initial_state: WorkflowState,
        *,
        start_agent: str | None = None,
    ) -> dict:
        """Execute the handoff chain until an agent terminates or max_rounds is hit."""
        working_state = dict(initial_state)
        merged_patch: dict[str, Any] = {}
        self._history = []

        agent_names = list(self.agents.keys())
        current_agent_name = start_agent or (agent_names[0] if agent_names else None)

        if current_agent_name is None:
            logger.warning("Handoff '%s': no agents configured", self.name)
            return merged_patch

        logger.info(
            "Handoff '%s' starting | mode=%s | agents=%s | max_rounds=%d",
            self.name,
            "autonomous" if self.autonomous else "routed",
            agent_names,
            self.max_rounds,
        )

        for round_num in range(self.max_rounds):
            if current_agent_name not in self.agents:
                logger.info(
                    "Handoff '%s' round %d: agent '%s' not found, terminating",
                    self.name, round_num, current_agent_name,
                )
                break

            cap = self.agents[current_agent_name]

            if self.termination_condition and self.termination_condition(working_state):
                logger.info("Handoff '%s' terminated by condition at round %d", self.name, round_num)
                break

            logger.info("Handoff '%s' round %d: %s", self.name, round_num, current_agent_name)

            try:
                patch = await cap.safe_run(working_state)
            except Exception as exc:
                logger.error("Handoff '%s' agent '%s' failed: %s", self.name, current_agent_name, exc)
                merged_patch.setdefault("errors", []).append(f"{current_agent_name}: {exc}")
                break

            merged_patch.update(patch)
            working_state.update(patch)

            self._history.append({
                "round": round_num,
                "agent": current_agent_name,
                "patch_keys": list(patch.keys()),
            })

            next_agent = cap.select_next(patch, working_state)
            if next_agent is None or next_agent == "END":
                logger.info(
                    "Handoff '%s' agent '%s' chose to terminate",
                    self.name, current_agent_name,
                )
                break

            current_agent_name = next_agent

        merged_patch["handoff_history"] = list(self._history)
        logger.info("Handoff '%s' complete | rounds=%d", self.name, len(self._history))
        return merged_patch
