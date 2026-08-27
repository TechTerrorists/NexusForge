from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class TokenBucket:
    capacity: int
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        if self.tokens >= 1:
            return 0.0
        needed = 1.0 - self.tokens
        return needed / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        app: object,
        anon_limit: int = 30,
        mutating_limit: int = 60,
        read_limit: int = 600,
        window_seconds: float = 60.0,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.anon_limit = anon_limit
        self.mutating_limit = mutating_limit
        self.read_limit = read_limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=read_limit, refill_rate=read_limit / window_seconds)
        )
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300.0

    def _get_client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return ip

    def _get_or_create_bucket(self, key: str, is_anonymous: bool) -> TokenBucket:
        if key not in self._buckets:
            limit = self.anon_limit if is_anonymous else self.read_limit
            self._buckets[key] = TokenBucket(
                capacity=limit, refill_rate=limit / self.window_seconds
            )
        return self._buckets[key]

    def _cleanup_expired(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        expired_keys = [
            k
            for k, v in self._buckets.items()
            if now - v.last_refill > self.window_seconds * 10
        ]
        for k in expired_keys:
            del self._buckets[k]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in ("/health", "/metrics", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        self._cleanup_expired()

        client_key = self._get_client_key(request)
        is_anonymous = not getattr(request.state, "user_id", None)

        bucket = self._get_or_create_bucket(client_key, is_anonymous)

        if request.method in self.MUTATING_METHODS:
            allowed = bucket.consume(self.mutating_limit // self.anon_limit)
        else:
            allowed = bucket.consume(1)

        if not allowed:
            retry_after = int(bucket.retry_after) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(bucket.capacity),
                    "X-RateLimit-Remaining": str(max(0, int(bucket.tokens))),
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(bucket.capacity)
        response.headers["X-RateLimit-Remaining"] = str(max(0, int(bucket.tokens)))

        return response
