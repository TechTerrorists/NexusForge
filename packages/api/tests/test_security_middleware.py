from __future__ import annotations

import json

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.security import SecurityMiddleware


@pytest.mark.asyncio
async def test_security_middleware_does_not_mutate_uuid_or_email() -> None:
    payload = {
        "repository_id": "80fd35ea-1392-4044-9ce1-6bb73b2b9c01",
        "email": "person@example.com",
    }
    body = json.dumps(payload).encode()
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/sessions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )
    middleware = SecurityMiddleware(lambda scope, receive, send: None)

    async def call_next(inner_request: Request) -> JSONResponse:
        assert json.loads(await inner_request.body()) == payload
        assert inner_request.state.sanitized_body == {
            "repository_id": "80fd35ea-[REDACTED_PHONE]-9ce1-6bb73b2b9c01",
            "email": "[REDACTED_EMAIL]",
        }
        return JSONResponse({"ok": True})

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
