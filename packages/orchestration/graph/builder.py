"""LangGraph StateGraph builder — hub-and-spoke topology for NexusForge.

Architecture:
  supervisor ──→ researcher ──┐
       ↑          analyzer ──┤
       └──────── executor  ──┘
       └──→ human_approval ──→ executor | END

The supervisor acts as the central router.  All workers return to supervisor.
Human approval is an ``interrupt_before`` node — graph suspends until resumed.
PostgreSQL checkpointer provides durable state across API worker restarts.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from packages.orchestration.graph.edges import route_after_approval, route_from_supervisor
from packages.orchestration.graph.nodes import build_node_factory
from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)

# Default agent names used by the hub-and-spoke topology.
_DEFAULT_AGENTS = ("researcher", "analyzer", "executor")

# Human-approval node name (convention).
HUMAN_APPROVAL_NODE = "human_approval"
SUPERVISOR_NODE = "supervisor"


def _get_domain_prompts(workflow_type: str) -> dict[str, str]:
    """Load prompt overrides for a workflow domain.

    Returns an empty dict when ``workflow_type`` has no overrides, which
    causes each agent to use its built-in default prompt.
    """
    overrides: dict[str, str] = {}
    try:
        if workflow_type == "support_ops":
            from packages.orchestration.workflows.support_ops_prompts import PROMPTS

            overrides = PROMPTS
        elif workflow_type == "finance_recon":
            from packages.orchestration.workflows.finance_recon_prompts import PROMPTS

            overrides = PROMPTS
    except ImportError:
        pass
    return overrides


def build_workflow_graph(
    *,
    workflow_type: str = "general",
    agents: dict[str, Any] | None = None,
    checkpointer: Any | None = None,
    interrupt_before: list[str] | None = None,
    prompt_overrides: dict[str, str] | None = None,
) -> Any:
    """Build and compile a LangGraph StateGraph with hub-and-spoke topology.

    Args:
        workflow_type: Domain name used to select prompt overrides.
        agents: Mapping of agent name -> agent instance.  Must contain at
            least ``supervisor``.  Workers default to ``_DEFAULT_AGENTS`` if
            not supplied (node factory is used instead).
        checkpointer: Optional LangGraph checkpointer for durable state.
        interrupt_before: Node names that trigger human-in-the-loop pauses.
            Defaults to ``["human_approval"]``.
        prompt_per_domain: Per-domain prompt overrides keyed by agent name.

    Returns:
        Compiled ``StateGraph`` ready for ``ainvoke`` / ``astream``.
    """
    agents = agents or {}

    # Prompt resolution: explicit overrides > domain defaults > agent defaults
    domain_prompts = _get_domain_prompts(workflow_type)
    effective_prompts: dict[str, str] = {**domain_prompts}
    if prompt_overrides:
        effective_prompts.update(prompt_overrides)

    # Build node closures — these bind to the provided agent instances (or
    # create lightweight stub agents when none are supplied).
    nodes = build_node_factory(
        supervisor=agents.get(SUPERVISOR_NODE),
        prompt_overrides=effective_prompts,
    )

    # ------------------------------------------------------------------ #
    # Build the StateGraph                                                 #
    # ------------------------------------------------------------------ #
    builder = StateGraph(WorkflowState)

    # Register nodes
    builder.add_node(SUPERVISOR_NODE, nodes[SUPERVISOR_NODE])
    for agent_name in _DEFAULT_AGENTS:
        builder.add_node(agent_name, nodes[agent_name])
    builder.add_node(HUMAN_APPROVAL_NODE, nodes[HUMAN_APPROVAL_NODE])

    # Entry point
    builder.set_entry_point(SUPERVISOR_NODE)

    # Supervisor -> conditional routing
    builder.add_conditional_edges(
        SUPERVISOR_NODE,
        route_from_supervisor,
        {
            "researcher": "researcher",
            "analyzer": "analyzer",
            "executor": "executor",
            "human_approval": HUMAN_APPROVAL_NODE,
            "END": END,
        },
    )

    # All workers return to supervisor (hub-and-spoke)
    for agent_name in _DEFAULT_AGENTS:
        builder.add_edge(agent_name, SUPERVISOR_NODE)

    # Human approval -> conditional routing (approved → executor, else END)
    builder.add_conditional_edges(
        HUMAN_APPROVAL_NODE,
        route_after_approval,
        {"executor": "executor", "END": END},
    )

    # ------------------------------------------------------------------ #
    # Compile                                                              #
    # ------------------------------------------------------------------ #
    compile_kwargs: dict[str, Any] = {}
    if interrupt_before is not None:
        compile_kwargs["interrupt_before"] = interrupt_before
    else:
        compile_kwargs["interrupt_before"] = [HUMAN_APPROVAL_NODE]

    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    graph = builder.compile(**compile_kwargs)
    logger.info(
        "Workflow graph compiled | type=%s | nodes=%s",
        workflow_type,
        list(builder.nodes),
    )
    return graph
