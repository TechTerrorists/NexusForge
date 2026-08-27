from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth.jwt import TokenPayload, verify_token

OPEN_PATHS = frozenset({"/", "/health", "/openapi.json", "/docs", "/redoc", "/metrics", "/login"})
PUBLIC_API_PATHS = frozenset({"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/refresh"})

ROUTE_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "GET": {
        "/api/v1/auth": ["owner", "admin", "editor", "viewer"],
        "/api/v1/agents": ["owner", "admin", "editor", "viewer"],
        "/api/v1/workflows": ["owner", "admin", "editor", "viewer"],
        "/api/v1/knowledge": ["owner", "admin", "editor", "viewer"],
        "/api/v1/tools": ["owner", "admin", "editor", "viewer"],
        "/api/v1/skills": ["owner", "admin", "editor", "viewer"],
        "/api/v1/memory": ["owner", "admin", "editor", "viewer"],
        "/api/v1/marketplace": ["owner", "admin", "editor", "viewer"],
        "/api/v1/audit": ["owner", "admin"],
        "/api/v1/metrics": ["owner", "admin", "editor", "viewer"],
        "/api/v1/overview": ["owner", "admin", "editor", "viewer"],
        "/api/v1/runs": ["owner", "admin", "editor", "viewer"],
        "/api/v1/repositories": ["owner", "admin", "editor", "viewer"],
        "/api/v1/chat": ["owner", "admin", "editor", "viewer"],
        "/api/v1/plans": ["owner", "admin", "editor", "viewer"],
        "/api/v1/workflow-graphs": ["owner", "admin", "editor", "viewer"],
        "/api/v1/settings": ["owner", "admin", "editor", "viewer"],
    },
    "POST": {
        "/api/v1/auth": ["owner", "admin", "editor", "viewer"],
        "/api/v1/agents": ["owner", "admin", "editor"],
        "/api/v1/workflows": ["owner", "admin", "editor"],
        "/api/v1/knowledge": ["owner", "admin", "editor"],
        "/api/v1/tools": ["owner", "admin", "editor"],
        "/api/v1/skills": ["owner", "admin", "editor"],
        "/api/v1/memory": ["owner", "admin", "editor"],
        "/api/v1/marketplace": ["owner", "admin"],
        "/api/v1/repositories": ["owner", "admin", "editor"],
        "/api/v1/chat": ["owner", "admin", "editor", "viewer"],
        "/api/v1/plans": ["owner", "admin", "editor"],
        "/api/v1/runs": ["owner", "admin", "editor"],
        "/api/v1/workflow-graphs": ["owner", "admin", "editor"],
    },
    "PUT": {
        "/api/v1/settings": ["owner", "admin", "editor"],
        "/api/v1/agents": ["owner", "admin", "editor"],
        "/api/v1/workflows": ["owner", "admin", "editor"],
        "/api/v1/knowledge": ["owner", "admin", "editor"],
        "/api/v1/tools": ["owner", "admin", "editor"],
        "/api/v1/skills": ["owner", "admin", "editor"],
    },
    "PATCH": {
        "/api/v1/agents": ["owner", "admin", "editor"],
        "/api/v1/workflows": ["owner", "admin", "editor"],
        "/api/v1/knowledge": ["owner", "admin", "editor"],
        "/api/v1/tools": ["owner", "admin", "editor"],
        "/api/v1/skills": ["owner", "admin", "editor"],
    },
    "DELETE": {
        "/api/v1/agents": ["owner", "admin"],
        "/api/v1/workflows": ["owner", "admin"],
        "/api/v1/knowledge": ["owner", "admin"],
        "/api/v1/tools": ["owner", "admin"],
        "/api/v1/skills": ["owner", "admin"],
        "/api/v1/marketplace": ["owner", "admin"],
    },
}


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if request.method in ("OPTIONS", "HEAD"):
            return await call_next(request)

        if path in OPEN_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        if path.startswith("/health") or path.startswith("/metrics"):
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        if path in PUBLIC_API_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]
        try:
            payload: TokenPayload = verify_token(token)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if payload.type != "access":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token type"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if payload.role == "owner":
            request.state.user_id = payload.sub
            request.state.tenant_id = payload.tenant_id
            request.state.user_role = payload.role
            return await call_next(request)

        method = request.method
        allowed_roles = self._get_allowed_roles(method, path)

        if allowed_roles is None:
            return JSONResponse(
                status_code=403,
                content={"detail": f"No permissions defined for {method} {path}"},
            )

        if payload.role not in allowed_roles:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Role '{payload.role}' is not authorized for {method} {path}"
                },
            )

        request.state.user_id = payload.sub
        request.state.tenant_id = payload.tenant_id
        request.state.user_role = payload.role

        return await call_next(request)

    def _get_allowed_roles(self, method: str, path: str) -> list[str] | None:
        method_permissions = ROUTE_PERMISSIONS.get(method, {})

        for route, roles in method_permissions.items():
            if path == route or path.startswith(route + "/"):
                return roles

        return None
