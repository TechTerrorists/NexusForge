from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class SemanticStore:
    """Semantic memory store using pgvector for embedding-based retrieval with TTL support."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create the semantic memory table if it doesn't exist."""
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                embedding vector(1536),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP,
                UNIQUE(tenant_id, namespace, key)
            )
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_semantic_memory_tenant ON semantic_memory(tenant_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_semantic_memory_ns ON semantic_memory(namespace)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_semantic_memory_key ON semantic_memory(tenant_id, namespace, key)
        """))
        self.db.commit()

    def store(
        self,
        tenant_id: str,
        namespace: str,
        key: str,
        value: str,
        embedding: list[float] | None = None,
        metadata: dict | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Store a value with optional embedding and TTL."""
        record_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds else None

        embedding_str = str(embedding) if embedding else None

        self.db.execute(
            text("""
                INSERT INTO semantic_memory (id, tenant_id, namespace, key, value, embedding, metadata, created_at, expires_at)
                VALUES (:id, :tenant_id, :namespace, :key, :value, :embedding, :metadata, :created_at, :expires_at)
                ON CONFLICT (tenant_id, namespace, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at
            """),
            {
                "id": record_id,
                "tenant_id": tenant_id,
                "namespace": namespace,
                "key": key,
                "value": value,
                "embedding": embedding_str,
                "metadata": json.dumps(metadata or {}),
                "created_at": now,
                "expires_at": expires_at,
            },
        )
        self.db.commit()
        return record_id

    def query(
        self,
        tenant_id: str,
        namespace: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Query semantic memory using cosine similarity, excluding expired entries."""
        embedding_str = str(query_embedding)
        results = self.db.execute(
            text("""
                SELECT id, key, value, metadata, created_at, expires_at,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM semantic_memory
                WHERE tenant_id = :tenant_id
                  AND namespace = :namespace
                  AND (expires_at IS NULL OR expires_at > :now)
                ORDER BY embedding <=> :embedding::vector
                LIMIT :top_k
            """),
            {
                "tenant_id": tenant_id,
                "namespace": namespace,
                "embedding": embedding_str,
                "top_k": top_k,
                "now": time.time(),
            },
        ).fetchall()

        return [
            {
                "id": row[0],
                "key": row[1],
                "value": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "created_at": row[4],
                "expires_at": row[5],
                "similarity": float(row[6]),
            }
            for row in results
        ]

    def get(
        self,
        tenant_id: str,
        namespace: str,
        key: str,
    ) -> dict | None:
        """Get a specific value by key, excluding expired entries."""
        row = self.db.execute(
            text("""
                SELECT id, value, metadata, created_at, expires_at
                FROM semantic_memory
                WHERE tenant_id = :tenant_id
                  AND namespace = :namespace
                  AND key = :key
                  AND (expires_at IS NULL OR expires_at > :now)
            """),
            {
                "tenant_id": tenant_id,
                "namespace": namespace,
                "key": key,
                "now": time.time(),
            },
        ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "key": key,
            "value": row[1],
            "metadata": json.loads(row[2]) if row[2] else {},
            "created_at": row[3],
            "expires_at": row[4],
        }

    def delete(self, tenant_id: str, namespace: str, key: str) -> bool:
        """Delete a specific memory entry by key."""
        result = self.db.execute(
            text("""
                DELETE FROM semantic_memory
                WHERE tenant_id = :tenant_id
                  AND namespace = :namespace
                  AND key = :key
            """),
            {"tenant_id": tenant_id, "namespace": namespace, "key": key},
        )
        self.db.commit()
        return result.rowcount > 0

    def delete_namespace(self, tenant_id: str, namespace: str) -> int:
        """Delete all entries in a namespace. Returns count of deleted entries."""
        result = self.db.execute(
            text("""
                DELETE FROM semantic_memory
                WHERE tenant_id = :tenant_id AND namespace = :namespace
            """),
            {"tenant_id": tenant_id, "namespace": namespace},
        )
        self.db.commit()
        return result.rowcount

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of deleted entries."""
        result = self.db.execute(
            text("""
                DELETE FROM semantic_memory
                WHERE expires_at IS NOT NULL AND expires_at < :now
            """),
            {"now": time.time()},
        )
        self.db.commit()
        return result.rowcount

    def list_namespaces(self, tenant_id: str) -> list[str]:
        """List all namespaces for a tenant."""
        rows = self.db.execute(
            text("""
                SELECT DISTINCT namespace
                FROM semantic_memory
                WHERE tenant_id = :tenant_id
                ORDER BY namespace
            """),
            {"tenant_id": tenant_id},
        ).fetchall()
        return [row[0] for row in rows]
