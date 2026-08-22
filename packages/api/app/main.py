from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.database import close_db, init_db, init_engine
from app.middleware import (
    AuditMiddleware,
    RateLimitMiddleware,
    RBACMiddleware,
    SecurityHeadersMiddleware,
    SecurityMiddleware,
)
from app.routers import all_routers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    warnings = settings.validate_production_posture()
    for warning in warnings:
        logger.warning("PRODUCTION POSTURE: %s", warning)

    init_engine()
    await init_db()

    logger.info(
        "NexusForge API started | env=%s | version=%s",
        settings.environment,
        settings.version,
    )

    yield

    await close_db()
    logger.info("NexusForge API shut down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="NexusForge AI-powered enterprise multi-agent workflow orchestration platform",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]
    app.add_middleware(RBACMiddleware)  # type: ignore[arg-type]
    app.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]
    app.add_middleware(SecurityMiddleware)  # type: ignore[arg-type]
    app.add_middleware(AuditMiddleware)  # type: ignore[arg-type]

    for router in all_routers:
        app.include_router(router)

    if settings.observability.metrics_enabled:
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "version": settings.version, "environment": settings.environment}

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "Resource not found"},
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else 4,
        log_level="debug" if settings.debug else "info",
    )
