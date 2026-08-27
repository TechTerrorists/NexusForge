from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import datetime


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
from packages.handoff.redis_streams import RedisMessageBus
from packages.task_runtime.scheduler import TaskScheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    warnings = settings.validate_production_posture()
    for warning in warnings:
        logger.warning("PRODUCTION POSTURE: %s", warning)

    init_engine()
    await init_db()
    from app.database import async_session_factory
    assert async_session_factory is not None

    message_bus = RedisMessageBus(settings.redis.url)
    try:
        await message_bus.connect()
        app.state.message_bus = message_bus
    except Exception:
        logger.warning("Redis unavailable, running without message bus")
        message_bus = None
        app.state.message_bus = None

    app.state.task_scheduler = TaskScheduler(async_session_factory, message_bus=message_bus)

    try:
        from sqlalchemy import select as sa_select
        from app.models import ExecutionStatus, WorkflowRun
        async with async_session_factory() as db:
            orphaned = (await db.scalars(
                sa_select(WorkflowRun).where(WorkflowRun.status == ExecutionStatus.RUNNING)
            )).all()
            for run in orphaned:
                run.status = ExecutionStatus.FAILED
                run.error = "Run interrupted: server restarted while execution was in progress."
                run.completed_at = datetime.utcnow()
            if orphaned:
                await db.commit()
                logger.warning("Recovered %d orphaned RUNNING runs (marked as FAILED)", len(orphaned))
    except Exception:
        logger.exception("Failed to recover orphaned runs")

    api_key = settings.opencode_llm.api_key.get_secret_value()
    if api_key:
        try:
            from pathlib import Path
            from sqlalchemy import select
            from app.models import SkillVersion
            from packages.task_runtime.skill_importer import import_skills

            async with async_session_factory() as db:
                count = (await db.scalar(select(SkillVersion.id))) if False else len(
                    (await db.scalars(select(SkillVersion))).all()
                )
            if count == 0:
                agency_path = os.getenv("NEXUSFORGE_AGENCY_AGENTS_PATH", "/opt/agency-agents")
                source = Path(agency_path)
                if source.is_dir():
                    result = await import_skills(
                        async_session_factory, source,
                        api_key=api_key,
                        base_url=settings.opencode_llm.base_url or None,
                    )
                    logger.info("Auto-imported skills: %s", result)
        except Exception:
            logger.exception("Skill auto-import failed")

    logger.info(
        "NexusForge API started | env=%s | version=%s",
        settings.environment,
        settings.version,
    )

    yield

    if message_bus and hasattr(message_bus, "close") and message_bus._client:
        await message_bus.close()
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
