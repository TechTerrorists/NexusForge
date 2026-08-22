from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.database import async_session_factory, init_engine
from app.models import AuditAction, AuditLog, RiskLevel


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

        try:
            await self._write_audit_log(
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
            )
        except Exception:
            pass

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
        elif status_code >= 400:
            risk_level = RiskLevel.MEDIUM
        elif action in (AuditAction.DELETE, AuditAction.EXECUTE):
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
            created_at=datetime.now(timezone.utc),
        )

        if async_session_factory is None:
            init_engine()

        async with async_session_factory()() as session:  # type: ignore[union-attr]
            session.add(audit_log)
            await session.commit()
