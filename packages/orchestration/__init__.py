"""NexusForge orchestration engine — multi-agent workflow orchestration primitives."""

from packages.orchestration.state import (
    WorkflowState,
    create_per_agent_channel,
    create_per_agent_channels,
)
from packages.orchestration.graph.builder import build_workflow_graph
from packages.orchestration.graph.edges import route_from_supervisor, route_after_approval
from packages.orchestration.graph.nodes import build_node_factory
from packages.orchestration.supervisor.router import SupervisorRouter, RoutingDecision
from packages.orchestration.patterns.sequential import SequentialPattern
from packages.orchestration.patterns.concurrent import ConcurrentPattern
from packages.orchestration.patterns.handoff import HandoffPattern
from packages.orchestration.patterns.group_chat import GroupChatPattern
from packages.orchestration.patterns.magentic import MagenticPattern
from packages.orchestration.switching.saga import AgentSwitchingSaga, SwitchPolicy, SwitchResult

__all__ = [
    "WorkflowState",
    "create_per_agent_channel",
    "create_per_agent_channels",
    "build_workflow_graph",
    "route_from_supervisor",
    "route_after_approval",
    "build_node_factory",
    "SupervisorRouter",
    "RoutingDecision",
    "SequentialPattern",
    "ConcurrentPattern",
    "HandoffPattern",
    "GroupChatPattern",
    "MagenticPattern",
    "AgentSwitchingSaga",
    "SwitchPolicy",
    "SwitchResult",
]
