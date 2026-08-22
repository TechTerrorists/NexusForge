import logging
import asyncio
from typing import Callable, Any

logger = logging.getLogger(__name__)


class Broadcaster:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._max_history: int = 100

    def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to events on a channel."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)
        logger.debug(f"Subscribed to channel: {channel}")

    def unsubscribe(self, channel: str, callback: Callable) -> None:
        """Unsubscribe from events on a channel."""
        if channel in self._subscribers:
            try:
                self._subscribers[channel].remove(callback)
            except ValueError:
                logger.warning(
                    f"Callback not found in channel subscribers: {channel}"
                )

    async def broadcast(self, channel: str, event: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers of a channel.

        Best-effort delivery: exceptions from individual subscribers
        are caught and logged without affecting other subscribers.
        """
        if channel not in self._history:
            self._history[channel] = []
        self._history[channel].append(event)
        if len(self._history[channel]) > self._max_history:
            self._history[channel] = self._history[channel][-self._max_history:]

        subscribers = self._subscribers.get(channel, [])
        if not subscribers:
            logger.debug(f"No subscribers for channel: {channel}")
            return

        logger.debug(
            f"Broadcasting to {len(subscribers)} subscribers on channel: {channel}"
        )

        for callback in subscribers:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"Error in broadcast subscriber for channel {channel}: {e}"
                )

    def get_subscriber_count(self, channel: str) -> int:
        """Get the number of subscribers for a channel."""
        return len(self._subscribers.get(channel, []))

    def get_channels(self) -> list[str]:
        """Get list of channels with active subscribers."""
        return list(self._subscribers.keys())

    def get_history(
        self, channel: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent broadcast history for a channel."""
        history = self._history.get(channel, [])
        return history[-limit:]

    def clear_history(self, channel: str = None) -> None:
        """Clear broadcast history for a channel or all channels."""
        if channel:
            self._history.pop(channel, None)
        else:
            self._history.clear()

    def set_max_history(self, max_history: int) -> None:
        """Set maximum history size per channel."""
        self._max_history = max_history
