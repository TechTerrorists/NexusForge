from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, require_role
from app.database import get_db
from app.llm_runtime import LLMRuntimeConfig, get_tenant_llm_config, save_tenant_llm_config
from app.models import User, UserRole

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
ActiveUser = Annotated[User, Depends(get_current_active_user)]
SettingsEditor = Annotated[
    User,
    Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
]


class LLMSettingsResponse(BaseModel):
    provider: str
    adapter: str
    endpoint: str
    model: str
    api_key_configured: bool
    api_key_hint: str | None = None
    source: str


class LLMSettingsUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    adapter: Literal["openai-compatible", "anthropic"]
    endpoint: AnyHttpUrl
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False


def _response(config: LLMRuntimeConfig) -> LLMSettingsResponse:
    hint = f"••••{config.api_key[-4:]}" if len(config.api_key) >= 4 else None
    return LLMSettingsResponse(
        provider=config.provider,
        adapter=config.adapter,
        endpoint=config.endpoint,
        model=config.model,
        api_key_configured=bool(config.api_key),
        api_key_hint=hint,
        source=config.source,
    )


@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    db: DatabaseSession,
    user: ActiveUser,
) -> LLMSettingsResponse:
    return _response(await get_tenant_llm_config(db, user.tenant_id))


@router.put("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(
    req: LLMSettingsUpdate,
    db: DatabaseSession,
    user: SettingsEditor,
) -> LLMSettingsResponse:
    try:
        config = await save_tenant_llm_config(
            db,
            user.tenant_id,
            provider=req.provider.strip(),
            adapter=req.adapter,
            endpoint=str(req.endpoint),
            model=req.model.strip(),
            api_key=req.api_key.strip() if req.api_key else None,
            clear_api_key=req.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _response(config)
