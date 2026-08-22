import json
import logging
import asyncio
from typing import Any, Callable, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CDCPoller:
    def __init__(self, db_session_factory=None, poll_interval: float = 1.0):
        self._db_session_factory = db_session_factory
        self._poll_interval = poll_interval
        self._last_processed_id: int = 0
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._subscribers: dict[str, list[Callable]] = {}

    async def start(self) -> None:
        """Start the CDC poller."""
        if self._running:
            logger.warning("CDC poller is already running")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("CDC poller started")

    async def stop(self) -> None:
        """Stop the CDC poller."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("CDC poller stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                events = await self.poll_once()
                for event in events:
                    await self._notify_subscribers(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in CDC poll loop: {e}")

            await asyncio.sleep(self._poll_interval)

    async def poll_once(self) -> list[dict[str, Any]]:
        """Poll for new changes once.

        Reads from the change_log table where id > last_processed_id,
        decodes the payload, and returns a list of change events.
        """
        if not self._db_session_factory:
            return []

        events: list[dict[str, Any]] = []

        try:
            async with self._db_session_factory() as session:
                result = await session.execute(
                    """
                    SELECT id, table_name, operation, payload, created_at
                    FROM change_log
                    WHERE id > :last_id
                    ORDER BY id ASC
                    LIMIT 100
                    """,
                    {"last_id": self._last_processed_id},
                )
                rows = result.fetchall()

                for row in rows:
                    row_dict = dict(row)
                    payload = row_dict.get("payload", "{}")

                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            payload = {"raw": payload}

                    event = {
                        "id": row_dict["id"],
                        "table_name": row_dict["table_name"],
                        "operation": row_dict["operation"],
                        "payload": payload,
                        "created_at": (
                            row_dict["created_at"].isoformat()
                            if row_dict.get("created_at")
                            else datetime.now(timezone.utc).isoformat()
                        ),
                    }
                    events.append(event)
                    self._last_processed_id = max(self._last_processed_id, row_dict["id"])

        except Exception as e:
            logger.error(f"Error polling change_log: {e}")

        if events:
            logger.debug(f"Polled {len(events)} change events (last_id={self._last_processed_id})")

        return events

    async def _notify_subscribers(self, event: dict[str, Any]) -> None:
        """Notify subscribers of a change event."""
        channel = event.get("table_name", "unknown")
        subscribers = self._subscribers.get(channel, []) + self._subscribers.get("*", [])

        for callback in subscribers:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Subscriber callback error for channel {channel}: {e}")

    def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to change events for a specific table/channel."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)
        logger.debug(f"Subscribed to CDC channel: {channel}")

    def unsubscribe(self, channel: str, callback: Callable) -> None:
        """Unsubscribe from change events for a specific table/channel."""
        if channel in self._subscribers:
            try:
                self._subscribers[channel].remove(callback)
            except ValueError:
                pass

    @property
    def last_processed_id(self) -> int:
        """Get the last processed change_log ID."""
        return self._last_processed_id

    def reset_last_processed_id(self, new_id: int = 0) -> None:
        """Reset the last processed ID."""
        self._last_processed_id = new_id
        logger.info(f"Reset last processed ID to {new_id}")
