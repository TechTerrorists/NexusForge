from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from packages.task_runtime.planner import _decode_json_payload, llm_create_plan


def test_decode_json_payload_accepts_fences_and_leading_commentary() -> None:
    fenced = """```json
{"steps": []}
```"""
    commentary = 'Here is the plan:\n{"steps": []}\nHope this helps.'

    assert _decode_json_payload(fenced) == {"steps": []}
    assert _decode_json_payload(commentary) == {"steps": []}


def test_decode_json_payload_rejects_unterminated_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        _decode_json_payload('{"steps": [{"instructions": "unfinished}')


@pytest.mark.asyncio
async def test_planner_retries_once_when_provider_returns_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        ('{"steps": [{"instructions": "unfinished}', "length"),
        (
            json.dumps(
                {
                    "steps": [
                        {
                            "key": "implement",
                            "title": "Implement the change",
                            "instructions": "Implement and test the requested change.",
                            "skill_slug": "software-engineer",
                            "depends_on": [],
                            "writes_code": True,
                            "nexus_phase": "build",
                            "role": "engineer",
                            "max_retries": 2,
                            "acceptance_criteria": "Tests pass",
                        }
                    ]
                }
            ),
            "stop",
        ),
    ]
    calls: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            content, finish_reason = responses.pop(0)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=content),
                        finish_reason=finish_reason,
                    )
                ]
            )

    class FakeOpenAIClient:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOpenAIClient),
    )
    skills = [
        SimpleNamespace(
            slug="software-engineer",
            name="Software engineer",
            description="Implements software changes",
            division="engineering",
        )
    ]

    plan = await llm_create_plan(
        "Add a feature",
        skills,
        model_provider="openai-compatible",
        model_name="nvidia/nemotron",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        custom_provider=True,
    )

    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.3
    assert calls[1]["temperature"] == 0.0
    assert "previous response was invalid" in calls[1]["messages"][1]["content"]
    assert [step.key for step in plan] == ["implement"]
