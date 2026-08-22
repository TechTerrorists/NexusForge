"""Supervisor with structured output — stage-aware routing for the hub-and-spoke graph.

The SupervisorRouter reads the current ``WorkflowState``, builds a
context-aware prompt, and uses ``model.with_structured_output(RoutingDecision)``
to emit a deterministic, auditable routing decision.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Structured output model                                                      #
# --------------------------------------------------------------------------- #

AgentName = Literal["researcher", "analyzer", "executor", "human_approval", "FINISH"]


class RoutingDecision(BaseModel):
    """Structured routing decision emitted by the supervisor."""

    next: AgentName
    reasoning: str


# --------------------------------------------------------------------------- #
# Stage transition map                                                          #
# --------------------------------------------------------------------------- #

_STAGE_MAP: dict[str, dict[str, str]] = {
    "researcher": {"stage": "research", "label": "Research"},
    "analyzer": {"stage": "analyze", "label": "Analysis"},
    "executor_propose": {"stage": "propose", "label": "Proposal"},
    "executor_execute": {"stage": "execute", "label": "Execution"},
    "human_approval": {"stage": "approve", "label": "Approval"},
    "FINISH": {"stage": "done", "label": "Complete"},
}


def _determine_stage(next_agent: str, current_stage: str) -> str:
    """Map agent name + current stage to the resulting stage name."""
    if next_agent == "executor":
        if current_stage in ("analyze", "research"):
            return "propose"
        return "execute"
    return _STAGE_MAP.get(next_agent, {}).get("stage", current_stage)


# --------------------------------------------------------------------------- #
# Default supervisor system prompt                                             #
# --------------------------------------------------------------------------- #

_DEFAULT_SUPERVISOR_PROMPT = """You are the Supervisor Agent for NexusForge, an enterprise AI orchestration platform.

Your job is to coordinate a team of specialist agents to process tasks:
- researcher: Gathers intelligence, context, and data
- analyzer: Analyses data, scores, classifies, and recommends
- executor: Takes concrete actions (writes, API calls, proposals)
- human_approval: Pauses for human review on sensitive decisions

Workflow stages:
1. init     → route to researcher (gather intelligence)
2. research → route to analyzer (analyse findings)
3. analyze  → if analysis warrants action: route to executor; else FINISH
4. propose  → route to human_approval (await review)
5. approve  → route to executor (execute approved action)
6. execute  → FINISH

Route to FINISH only when the workflow is complete or the task is done.
Always include a brief reasoning for your routing decision."""


# --------------------------------------------------------------------------- #
# SupervisorRouter                                                             #
# --------------------------------------------------------------------------- #

class SupervisorRouter:
    """Structured-output supervisor that uses ``model.with_structured_output``.

    Usage::

        router = SupervisorRouter(model=llm, system_prompt="...")
        decision = await router.route(state)
        # decision.next == "researcher" | "analyzer" | "executor" | ...
    """

    def __init__(
        self,
        model: BaseChatModel,
        system_prompt: str | None = None,
        allowed_agents: list[str] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt or _DEFAULT_SUPERVISOR_PROMPT
        self.allowed_agents = allowed_agents or [
            "researcher", "analyzer", "executor", "human_approval", "FINISH"
        ]
        self._structured_model = model.with_structured_output(RoutingDecision)

    def _build_context(self, state: WorkflowState) -> str:
        """Build a context summary for the routing decision."""
        parts = [f"Current stage: {state.get('current_stage', 'unknown')}"]

        errors = state.get("errors", [])
        if errors:
            parts.append(f"Recent errors: {errors[-1]}")

        analysis = state.get("analysis_scores", [])
        if analysis:
            latest = analysis[-1]
            score = latest.get("score", 0)
            parts.append(f"Latest analysis score: {score}/10")
            if score < 4.0:
                parts.append("Score below threshold — consider FINISH (disqualified)")

        approval = state.get("approval_status")
        if approval:
            parts.append(f"Approval status: {approval}")

        executed = state.get("executed_actions", [])
        if executed:
            parts.append(f"Actions completed: {len(executed)} ({', '.join(executed[-3:])})")

        tokens = state.get("total_tokens", 0)
        cost = state.get("total_cost_usd", 0.0)
        parts.append(f"Resource usage: {tokens} tokens, ${cost:.4f}")

        return "\n".join(parts)

    async def route(self, state: WorkflowState) -> RoutingDecision:
        """Invoke the LLM with structured output and return a RoutingDecision.

        Falls back to a deterministic decision if the LLM call fails.
        """
        context = self._build_context(state)

        prompt = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(
                content=f"Context:\n{context}\n\n"
                f"Available agents: {self.allowed_agents}\n\n"
                f"What is the next routing decision?"
            ),
        ]

        try:
            decision = cast(RoutingDecision, await self._structured_model.ainvoke(prompt))
        except Exception as exc:
            logger.warning("Supervisor LLM call failed, using deterministic fallback: %s", exc)
            decision = self._deterministic_fallback(state)

        logger.info(
            "Supervisor routing: stage=%s -> %s | reason: %s",
            state.get("current_stage"),
            decision.next,
            decision.reasoning,
        )
        return decision

    def _deterministic_fallback(self, state: WorkflowState) -> RoutingDecision:
        """Deterministic fallback when the LLM is unavailable."""
        stage = state.get("current_stage", "init")
        scores = state.get("analysis_scores", [])

        if stage == "init":
            return RoutingDecision(next="researcher", reasoning="Starting workflow — gather intelligence")
        elif stage == "research":
            return RoutingDecision(next="analyzer", reasoning="Research complete — analyse findings")
        elif stage == "analyze":
            if scores and scores[-1].get("score", 0) >= 4.0:
                return RoutingDecision(next="executor", reasoning="Analysis positive — draft proposal")
            return RoutingDecision(next="FINISH", reasoning="Score below threshold — disqualify")
        elif stage == "propose":
            return RoutingDecision(next="human_approval", reasoning="Proposal ready — await human review")
        elif stage == "approve":
            approval = state.get("approval_status")
            if approval == "approved":
                return RoutingDecision(next="executor", reasoning="Approved — execute")
            return RoutingDecision(next="FINISH", reasoning="Not approved — terminate")
        return RoutingDecision(next="FINISH", reasoning="Workflow complete")

    async def route_as_dict(self, state: WorkflowState) -> dict:
        """Route and return a state-update dict compatible with LangGraph."""
        decision = await self.route(state)
        next_stage = _determine_stage(decision.next, state.get("current_stage", ""))
        return {
            "next_agent": decision.next,
            "current_stage": next_stage,
            "messages": [
                AIMessage(
                    content=f"[Supervisor] Routing to {decision.next}: {decision.reasoning}",
                    name="supervisor",
                )
            ],
        }
