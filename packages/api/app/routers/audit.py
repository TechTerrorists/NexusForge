from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..models import AuditLog, User
from ..auth.dependencies import require_role

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditResponse(BaseModel):
    id: str
    request_id: str
    method: str
    path: str
    status_code: int
    outcome: str
    latency_ms: float
    client_ip: str
    created_at: str


@router.get("/", response_model=list[AuditResponse])
async def list_audit_logs(
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        AuditResponse(
            id=str(l.id), request_id=l.request_id, method=l.method, path=l.path,
            status_code=l.status_code, outcome=l.outcome, latency_ms=l.latency_ms,
            client_ip=l.client_ip, created_at=l.created_at.isoformat(),
        )
        for l in logs
    ]
