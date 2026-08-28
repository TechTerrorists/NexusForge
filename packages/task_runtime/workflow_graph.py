"""Validation and compilation for the deliberately small v1 workflow DSL."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


ALLOWED_NODE_TYPES = frozenset(
    {
        "start",
        "http_request",
        "map",
        "condition",
        "foreach",
        "approval",
        "command",
        "notification",
        "llm",
        "agent",
        "end",
        # Legacy visual nodes compile as deterministic mappings.
        "task",
    }
)
WRITE_NODE_TYPES = frozenset({"http_request", "command", "notification", "agent"})


@dataclass(frozen=True)
class CompiledStep:
    key: str
    title: str
    node_type: str
    depends_on: list[str]
    config: dict[str, Any]
    requires_approval: bool


class GraphValidationError(ValueError):
    pass


def validate_graph(graph: dict[str, Any]) -> list[str]:
    """Return validation errors instead of accepting arbitrary React Flow data."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["nodes and edges must be arrays"]
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    errors: list[str] = []
    if len(ids) != len(set(ids)) or any(not node_id for node_id in ids):
        errors.append("every node needs a unique id")
    types = {node.get("id"): node.get("type") for node in nodes if isinstance(node, dict)}
    unknown = sorted({str(kind) for kind in types.values() if kind not in ALLOWED_NODE_TYPES})
    if unknown:
        errors.append(f"unsupported node types: {', '.join(unknown)}")
    starts = [node_id for node_id, kind in types.items() if kind == "start"]
    ends = [node_id for node_id, kind in types.items() if kind == "end"]
    if len(starts) != 1:
        errors.append("a workflow must contain exactly one start node")
    if not ends:
        errors.append("a workflow must contain at least one end node")
    adjacency: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, int] = defaultdict(int)
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("every edge must be an object")
            continue
        source, target = edge.get("source"), edge.get("target")
        if source not in types or target not in types:
            errors.append("edges must reference existing nodes")
            continue
        adjacency[source].append(target)
        incoming[target] += 1
    if starts:
        reachable: set[str] = set()
        queue = deque(starts)
        while queue:
            node_id = queue.popleft()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            queue.extend(adjacency[node_id])
        unreachable = set(types) - reachable
        if unreachable:
            errors.append(f"unreachable nodes: {', '.join(sorted(unreachable))}")
    reverse: dict[str, list[str]] = defaultdict(list)
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].append(source)
    can_reach_end: set[str] = set()
    queue = deque(ends)
    while queue:
        node_id = queue.popleft()
        if node_id in can_reach_end:
            continue
        can_reach_end.add(node_id)
        queue.extend(reverse[node_id])
    dead_ends = set(types) - can_reach_end
    if dead_ends:
        errors.append(f"nodes without a path to end: {', '.join(sorted(dead_ends))}")
    indegree = {node_id: incoming[node_id] for node_id in types}
    queue = deque(node_id for node_id, value in indegree.items() if value == 0)
    visited = 0
    while queue:
        node_id = queue.popleft()
        visited += 1
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(types):
        errors.append("cycles are not supported in v1 workflows")
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") not in WRITE_NODE_TYPES:
            continue
        predecessors = {edge.get("source") for edge in edges if edge.get("target") == node.get("id")}
        if not any(types.get(predecessor) == "approval" for predecessor in predecessors):
            errors.append(f"{node.get('type')} node '{node.get('id')}' requires a preceding approval node")
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data", {})
        if node.get("type") == "foreach" and int(data.get("max_items", 0) or 0) not in range(1, 101):
            errors.append(f"foreach node '{node.get('id')}' requires max_items between 1 and 100")
        if node.get("type") == "http_request" and not data.get("allowed_domains"):
            errors.append(f"http_request node '{node.get('id')}' requires an allowed_domains list")
        if node.get("type") == "http_request" and str(data.get("method", "GET")).upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            errors.append(f"http_request node '{node.get('id')}' uses an unsupported method")
        if node.get("type") == "notification" and (not data.get("url") or not data.get("allowed_domains")):
            errors.append(f"notification node '{node.get('id')}' requires url and allowed_domains")
        if node.get("type") == "command" and (not isinstance(data.get("argv"), list) or not data.get("argv") or not all(isinstance(part, str) and part for part in data.get("argv", []))):
            errors.append(f"command node '{node.get('id')}' requires an argv array")
        if node.get("type") in {"llm", "agent"} and not str(data.get("prompt", "")).strip():
            errors.append(f"{node.get('type')} node '{node.get('id')}' requires a prompt")
        if node.get("type") == "agent" and not str(data.get("role", "")).strip():
            errors.append(f"agent node '{node.get('id')}' requires a workforce role slug")
    return errors


def compile_graph(graph: dict[str, Any]) -> list[CompiledStep]:
    errors = validate_graph(graph)
    if errors:
        raise GraphValidationError("; ".join(errors))
    nodes = {node["id"]: node for node in graph["nodes"]}
    deps: dict[str, list[str]] = defaultdict(list)
    for edge in graph["edges"]:
        deps[edge["target"]].append(edge["source"])
    edge_conditions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph["edges"]:
        if isinstance(edge.get("data"), dict) and "when" in edge["data"]:
            edge_conditions[edge["target"]].append(
                {"source": edge["source"], "when": bool(edge["data"]["when"])}
            )
    return [
        CompiledStep(
            key=node_id,
            title=str(node.get("data", {}).get("label") or node_id),
            node_type=str(node["type"]),
            depends_on=[dependency for dependency in deps[node_id] if nodes[dependency]["type"] != "start"],
            config={**dict(node.get("data", {})), "_incoming_conditions": edge_conditions[node_id]},
            requires_approval=node["type"] in {"approval", "notification"},
        )
        for node_id, node in nodes.items()
        if node["type"] not in {"start", "end"}
    ]
