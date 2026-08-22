"""WorkflowState — the single TypedDict that flows through every graph node.

Reducer semantics (LangGraph conventions):
  - add_messages  -> append messages, dedup by ID (standard LangGraph pattern)
  - operator.add  -> list concatenation (accumulate results across agent hops)
  - no reducer    -> last-write-wins (simple override, used for routing decisions)

Shared channels carry conversation messages, routing decisions, per-agent data,
human approval state, memory context, and workflow bookkeeping through the graph.
"""

from __future__ import annotations

import uuid
from operator import add
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# --------------------------------------------------------------------------- #
# Core state definition                                                        #
# --------------------------------------------------------------------------- #

class WorkflowState(TypedDict):
    """Unified state that every graph node reads and writes."""

    # ---- Message channel — add_messages handles dedup by message ID ---- #
    messages: Annotated[list[BaseMessage], add_messages]

    # ---- Input / Output channels ---- #
    input: dict
    output: NotRequired[dict | None]

    # ---- System channel ---- #
    sys: dict

    # ---- Human-in-the-loop ---- #
    human: NotRequired[dict | None]

    # ---- Persistent memories ---- #
    memories: NotRequired[dict | None]

    # ---- Follow-up queue (decentralised handoff patterns) ---- #
    pending_follow_ups: Annotated[list[dict], add]

    # ---- Routing — supervisor writes, conditional edges read ---- #
    next_agent: str | None
    current_stage: str
    current_node: str | None

    # ---- Accumulator fields — results append across agent hops ---- #
    research_results: Annotated[list[dict], add]
    analysis_scores: Annotated[list[dict], add]
    executed_actions: Annotated[list[str], add]
    errors: Annotated[list[str], add]

    # ---- Workflow bookkeeping ---- #
    workflow_id: str
    thread_id: str

    # ---- Domain data (generic dict, typed by the domain layer) ---- #
    lead_id: str | None
    lead_data: dict | None
    proposal: dict | None

    # ---- Human approval state ---- #
    approval_status: str | None
    approval_token: str | None

    # ---- Cost tracking (updated by cost tracker after each LLM call) ---- #
    total_tokens: int
    total_cost_usd: float

    # ---- Dry-run flag ---- #
    dry_run: bool

    # ---- Metadata forwarded to tracing / audit log ---- #
    run_metadata: dict


# --------------------------------------------------------------------------- #
# Per-agent channel helpers                                                    #
# --------------------------------------------------------------------------- #

def create_per_agent_channel(agent_name: str) -> dict:
    """Create an isolated data channel for a single agent.

    Returns a dict keyed by ``<agent_name>_data`` that the agent can use
    to store intermediate results without polluting other agents' namespaces.
    """
    channel_key = f"{agent_name}_data"
    return {channel_key: {}}


def create_per_agent_channels(agent_names: list[str]) -> dict:
    """Create isolated data channels for a list of agents.

    Returns a merged dict of ``<agent_name>_data`` -> ``{}`` entries that
    can be merged into the initial WorkflowState ``sys`` dict.
    """
    merged: dict[str, dict] = {}
    for name in agent_names:
        channel_key = f"{name}_data"
        merged[channel_key] = {}
    return merged


# --------------------------------------------------------------------------- #
# Initial state factory                                                        #
# --------------------------------------------------------------------------- #

def create_initial_state(
    *,
    workflow_id: str | None = None,
    thread_id: str | None = None,
    input_data: dict | None = None,
    sys_config: dict | None = None,
    dry_run: bool = False,
    run_metadata: dict | None = None,
) -> WorkflowState:
    """Build a fresh WorkflowState for a new run.

    Generates UUIDs for ``workflow_id`` / ``thread_id`` when not provided.
    """
    return WorkflowState(
        messages=[],
        input=input_data or {},
        output=None,
        sys=sys_config or {},
        human=None,
        memories=None,
        pending_follow_ups=[],
        next_agent=None,
        current_stage="init",
        current_node=None,
        research_results=[],
        analysis_scores=[],
        executed_actions=[],
        errors=[],
        workflow_id=workflow_id or str(uuid.uuid4()),
        thread_id=thread_id or str(uuid.uuid4()),
        lead_id=None,
        lead_data=None,
        proposal=None,
        approval_status=None,
        approval_token=None,
        total_tokens=0,
        total_cost_usd=0.0,
        dry_run=dry_run,
        run_metadata=run_metadata or {},
    )
