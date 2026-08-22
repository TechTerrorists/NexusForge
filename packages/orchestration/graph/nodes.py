"""Pure async node functions — thin wrappers around agent invocations.

Each function has the signature::

    async def node_name(state: WorkflowState) -> dict

LangGraph calls these and merges the returned dict into ``WorkflowState`` via
reducer semantics.  Every worker node is wrapped with cost tracking so token
usage and dollar cost accumulate in ``total_tokens`` / ``total_cost_usd``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Default prompts                                                              #
# --------------------------------------------------------------------------- #

_DEFAULT_SUPERVISOR_PROMPT = (
    "You are the Supervisor Agent for NexusForge, an enterprise AI orchestration "
    "platform.  Your job is to coordinate specialist agents:\n"
    "- researcher: gathers intelligence and context\n"
    "- analyzer: analyses data, scores, and classifies\n"
    "- executor: takes concrete actions (writes, API calls, emails)\n"
    "- human_approval: pauses for human review on sensitive decisions\n\n"
    "Route to the most appropriate agent based on the current stage.\n"
    "Route to FINISH when the workflow is complete.\n"
    "Always include brief reasoning for your routing decision."
)

_DEFAULT_RESEARCHER_PROMPT = (
    "You are the Researcher Agent for NexusForge.  Your mission: gather "
    "comprehensive intelligence relevant to the task.  Use available tools "
    "and available context to produce structured findings."
)

_DEFAULT_ANALYZER_PROMPT = (
    "You are the Analyzer Agent for NexusForge.  Your mission: analyse the "
    "data gathered by the researcher and produce a scored, classified "
    "assessment with clear recommendations."
)

_DEFAULT_EXECUTOR_PROMPT = (
    "You are the Executor Agent for NexusForge.  Your mission: take "
    "concrete actions based on the analysis — draft outputs, call APIs, "
    "send messages.  Record every action you take."
)

_PROMPT_DEFAULTS: dict[str, str] = {
    "supervisor": _DEFAULT_SUPERVISOR_PROMPT,
    "researcher": _DEFAULT_RESEARCHER_PROMPT,
    "analyzer": _DEFAULT_ANALYZER_PROMPT,
    "executor": _DEFAULT_EXECUTOR_PROMPT,
}


# --------------------------------------------------------------------------- #
# Stub agent — lightweight wrapper when no real agent object is provided        #
# --------------------------------------------------------------------------- #

class _StubAgent:
    """Minimal agent that invokes an LLM with a system prompt and structured output.

    Used when the caller doesn't supply pre-built agent instances so that the
    graph can still be compiled and executed with just an LLM.
    """

    def __init__(self, name: str, model: BaseChatModel, system_prompt: str) -> None:
        self.name = name
        self.model = model
        self.model_name = getattr(model, "model_name", None) or getattr(model, "model", None) or "stub"
        self.system_prompt = system_prompt

    async def safe_run(self, state: WorkflowState) -> dict:
        prompt = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Current state:\n{self._summarise_state(state)}"),
        ]
        response = await self.model.ainvoke(prompt)
        usage = getattr(response, "usage_metadata", None) or {}
        return {
            "messages": [response],
            "total_tokens": int(state.get("total_tokens", 0)) + int(usage.get("total_tokens", 0)),
        }

    @staticmethod
    def _summarise_state(state: WorkflowState) -> str:
        parts = [
            f"stage={state.get('current_stage')}",
            f"next_agent={state.get('next_agent')}",
            f"errors={len(state.get('errors', []))}",
        ]
        return " | ".join(parts)


# --------------------------------------------------------------------------- #
# RoutingDecision model (used by supervisor for structured output)             #
# --------------------------------------------------------------------------- #

class RoutingDecision:
    """Lightweight stand-in for a Pydantic RoutingDecision model.

    When the caller supplies a ``BaseChatModel`` the supervisor node uses
    ``model.with_structured_output`` to get a real Pydantic model; this
    plain class is the fallback for simple string routing.
    """

    def __init__(self, next_agent: str, reasoning: str = "") -> None:
        self.next = next_agent
        self.reasoning = reasoning


# --------------------------------------------------------------------------- #
# Node implementations                                                         #
# --------------------------------------------------------------------------- #

async def supervisor_node(state: WorkflowState) -> dict:
    """Supervisor node — reads current state and decides which worker runs next.

    If the agent supplies a ``with_structured_output`` compatible model, the
    decision is made via structured output.  Otherwise a simple stage-map is
    used as a deterministic fallback.
    """
    agent = state.get("_supervisor_agent")
    if agent is not None:
        return await _run_with_cost_tracking(agent, state)

    # Deterministic fallback when no LLM-backed agent is available
    stage = state.get("current_stage", "init")
    next_agent = _deterministic_route(stage, state)
    return {
        "next_agent": next_agent,
        "current_stage": _stage_for_agent(next_agent),
        "messages": [
            AIMessage(
                content=f"[Supervisor] Routing to {next_agent} (deterministic, stage={stage})",
                name="supervisor",
            )
        ],
    }


async def researcher_node(state: WorkflowState) -> dict:
    """Researcher node — gathers intelligence and appends to research_results."""
    agent = state.get("_researcher_agent")
    if agent is not None:
        return await _run_with_cost_tracking(agent, state)

    # Stub fallback
    return {
        "research_results": [{"summary": f"Research at stage {state.get('current_stage')}", "status": "stub"}],
        "messages": [
            AIMessage(content="[Researcher] Research completed (stub).", name="researcher")
        ],
    }


async def analyzer_node(state: WorkflowState) -> dict:
    """Analyzer node — scores and classifies, appends to analysis_scores."""
    agent = state.get("_analyzer_agent")
    if agent is not None:
        return await _run_with_cost_tracking(agent, state)

    return {
        "analysis_scores": [{"score": 5.0, "status": "stub"}],
        "messages": [
            AIMessage(content="[Analyzer] Analysis completed (stub, score=5.0).", name="analyzer")
        ],
    }


async def executor_node(state: WorkflowState) -> dict:
    """Executor node — takes concrete actions and records them."""
    agent = state.get("_executor_agent")
    if agent is not None:
        return await _run_with_cost_tracking(agent, state)

    return {
        "executed_actions": ["stub_action"],
        "messages": [
            AIMessage(content="[Executor] Action executed (stub).", name="executor")
        ],
    }


async def human_approval_node(state: WorkflowState) -> dict:
    """Human approval node — graph suspends here via ``interrupt_before``.

    When the graph is resumed after human intervention, this node runs with
    the updated ``approval_status``.  Actual routing happens in
    ``route_after_approval``.
    """
    approval_status = state.get("approval_status", "pending")
    approval_token = state.get("approval_token") or str(uuid.uuid4())

    logger.info(
        "Human approval node | status=%s | token=%s",
        approval_status,
        approval_token,
    )

    return {
        "approval_token": approval_token,
        "approval_status": approval_status,
    }


# --------------------------------------------------------------------------- #
# Factory — returns per-graph node closures                                    #
# --------------------------------------------------------------------------- #

def build_node_factory(
    supervisor: Any | None = None,
    prompt_overrides: dict[str, str] | None = None,
) -> dict[str, Callable]:
    """Return per-graph node callables bound to the provided agent instances.

    Each compiled graph gets its own closures so that compiling multiple
    workflow types in one process doesn't clobber shared module-level state.

    When ``supervisor`` is ``None`` the factory falls back to deterministic
    stub agents.  Callers that supply real agent objects should also stash
    them on the state dict (``_supervisor_agent``, ``_researcher_agent``, etc.)
    or pass them via the ``agents`` mapping in ``build_workflow_graph``.
    """
    prompts = {**_PROMPT_DEFAULTS}
    if prompt_overrides:
        prompts.update(prompt_overrides)

    # If a real supervisor agent was passed, store it so the node can access it
    _supervisor = supervisor

    async def _supervisor_node(state: WorkflowState) -> dict:
        patched = {**state, "_supervisor_agent": _supervisor}
        return await supervisor_node(patched)

    async def _researcher_node(state: WorkflowState) -> dict:
        return await researcher_node(state)

    async def _analyzer_node(state: WorkflowState) -> dict:
        return await analyzer_node(state)

    async def _executor_node(state: WorkflowState) -> dict:
        return await executor_node(state)

    async def _human_approval_node(state: WorkflowState) -> dict:
        return await human_approval_node(state)

    return {
        "supervisor": _supervisor_node,
        "researcher": _researcher_node,
        "analyzer": _analyzer_node,
        "executor": _executor_node,
        "human_approval": _human_approval_node,
    }


# --------------------------------------------------------------------------- #
# Cost-tracking wrapper                                                        #
# --------------------------------------------------------------------------- #

async def _run_with_cost_tracking(agent: Any, state: WorkflowState) -> dict:
    """Invoke an agent's ``safe_run`` and accumulate token / cost totals."""
    current_cost = float(state.get("total_cost_usd") or 0.0)
    current_tokens = int(state.get("total_tokens") or 0)

    patch = await agent.safe_run(state)

    # Extract usage from messages in the patch
    messages = patch.get("messages", []) or []
    in_tok, out_tok = _extract_usage(messages, getattr(agent, "model_name", "unknown"))

    # Simple cost estimate — real implementation would look up per-model pricing
    call_cost = _estimate_cost(getattr(agent, "model_name", ""), in_tok, out_tok)

    patch["total_tokens"] = current_tokens + in_tok + out_tok
    patch["total_cost_usd"] = round(current_cost + call_cost, 6)

    logger.debug(
        "Cost tracked | agent=%s in=%d out=%d call=$%.4f total=$%.4f",
        agent.name,
        in_tok,
        out_tok,
        call_cost,
        patch["total_cost_usd"],
    )
    return patch


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _extract_usage(messages: list[Any], model_name: str) -> tuple[int, int]:
    """Sum input + output tokens across any AIMessage with usage_metadata."""
    input_tokens = 0
    output_tokens = 0
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            input_tokens += int(usage.get("input_tokens", 0) or 0)
            output_tokens += int(usage.get("output_tokens", 0) or 0)
    return input_tokens, output_tokens


def _estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Rough cost estimate based on common model pricing tiers."""
    # Default tier (generic model)
    input_rate = 0.5 / 1_000_000   # $0.50 per 1M input tokens
    output_rate = 1.5 / 1_000_000  # $1.50 per 1M output tokens

    name_lower = model_name.lower()
    if "gpt-4o" in name_lower:
        input_rate = 2.5 / 1_000_000
        output_rate = 10.0 / 1_000_000
    elif "gpt-4" in name_lower:
        input_rate = 30.0 / 1_000_000
        output_rate = 60.0 / 1_000_000
    elif "claude" in name_lower and "sonnet" in name_lower:
        input_rate = 3.0 / 1_000_000
        output_rate = 15.0 / 1_000_000
    elif "claude" in name_lower and "haiku" in name_lower:
        input_rate = 0.25 / 1_000_000
        output_rate = 1.25 / 1_000_000

    return (input_tokens * input_rate) + (output_tokens * output_rate)


def _deterministic_route(stage: str, state: WorkflowState) -> str:
    """Fallback routing when no LLM is available — maps stages to agents."""
    stage_agent_map: dict[str, str] = {
        "init": "researcher",
        "research": "analyzer",
        "analyze": "executor",
        "propose": "human_approval",
        "approve": "executor",
        "execute": "executor",
    }
    # Check if lead was disqualified
    scores = state.get("analysis_scores", [])
    if scores and scores[-1].get("score", 0) < 4.0:
        return "FINISH"

    return stage_agent_map.get(stage, "FINISH")


def _stage_for_agent(agent_name: str) -> str:
    """Map agent name to the stage it produces."""
    return {
        "researcher": "research",
        "analyzer": "analyze",
        "executor": "execute",
        "human_approval": "approve",
        "FINISH": "done",
    }.get(agent_name, "done")
