from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from packages.handoff.redis_streams import AgentMessage, RedisMessageBus


@pytest.mark.asyncio
async def test_coordinator_consumer_blocks_and_advances_stream_offset() -> None:
    bus = RedisMessageBus("redis://unused")
    client = MagicMock()
    client.xread = AsyncMock(
        side_effect=[
            [
                (
                    b"run:r1:agent:coordinator",
                    [(b"1-0", AgentMessage(sender="worker").to_redis())],
                )
            ],
            [],
        ]
    )
    bus._client = client

    messages = await bus.consume_coordinator("r1", timeout_ms=250)
    assert len(messages) == 1
    assert messages[0].sender == "worker"
    client.xread.assert_awaited_with(
        {"run:r1:agent:coordinator": "0-0"}, count=50, block=250
    )

    await bus.consume_coordinator("r1", timeout_ms=250)
    client.xread.assert_awaited_with(
        {"run:r1:agent:coordinator": "1-0"}, count=50, block=250
    )
