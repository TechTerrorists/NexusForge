import asyncio
import random
import time
from typing import Any


class ConnectorError(Exception):
    """Base exception for connector errors."""
    pass


class RetryableError(ConnectorError):
    """Error that can be retried (e.g., rate limits, server errors)."""
    pass


class PermanentError(ConnectorError):
    """Non-retryable error (e.g., bad request, auth failure)."""
    pass


class ConnectorDisabled(ConnectorError):
    """Raised when attempting to use a connector that is disabled."""
    pass


class BaseConnector:
    """Base class for all external service connectors with retry logic and mock fallback."""
    
    vendor: str = "base"
    timeout_seconds: float = 30.0
    retryable_status: frozenset = frozenset({429, 502, 503, 504})
    max_attempts: int = 3

    def __init__(self, token: str | None = None, base_url: str = "", **kwargs):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.enabled = bool(token)
        self._extra = kwargs

    def is_enabled(self) -> bool:
        return self.enabled

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def _mock_response(self, method: str, path: str) -> dict:
        return {"mock": True, "vendor": self.vendor, "method": method, "path": path}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json: dict = None,
        extra_headers: dict = None,
    ) -> dict:
        if not self.is_enabled():
            return self._mock_response(method, path)

        import httpx

        url = f"{self.base_url}{path}"
        headers = {**self.auth_header(), **(extra_headers or {})}

        last_error = None
        for attempt in range(self.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.request(
                        method, url, params=params, json=json, headers=headers
                    )

                    if response.status_code in self.retryable_status:
                        retry_after = self._parse_retry_after(response)
                        delay = retry_after or self._backoff_seconds(attempt)
                        await asyncio.sleep(delay)
                        last_error = RetryableError(f"Status {response.status_code}")
                        continue

                    if response.status_code >= 400:
                        raise PermanentError(
                            f"Status {response.status_code}: {response.text[:500]}"
                        )

                    return (
                        response.json()
                        if response.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else {"status": "ok", "data": response.text}
                    )
            except (RetryableError, httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                delay = self._backoff_seconds(attempt)
                await asyncio.sleep(delay)
            except Exception as e:
                raise PermanentError(str(e))

        raise last_error or ConnectorError("Max retries exceeded")

    def _backoff_seconds(self, attempt: int) -> float:
        base = min(2 ** attempt, 30)
        return base * (0.5 + random.random() * 0.5)

    def _parse_retry_after(self, response) -> float | None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return None

    async def get(self, path: str, **kwargs) -> dict:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict:
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> dict:
        return await self._request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> dict:
        return await self._request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> dict:
        return await self._request("DELETE", path, **kwargs)
