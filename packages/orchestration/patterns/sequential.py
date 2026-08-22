"""Sequential pattern — chain agents in strict order, passing state along.

The output of each agent becomes part of the state consumed by the next.
This is the simplest orchestration pattern and the building block for
more complex ones.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


class SequentialPattern:
    """Chain N agents in sequence, passing accumulated state to each.

    Usage::

        pattern = SequentialPattern(agents=[researcher, analyzer, executor])
        result = await pattern.run(initial_state)

    Each agent must implement ``async def safe_run(state) -> dict``.
    The partial dicts returned are merged into the working state after
    each agent completes.
    """

    def __init__(
        self,
        agents: list[Any],
        name: str = "sequential",
    ) -> None:
        self.name = name
        self.agents = agents

    async def run(
        self,
        initial_state: WorkflowState,
        *,
        config: dict | None = None,
    ) -> dict:
        """Execute the full chain and return the final state patch.

        Args:
            initial_state: Starting state for the chain.
            config: Optional config dict (passed through to each agent).

        Returns:
            Merged state patch containing all intermediate results.
        """
        working_state = dict(initial_state)
        merged_patch: dict[str, Any] = {}
        agent_names = [getattr(a, "name", f"agent_{i}") for i, a in enumerate(self.agents)]

        logger.info(
            "Sequential '%s' starting | agents=%s",
            self.name,
            agent_names,
        )

        for idx, agent in enumerate(self.agents):
            agent_name = getattr(agent, "name", f"agent_{idx}")
            logger.info(
                "Sequential '%s' step %d/%d — %s",
                self.name,
                idx + 1,
                len(self.agents),
                agent_name,
            )

            try:
                patch = await agent.safe_run(working_state)
            except Exception as exc:
                logger.error("Sequential '%s' agent '%s' failed: %s", self.name, agent_name, exc)
                error_entry = f"{agent_name}: {exc}"
                existing_errors = list(working_state.get("errors", []))
                merged_patch["errors"] = existing_errors + [error_entry]
                break

            merged_patch.update(patch)
            working_state.update(patch)

        logger.info("Sequential '%s' complete | steps=%d", self.name, len(self.agents))
        return merged_patch

    async def run_streaming(
        self,
        initial_state: WorkflowState,
    ):
        """Yield per-agent state patches as they complete."""
        working_state = dict(initial_state)

        for idx, agent in enumerate(self.agents):
            agent_name = getattr(agent, "name", f"agent_{idx}")
            patch = await agent.safe_run(working_state)
            working_state.update(patch)
            yield {"agent": agent_name, "step": idx, "patch": patch}
