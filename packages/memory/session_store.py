from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class ConversationSessionStore:
    """Persistent conversation session store for agent threads."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create session and message tables."""
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                last_message_at TIMESTAMP
            )
        """))
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                token_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_conv_sessions_agent ON conversation_sessions(agent_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_conv_sessions_thread ON conversation_sessions(thread_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_conv_messages_session ON conversation_messages(session_id)
        """))
        self.db.commit()

    def create_session(
        self,
        agent_id: str,
        thread_id: str,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new conversation session."""
        session_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute(
            text("""
                INSERT INTO conversation_sessions (id, agent_id, thread_id, metadata, created_at, updated_at, last_message_at)
                VALUES (:id, :agent_id, :thread_id, :metadata, :created_at, :updated_at, :last_message_at)
            """),
            {
                "id": session_id,
                "agent_id": agent_id,
                "thread_id": thread_id,
                "metadata": json.dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
                "last_message_at": now,
            },
        )
        self.db.commit()
        return {
            "id": session_id,
            "agent_id": agent_id,
            "thread_id": thread_id,
            "status": "active",
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
        }

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve a session by ID."""
        row = self.db.execute(
            text("""
                SELECT id, agent_id, thread_id, status, metadata, created_at, updated_at, last_message_at
                FROM conversation_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id},
        ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "agent_id": row[1],
            "thread_id": row[2],
            "status": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
            "updated_at": row[6],
            "last_message_at": row[7],
        }

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        token_count: int = 0,
    ) -> dict:
        """Add a message to a session."""
        message_id = str(uuid.uuid4())
        now = time.time()

        self.db.execute(
            text("""
                INSERT INTO conversation_messages (id, session_id, role, content, metadata, token_count, created_at)
                VALUES (:id, :session_id, :role, :content, :metadata, :token_count, :created_at)
            """),
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": json.dumps(metadata or {}),
                "token_count": token_count,
                "created_at": now,
            },
        )

        self.db.execute(
            text("""
                UPDATE conversation_sessions
                SET updated_at = :now, last_message_at = :now
                WHERE id = :session_id
            """),
            {"now": now, "session_id": session_id},
        )
        self.db.commit()

        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "token_count": token_count,
            "created_at": now,
        }

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Retrieve messages for a session with pagination."""
        rows = self.db.execute(
            text("""
                SELECT id, session_id, role, content, metadata, token_count, created_at
                FROM conversation_messages
                WHERE session_id = :session_id
                ORDER BY created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            {"session_id": session_id, "limit": limit, "offset": offset},
        ).fetchall()

        return [
            {
                "id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "token_count": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        result = self.db.execute(
            text("DELETE FROM conversation_sessions WHERE id = :session_id"),
            {"session_id": session_id},
        )
        self.db.commit()
        return result.rowcount > 0

    def list_sessions(
        self,
        agent_id: str | None = None,
        thread_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List sessions with optional filtering."""
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if agent_id:
            conditions.append("agent_id = :agent_id")
            params["agent_id"] = agent_id
        if thread_id:
            conditions.append("thread_id = :thread_id")
            params["thread_id"] = thread_id
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = self.db.execute(
            text(f"""
                SELECT id, agent_id, thread_id, status, metadata, created_at, updated_at, last_message_at
                FROM conversation_sessions
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()

        return [
            {
                "id": row[0],
                "agent_id": row[1],
                "thread_id": row[2],
                "status": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "created_at": row[5],
                "updated_at": row[6],
                "last_message_at": row[7],
            }
            for row in rows
        ]

    def close_session(self, session_id: str) -> dict | None:
        """Mark a session as closed."""
        now = time.time()
        self.db.execute(
            text("""
                UPDATE conversation_sessions
                SET status = 'closed', updated_at = :now
                WHERE id = :session_id
            """),
            {"now": now, "session_id": session_id},
        )
        self.db.commit()
        return self.get_session(session_id)

    def get_total_tokens(self, session_id: str) -> int:
        """Get total token count for a session."""
        row = self.db.execute(
            text("""
                SELECT COALESCE(SUM(token_count), 0)
                FROM conversation_messages
                WHERE session_id = :session_id
            """),
            {"session_id": session_id},
        ).fetchone()
        return int(row[0]) if row else 0
