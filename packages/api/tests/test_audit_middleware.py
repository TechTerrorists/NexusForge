from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.database as database
from app.middleware.audit import AuditMiddleware
from app.models import AuditAction


@pytest.mark.asyncio
async def test_audit_timestamp_matches_naive_database_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    session_factory = MagicMock(return_value=session_context)
    monkeypatch.setattr(database, "async_session_factory", session_factory)

    middleware = AuditMiddleware(MagicMock())
    await middleware._write_audit_log(
        request_id="3c434fc1-c8c4-4482-9e0e-0291fcd00214",
        action=AuditAction.READ,
        resource_type="runs",
        resource_id=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
        status_code=200,
        method="GET",
        path="/api/v1/runs",
        duration_ms=1,
    )

    audit_log = session.add.call_args.args[0]
    assert audit_log.created_at.tzinfo is None
    session.commit.assert_awaited_once()
