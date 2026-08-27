"""Redis Streams message bus for inter-agent communication."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    recipient: str = ""
    type: str = "status"
    payload: dict = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    reply_to: str | None = None

    def to_redis(self) -> dict[str, str]:
        data = asdict(self)
        return {"data": json.dumps(data, default=str)}

    @classmethod
    def from_redis(cls, raw: dict[bytes, bytes]) -> AgentMessage | None:
        try:
            data_str = raw.get(b"data") or raw.get("data")
            if isinstance(data_str, bytes):
                data_str = data_str.decode()
            data = json.loads(data_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None


class RedisMessageBus:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None
        self._stream_offsets: dict[str, str] = {}

    async def connect(self) -> None:
        self._pool = aioredis.ConnectionPool.from_url(
            self._redis_url, max_connections=50, decode_responses=False
        )
        self._client = aioredis.Redis(connection_pool=self._pool)
        await self._client.ping()
        logger.info("Redis message bus connected to %s", self._redis_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("RedisMessageBus is not connected. Call connect() first.")
        return self._client

    def run_channel(self, run_id: str) -> str:
        return f"run:{run_id}:messages"

    def agent_inbox(self, run_id: str, step_id: str) -> str:
        return f"run:{run_id}:agent:{step_id}"

    def coordinator_inbox(self, run_id: str) -> str:
        return f"run:{run_id}:agent:coordinator"

    async def create_run_channel(self, run_id: str) -> None:
        stream = self.run_channel(run_id)
        await self.client.xadd(
            stream,
            {"data": json.dumps({"event": "channel_created", "run_id": run_id})},
        )
        logger.info("Created run channel: %s", stream)

    async def create_agent_inbox(self, run_id: str, step_id: str) -> str:
        inbox = self.agent_inbox(run_id, step_id)
        await self.client.xadd(
            inbox,
            {"data": json.dumps({"event": "inbox_created", "step_id": step_id})},
        )
        return inbox

    async def publish(self, run_id: str, message: AgentMessage) -> str:
        run_stream = self.run_channel(run_id)
        msg_id = await self.client.xadd(run_stream, message.to_redis())

        if message.recipient == "coordinator":
            coord_inbox = self.coordinator_inbox(run_id)
            await self.client.xadd(coord_inbox, message.to_redis())
        elif message.recipient:
            agent_inbox = self.agent_inbox(run_id, message.recipient)
            await self.client.xadd(agent_inbox, message.to_redis())

        return str(msg_id)

    async def consume(
        self, run_id: str, step_id: str, timeout_ms: int = 5000, count: int = 10
    ) -> list[AgentMessage]:
        inbox = self.agent_inbox(run_id, step_id)
        last_id = self._stream_offsets.get(inbox, "0-0")
        try:
            result = await self.client.xread(
                {inbox: last_id}, count=count, block=timeout_ms
            )
        except Exception:
            logger.exception("Failed to consume agent inbox %s", inbox)
            return []

        messages: list[AgentMessage] = []
        for _stream_name, entries in (result or []):
            for entry_id, raw_data in entries:
                self._stream_offsets[inbox] = (
                    entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                )
                msg = AgentMessage.from_redis(raw_data)
                if msg:
                    messages.append(msg)
        return messages

    async def consume_coordinator(
        self, run_id: str, timeout_ms: int = 5000, count: int = 50
    ) -> list[AgentMessage]:
        inbox = self.coordinator_inbox(run_id)
        last_id = self._stream_offsets.get(inbox, "0-0")
        try:
            result = await self.client.xread(
                {inbox: last_id}, count=count, block=timeout_ms
            )
        except Exception:
            logger.exception("Failed to consume coordinator inbox %s", inbox)
            return []

        messages: list[AgentMessage] = []
        for _stream_name, entries in (result or []):
            for entry_id, raw_data in entries:
                self._stream_offsets[inbox] = (
                    entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                )
                msg = AgentMessage.from_redis(raw_data)
                if msg:
                    messages.append(msg)
        return messages

    async def get_run_log(self, run_id: str, last_id: str = "0") -> list[AgentMessage]:
        stream = self.run_channel(run_id)
        try:
            result = await self.client.xrange(stream, min=last_id, max="+", count=500)
        except Exception:
            return []

        messages: list[AgentMessage] = []
        for _entry_id, raw_data in (result or []):
            msg = AgentMessage.from_redis(raw_data)
            if msg:
                messages.append(msg)
        return messages

    async def publish_status(
        self, run_id: str, sender: str, step_id: str, status: str, details: dict | None = None
    ) -> None:
        msg = AgentMessage(
            sender=sender,
            recipient="coordinator",
            type="status",
            payload={"step_id": step_id, "status": status, **(details or {})},
        )
        await self.publish(run_id, msg)

    async def publish_findings(
        self, run_id: str, sender: str, findings: str, artifact_refs: list[str] | None = None
    ) -> None:
        msg = AgentMessage(
            sender=sender,
            recipient="coordinator",
            type="findings",
            payload={"findings": findings},
            artifact_refs=artifact_refs or [],
        )
        await self.publish(run_id, msg)

    async def publish_question(
        self, run_id: str, sender: str, recipient: str, question: str
    ) -> None:
        msg = AgentMessage(
            sender=sender,
            recipient=recipient,
            type="question",
            payload={"question": question},
        )
        await self.publish(run_id, msg)

    async def publish_review(
        self, run_id: str, sender: str, target_step: str, approved: bool, feedback: str = ""
    ) -> None:
        msg = AgentMessage(
            sender=sender,
            recipient="coordinator",
            type="review",
            payload={
                "target_step": target_step,
                "approved": approved,
                "feedback": feedback,
            },
        )
        await self.publish(run_id, msg)

    async def cleanup(self, run_id: str) -> None:
        keys = await self.client.keys(f"run:{run_id}:*")
        if keys:
            await self.client.delete(*keys)
            logger.info("Cleaned up %d Redis keys for run %s", len(keys), run_id)
        prefix = f"run:{run_id}:"
        self._stream_offsets = {
            stream: offset
            for stream, offset in self._stream_offsets.items()
            if not stream.startswith(prefix)
        }
