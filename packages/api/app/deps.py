"""Shared FastAPI dependency helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_active_user, get_current_user, require_role
from app.models import User


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_db — use in routers that need a short name."""
    async for session in get_db():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]
