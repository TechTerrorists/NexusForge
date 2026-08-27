from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.models import Tenant

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

LLM_SETTINGS_KEY = "llm_provider"


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    adapter: str
    endpoint: str
    model: str
    api_key: str
    source: str = "environment"


def _cipher() -> Fernet:
    secret = get_settings().auth.secret_key.get_secret_value().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    return _cipher().encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_api_key: str) -> str:
    try:
        return _cipher().decrypt(encrypted_api_key.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("The saved LLM API key cannot be decrypted") from exc


def environment_llm_config() -> LLMRuntimeConfig:
    settings = get_settings()
    return LLMRuntimeConfig(
        provider="OpenCode Zen",
        adapter="openai-compatible",
        endpoint=settings.opencode_llm.base_url,
        model=settings.opencode_llm.model,
        api_key=settings.opencode_llm.api_key.get_secret_value(),
    )


async def get_tenant_llm_config(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> LLMRuntimeConfig:
    fallback = environment_llm_config()
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        return fallback

    stored = (tenant.settings or {}).get(LLM_SETTINGS_KEY)
    if not isinstance(stored, dict):
        return fallback

    # The presence of the field is significant: ``None`` means the tenant
    # deliberately cleared the key and must not silently inherit the process
    # environment's credential.
    api_key = fallback.api_key
    if "api_key_encrypted" in stored:
        encrypted_key = stored.get("api_key_encrypted")
        api_key = ""
        if isinstance(encrypted_key, str) and encrypted_key:
            try:
                api_key = decrypt_api_key(encrypted_key)
            except ValueError:
                logger.exception("Could not decrypt LLM API key for tenant %s", tenant_id)

    return LLMRuntimeConfig(
        provider=str(stored.get("provider") or fallback.provider),
        adapter=str(stored.get("adapter") or fallback.adapter),
        endpoint=str(stored.get("endpoint") or fallback.endpoint),
        model=str(stored.get("model") or fallback.model),
        api_key=api_key,
        source="database",
    )


async def save_tenant_llm_config(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    provider: str,
    adapter: str,
    endpoint: str,
    model: str,
    api_key: str | None,
    clear_api_key: bool = False,
) -> LLMRuntimeConfig:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")

    settings_data = dict(tenant.settings or {})
    previous = settings_data.get(LLM_SETTINGS_KEY)
    previous_data = previous if isinstance(previous, dict) else {}
    key_is_overridden = "api_key_encrypted" in previous_data
    encrypted_key = previous_data.get("api_key_encrypted")
    if clear_api_key:
        encrypted_key = None
        key_is_overridden = True
    elif api_key:
        encrypted_key = encrypt_api_key(api_key)
        key_is_overridden = True

    provider_settings = {
        "provider": provider,
        "adapter": adapter,
        "endpoint": endpoint.rstrip("/"),
        "model": model,
    }
    if key_is_overridden:
        provider_settings["api_key_encrypted"] = encrypted_key
    settings_data[LLM_SETTINGS_KEY] = provider_settings
    tenant.settings = settings_data
    await db.flush()
    return await get_tenant_llm_config(db, tenant_id)
