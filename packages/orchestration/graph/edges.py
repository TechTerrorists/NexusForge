"""Conditional edge routing functions for the LangGraph StateGraph.

Each function reads from ``WorkflowState`` and returns a string key that
maps to the next node name in the graph's edge table.
"""

from __future__ import annotations

from packages.orchestration.state import WorkflowState


def route_from_supervisor(state: WorkflowState) -> str:
    """Primary routing decision from the supervisor node.

    Reads ``state['next_agent']`` which the ``SupervisorAgent`` (or
    deterministic fallback) writes.  Returns a node name or ``"END"``.
    """
    next_agent = state.get("next_agent")

    if next_agent in ("researcher", "analyzer", "executor", "human_approval"):
        return next_agent

    # FINISH, None, or any unknown value → end the workflow
    return "END"


def route_after_approval(state: WorkflowState) -> str:
    """Routes out of the ``human_approval`` node based on the approval decision.

    After a human calls the approval/rejection API the graph is resumed with
    the updated ``approval_status`` in state.
    """
    approval_status = state.get("approval_status")

    if approval_status == "approved":
        return "executor"

    # rejected, expired, pending, or any other status → end workflow
    return "END"
