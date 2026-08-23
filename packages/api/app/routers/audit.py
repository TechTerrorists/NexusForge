from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..models import AuditLog, User, UserRole, AuditAction
from ..auth.dependencies import require_role

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    ip_address: str | None
    risk_level: str
    created_at: str


@router.get("/", response_model=list[AuditResponse])
async def list_audit_logs(
    action: str | None = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER)),
):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        q = q.where(AuditLog.action == action)
    q = q.limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [
        AuditResponse(
            id=str(l.id), user_id=str(l.user_id) if l.user_id else None,
            action=l.action.value, resource_type=l.resource_type,
            resource_id=l.resource_id, details=l.details or {},
            ip_address=l.ip_address, risk_level=l.risk_level.value,
            created_at=l.created_at.isoformat(),
        )
        for l in logs
    ]
