from __future__ import annotations

from starlette.requests import Request

from app.middleware.rate_limit import RateLimitMiddleware


def _request(method: str, path: str, user_id: str | None = None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )
    if user_id:
        request.state.user_id = user_id
    return request


def test_rate_limit_uses_separate_authenticated_traffic_lanes() -> None:
    middleware = RateLimitMiddleware(
        lambda scope, receive, send: None,
        anon_limit=10,
        mutating_limit=20,
        read_limit=100,
        stream_limit=30,
    )

    assert middleware._policy(_request("GET", "/api/v1/runs", "user-1"), False) == (
        "read",
        100,
    )
    assert middleware._policy(
        _request("GET", "/api/v1/runs/id/events", "user-1"), False
    ) == ("stream", 30)
    assert middleware._policy(_request("POST", "/api/v1/runs/id/resume", "user-1"), False) == (
        "mutation",
        20,
    )
    assert middleware._policy(_request("POST", "/api/v1/auth/login"), True) == (
        "mutation",
        10,
    )
