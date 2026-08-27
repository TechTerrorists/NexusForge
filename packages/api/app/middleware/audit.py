from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

import app.database as _db
from app.models import AuditAction, AuditLog, RiskLevel

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/redoc", "/openapi.json"})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.audit_id = request_id
        start_time = time.monotonic()

        client_ip = self._extract_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        action = self._determine_action(request.method)
        resource_type = self._extract_resource_type(request.url.path)

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start_time) * 1000)

        asyncio.create_task(self._write_audit_log(
            request_id=request_id,
            action=action,
            resource_type=resource_type,
            resource_id=self._extract_resource_id(request.url.path),
            ip_address=client_ip,
            user_agent=user_agent,
            status_code=response.status_code,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        ))

        response.headers["X-Request-ID"] = request_id
        return response

    def _extract_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"

    def _determine_action(self, method: str) -> AuditAction:
        method_map = {
            "GET": AuditAction.READ,
            "HEAD": AuditAction.READ,
            "OPTIONS": AuditAction.READ,
            "POST": AuditAction.CREATE,
            "PUT": AuditAction.UPDATE,
            "PATCH": AuditAction.UPDATE,
            "DELETE": AuditAction.DELETE,
        }
        return method_map.get(method, AuditAction.READ)

    def _extract_resource_type(self, path: str) -> str:
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) >= 3:
            return parts[2] if parts[0] == "api" else parts[1]
        if len(parts) >= 2:
            return parts[-1]
        return "unknown"

    def _extract_resource_id(self, path: str) -> str | None:
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) >= 4 and parts[0] == "api":
            potential_id = parts[3]
            try:
                uuid.UUID(potential_id)
                return potential_id
            except ValueError:
                pass
        return None

    async def _write_audit_log(
        self,
        request_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str | None,
        ip_address: str,
        user_agent: str,
        status_code: int,
        method: str,
        path: str,
        duration_ms: int,
    ) -> None:
        risk_level = RiskLevel.LOW
        if status_code >= 500:
            risk_level = RiskLevel.HIGH
        elif status_code >= 400 or action in (AuditAction.DELETE, AuditAction.EXECUTE):
            risk_level = RiskLevel.MEDIUM

        audit_log = AuditLog(
            id=uuid.UUID(request_id) if len(request_id) == 36 else uuid.uuid4(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            risk_level=risk_level,
            details={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
            # AuditLog.created_at is a PostgreSQL TIMESTAMP WITHOUT TIME ZONE.
            # Keep the value in UTC, but naive, like the rest of the models.
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )

        if _db.async_session_factory is None:
            _db.init_engine()

        try:
            async with _db.async_session_factory() as session:
                session.add(audit_log)
                await session.commit()
        except Exception:
            # Auditing must never break an otherwise successful API request or
            # leak an unhandled task exception into the event loop.
            logger.exception(
                "Failed to write audit log for %s %s (request_id=%s)",
                method,
                path,
                request_id,
            )
