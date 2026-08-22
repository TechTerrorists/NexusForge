from fastapi import APIRouter, Depends, Response
from ..models import User
from ..auth.dependencies import get_current_active_user

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("/prometheus")
async def prometheus_metrics(user: User = Depends(get_current_active_user)):
    from packages.observability.metrics import PrometheusMetrics
    metrics = PrometheusMetrics()
    return Response(content=metrics.get_metrics(), media_type="text/plain")


@router.get("/cost")
async def cost_summary(user: User = Depends(get_current_active_user)):
    return {
        "total_cost_usd": 0.0,
        "budget_limit_usd": 100.0,
        "per_agent": {},
        "per_model": {},
    }


@router.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


@router.get("/health/ready")
async def readiness():
    return {"status": "ready"}
