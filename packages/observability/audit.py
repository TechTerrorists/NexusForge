import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    id: int = 0
    request_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    role: str = ""
    method: str = ""
    path: str = ""
    status_code: int = 0
    outcome: str = ""
    latency_ms: float = 0.0
    client_ip: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


class AuditLogger:
    def __init__(self, db_session_factory=None):
        self._db_session_factory = db_session_factory
        self._in_memory_log: list[dict[str, Any]] = []

    async def log(
        self,
        request_id: str,
        user_id: str,
        tenant_id: str,
        role: str,
        method: str,
        path: str,
        status_code: int,
        outcome: str,
        latency_ms: float,
        client_ip: str,
        metadata: dict[str, Any] = None
    ) -> None:
        """Log an audit entry."""
        entry = {
            "request_id": request_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "role": role,
            "method": method,
            "path": path,
            "status_code": status_code,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "client_ip": client_ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {}
        }
        
        self._in_memory_log.append(entry)
        
        if self._db_session_factory:
            try:
                await self._persist_to_db(entry)
            except Exception as e:
                logger.error(f"Failed to persist audit log to database: {e}")
        
        logger.info(
            f"Audit: {method} {path} - {status_code} ({outcome}) "
            f"[{latency_ms:.2f}ms] user={user_id} tenant={tenant_id}"
        )

    async def _persist_to_db(self, entry: dict[str, Any]) -> None:
        """Persist audit entry to database."""
        if not self._db_session_factory:
            return
        
        async with self._db_session_factory() as session:
            await session.execute(
                """
                INSERT INTO audit_logs 
                (request_id, user_id, tenant_id, role, method, path, 
                 status_code, outcome, latency_ms, client_ip, timestamp, metadata)
                VALUES (:request_id, :user_id, :tenant_id, :role, :method, :path,
                        :status_code, :outcome, :latency_ms, :client_ip, :timestamp, :metadata)
                """,
                {
                    "request_id": entry["request_id"],
                    "user_id": entry["user_id"],
                    "tenant_id": entry["tenant_id"],
                    "role": entry["role"],
                    "method": entry["method"],
                    "path": entry["path"],
                    "status_code": entry["status_code"],
                    "outcome": entry["outcome"],
                    "latency_ms": entry["latency_ms"],
                    "client_ip": entry["client_ip"],
                    "timestamp": entry["timestamp"],
                    "metadata": json.dumps(entry["metadata"])
                }
            )
            await session.commit()

    async def query(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query audit logs with optional filters."""
        if self._db_session_factory:
            try:
                return await self._query_from_db(tenant_id, start_date, end_date, limit)
            except Exception as e:
                logger.error(f"Failed to query audit logs from database: {e}")
        
        return self._query_from_memory(tenant_id, start_date, end_date, limit)

    async def _query_from_db(
        self,
        tenant_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        limit: int
    ) -> list[dict[str, Any]]:
        """Query audit logs from database."""
        if not self._db_session_factory:
            return []
        
        query = "SELECT * FROM audit_logs WHERE tenant_id = :tenant_id"
        params = {"tenant_id": tenant_id, "limit": limit}
        
        if start_date:
            query += " AND timestamp >= :start_date"
            params["start_date"] = start_date.isoformat()
        
        if end_date:
            query += " AND timestamp <= :end_date"
            params["end_date"] = end_date.isoformat()
        
        query += " ORDER BY timestamp DESC LIMIT :limit"
        
        async with self._db_session_factory() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()
            return [dict(row) for row in rows]

    def _query_from_memory(
        self,
        tenant_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        limit: int
    ) -> list[dict[str, Any]]:
        """Query audit logs from in-memory storage."""
        filtered = [
            entry for entry in self._in_memory_log
            if entry["tenant_id"] == tenant_id
        ]
        
        if start_date:
            filtered = [
                entry for entry in filtered
                if datetime.fromisoformat(entry["timestamp"]) >= start_date
            ]
        
        if end_date:
            filtered = [
                entry for entry in filtered
                if datetime.fromisoformat(entry["timestamp"]) <= end_date
            ]
        
        filtered.sort(key=lambda x: x["timestamp"], reverse=True)
        return filtered[:limit]

    def get_stats(self, tenant_id: str = None) -> dict[str, Any]:
        """Get audit log statistics."""
        entries = self._in_memory_log
        if tenant_id:
            entries = [e for e in entries if e["tenant_id"] == tenant_id]
        
        if not entries:
            return {"total_entries": 0}
        
        outcomes = {}
        for entry in entries:
            outcome = entry["outcome"]
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        
        latencies = [e["latency_ms"] for e in entries]
        
        return {
            "total_entries": len(entries),
            "outcomes": outcomes,
            "avg_latency_ms": sum(latencies) / len(latencies),
            "max_latency_ms": max(latencies),
            "min_latency_ms": min(latencies)
        }
