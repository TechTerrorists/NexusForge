from __future__ import annotations

import json
import uuid

import pytest
from packages.task_runtime.opencode import OpenCodeRunner, _event_text_parts, _event_usage

from app.llm_runtime import (
    decrypt_api_key,
    encrypt_api_key,
    get_tenant_llm_config,
    save_tenant_llm_config,
)
from app.models import Tenant


class FakeSession:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.flush_count = 0

    async def get(self, model: type[Tenant], tenant_id: uuid.UUID) -> Tenant | None:
        assert model is Tenant
        return self.tenant if self.tenant.id == tenant_id else None

    async def flush(self) -> None:
        self.flush_count += 1


def make_tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(),
        name="Test tenant",
        slug=f"test-{uuid.uuid4()}",
        settings={},
    )


def test_api_key_encryption_round_trip() -> None:
    encrypted = encrypt_api_key("provider-secret")

    assert encrypted != "provider-secret"
    assert decrypt_api_key(encrypted) == "provider-secret"


@pytest.mark.asyncio
async def test_saving_profile_without_key_keeps_environment_key_inherited() -> None:
    tenant = make_tenant()
    session = FakeSession(tenant)

    saved = await save_tenant_llm_config(
        session,  # type: ignore[arg-type]
        tenant.id,
        provider="OpenCode Zen",
        adapter="openai-compatible",
        endpoint="https://opencode.ai/zen/v1",
        model="model-from-settings",
        api_key=None,
    )

    assert "api_key_encrypted" not in tenant.settings["llm_provider"]
    assert saved.model == "model-from-settings"
    assert saved.source == "database"


@pytest.mark.asyncio
async def test_saved_key_is_encrypted_preserved_and_clearable() -> None:
    tenant = make_tenant()
    session = FakeSession(tenant)

    saved = await save_tenant_llm_config(
        session,  # type: ignore[arg-type]
        tenant.id,
        provider="OpenRouter",
        adapter="openai-compatible",
        endpoint="https://openrouter.ai/api/v1/",
        model="openai/gpt-4.1-mini",
        api_key="provider-secret",
    )

    encrypted = tenant.settings["llm_provider"]["api_key_encrypted"]
    assert saved.api_key == "provider-secret"
    assert saved.source == "database"
    assert encrypted != "provider-secret"
    assert decrypt_api_key(encrypted) == "provider-secret"

    preserved = await save_tenant_llm_config(
        session,  # type: ignore[arg-type]
        tenant.id,
        provider="OpenRouter",
        adapter="openai-compatible",
        endpoint="https://openrouter.ai/api/v1",
        model="anthropic/claude-sonnet-4",
        api_key=None,
    )
    assert preserved.api_key == "provider-secret"

    cleared = await save_tenant_llm_config(
        session,  # type: ignore[arg-type]
        tenant.id,
        provider="Local Ollama",
        adapter="openai-compatible",
        endpoint="http://host.docker.internal:11434/v1",
        model="qwen3",
        api_key=None,
        clear_api_key=True,
    )
    assert cleared.api_key == ""
    assert tenant.settings["llm_provider"]["api_key_encrypted"] is None
    assert session.flush_count == 3


@pytest.mark.asyncio
async def test_explicitly_empty_saved_key_does_not_use_environment_fallback() -> None:
    tenant = make_tenant()
    tenant.settings = {
        "llm_provider": {
            "provider": "Local vLLM",
            "adapter": "openai-compatible",
            "endpoint": "http://host.docker.internal:8001/v1",
            "model": "local-model",
            "api_key_encrypted": None,
        }
    }

    config = await get_tenant_llm_config(
        FakeSession(tenant),  # type: ignore[arg-type]
        tenant.id,
    )

    assert config.api_key == ""
    assert config.source == "database"


def test_opencode_provider_config_uses_selected_adapter_and_model() -> None:
    raw = OpenCodeRunner()._provider_config(
        provider="Anthropic",
        adapter="anthropic",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-4-20250514",
    )

    config = json.loads(raw)["provider"]["nexusforge"]
    assert config["npm"] == "@ai-sdk/anthropic"
    assert config["options"]["baseURL"] == "https://api.anthropic.com"
    assert config["options"]["apiKey"] == "{env:NEXUSFORGE_OPENCODE_API_KEY}"
    assert "claude-sonnet-4-20250514" in config["models"]


def test_opencode_openrouter_config_uses_builtin_provider() -> None:
    runner = OpenCodeRunner()

    assert runner._is_openrouter("OpenRouter", "https://openrouter.ai/api/v1")
    config = json.loads(runner._openrouter_config("openrouter/nvidia/nemotron"))

    assert "nvidia/nemotron" in config["provider"]["openrouter"]["models"]
    assert "openrouter/nvidia/nemotron" not in config["provider"]["openrouter"]["models"]
    assert "nexusforge" not in config["provider"]


def test_opencode_failure_reports_structured_error_and_strips_ansi() -> None:
    message = OpenCodeRunner._failure_message(
        "OpenCode sandbox",
        [
            {
                "type": "error",
                "error": {
                    "data": {"ref": "err_example", "message": "Provider rejected model"}
                },
            }
        ],
        '\x1b[93magent "missing" not found\x1b[0m',
    )

    assert message == (
        'OpenCode sandbox failed: Provider rejected model; reference err_example; '
        'agent "missing" not found'
    )


def test_current_opencode_jsonl_extracts_nested_text_and_usage() -> None:
    events = [
        {
            "type": "text",
            "part": {"type": "text", "text": "Repository analysis complete."},
        },
        {
            "type": "step_finish",
            "part": {
                "type": "step-finish",
                "cost": 0.125,
                "tokens": {"input": 120, "output": 30, "reasoning": 10},
            },
        },
    ]

    assert _event_text_parts(events[0]) == ["Repository analysis complete."]
    assert _event_usage(events) == (160, 0.125)
