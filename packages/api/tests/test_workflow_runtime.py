from __future__ import annotations

from datetime import UTC, datetime

import pytest

from packages.task_runtime.cron import next_cron_fire
from packages.task_runtime.workflow_graph import compile_graph, validate_graph


def test_deterministic_graph_compiles_typed_nodes() -> None:
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "map", "type": "map", "data": {"mapping": {"name": "{{ input.name }}"}}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "map"},
            {"source": "map", "target": "end"},
        ],
    }

    assert validate_graph(graph) == []
    assert [step.key for step in compile_graph(graph)] == ["map"]


def test_side_effect_node_requires_approval() -> None:
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {
                "id": "http",
                "type": "http_request",
                "data": {"url": "https://example.com", "allowed_domains": ["example.com"]},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "http"},
            {"source": "http", "target": "end"},
        ],
    }

    assert any("requires a preceding approval" in error for error in validate_graph(graph))


def test_timezone_aware_cron_returns_utc_naive_storage_time() -> None:
    after = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
    result = next_cron_fire("30 12 * * *", "Asia/Kolkata", after)

    assert result == datetime(2026, 8, 27, 7, 0)
    assert result.tzinfo is None


def test_invalid_cron_is_rejected() -> None:
    with pytest.raises(ValueError):
        next_cron_fire("not a cron", "UTC")
