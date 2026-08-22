"""Concurrent pattern — fan-out to parallel agents, fan-in with aggregation.

All agents execute concurrently on the same state snapshot.  Results are
collected and merged via a configurable aggregation function.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


def _default_aggregator(results: list[dict]) -> dict:
    """Merge all agent patches into a single dict.

    List-type fields (``errors``, ``research_results``, etc.) are concatenated.
    Scalar fields use last-write-wins.
    """
    merged: dict[str, Any] = {}
    list_keys = {"errors", "research_results", "analysis_scores", "executed_actions", "messages"}

    for patch in results:
        for key, value in patch.items():
            if key in list_keys and key in merged:
                existing = merged[key]
                if isinstance(existing, list) and isinstance(value, list):
                    merged[key] = existing + value
                else:
                    merged[key] = value
            else:
                merged[key] = value
    return merged


class ConcurrentPattern:
    """Fan-out to N agents in parallel, fan-in with aggregation.

    Usage::

        pattern = ConcurrentPattern(agents=[agent_a, agent_b, agent_c])
        result = await pattern.run(initial_state)

    All agents run concurrently on the same state snapshot.  The
    ``aggregator`` callable merges the individual patches; the default
    handles list concatenation for accumulator fields.
    """

    def __init__(
        self,
        agents: list[Any],
        name: str = "concurrent",
        aggregator: Callable[[list[dict]], dict] | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.name = name
        self.agents = agents
        self.aggregator = aggregator or _default_aggregator
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None

    async def _run_single(self, agent: Any, state: WorkflowState) -> dict:
        """Run a single agent, optionally gated by the semaphore."""
        if self._semaphore:
            async with self._semaphore:
                return await agent.safe_run(state)
        return await agent.safe_run(state)

    async def run(
        self,
        initial_state: WorkflowState,
        *,
        config: dict | None = None,
    ) -> dict:
        """Execute all agents concurrently and aggregate results.

        Args:
            initial_state: Shared state snapshot for all agents.
            config: Optional config (currently unused, reserved).

        Returns:
            Aggregated state patch.
        """
        agent_names = [getattr(a, "name", f"agent_{i}") for i, a in enumerate(self.agents)]

        logger.info(
            "Concurrent '%s' starting | agents=%s",
            self.name,
            agent_names,
        )

        # All agents see the same snapshot — no interleaving
        frozen_state = dict(initial_state)

        tasks = [
            asyncio.create_task(
                self._run_single(agent, frozen_state),
                name=getattr(agent, "name", f"agent_{i}"),
            )
            for i, agent in enumerate(self.agents)
        ]

        results: list[dict] = []
        for coro in asyncio.as_completed(tasks):
            try:
                patch = await coro
                results.append(patch)
            except Exception as exc:
                logger.error("Concurrent '%s' agent failed: %s", self.name, exc)
                results.append({"errors": [f"concurrent_agent: {exc}"]})

        merged = self.aggregator(results)

        logger.info(
            "Concurrent '%s' complete | agents=%d",
            self.name,
            len(self.agents),
        )
        return merged

    async def run_streaming(
        self,
        initial_state: WorkflowState,
    ):
        """Yield per-agent patches as they complete (unordered)."""
        frozen_state = dict(initial_state)

        tasks = {
            asyncio.create_task(
                self._run_single(agent, frozen_state),
                name=getattr(agent, "name", f"agent_{i}"),
            )
            for i, agent in enumerate(self.agents)
        }

        for coro in asyncio.as_completed(tasks):
            try:
                patch = await coro
                task_name = next(
                    t.get_name() for t in tasks if t._coro is coro  # type: ignore[attr-defined]
                )
                yield {"agent": task_name, "patch": patch}
            except Exception as exc:
                yield {"agent": "unknown", "patch": {"errors": [str(exc)]}}
