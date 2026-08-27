"""Validation and compilation for the deliberately small v1 workflow DSL."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


ALLOWED_NODE_TYPES = frozenset({"start", "task", "agent", "condition", "approval", "notification", "end"})
WRITE_NODE_TYPES = frozenset({"notification"})


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
    return errors


def compile_graph(graph: dict[str, Any]) -> list[CompiledStep]:
    errors = validate_graph(graph)
    if errors:
        raise GraphValidationError("; ".join(errors))
    nodes = {node["id"]: node for node in graph["nodes"]}
    deps: dict[str, list[str]] = defaultdict(list)
    for edge in graph["edges"]:
        deps[edge["target"]].append(edge["source"])
    return [
        CompiledStep(
            key=node_id,
            title=str(node.get("data", {}).get("label") or node_id),
            node_type=str(node["type"]),
            depends_on=[dependency for dependency in deps[node_id] if nodes[dependency]["type"] != "start"],
            config=dict(node.get("data", {})),
            requires_approval=node["type"] in {"approval", "notification"},
        )
        for node_id, node in nodes.items()
        if node["type"] not in {"start", "end", "condition"}
    ]
