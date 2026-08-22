from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    thread_id: str = ""
    tenant_id: str = ""
    created_at: float = field(default_factory=time.time)
    _messages: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self._messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": time.time(),
            }
        )

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "thread_id": self.thread_id,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "messages": list(self._messages),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.session_id = snapshot["session_id"]
        self.agent_id = snapshot.get("agent_id", "")
        self.thread_id = snapshot.get("thread_id", "")
        self.tenant_id = snapshot.get("tenant_id", "")
        self.created_at = snapshot.get("created_at", self.created_at)
        self._messages = list(snapshot.get("messages", []))


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def create(
        self,
        agent_id: str = "",
        thread_id: str = "",
        tenant_id: str = "",
    ) -> AgentSession:
        session = AgentSession(
            agent_id=agent_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)

    def update(self, session: AgentSession) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
