import asyncio
from typing import Optional
from .types import HandoffMessage, LaneName, LaneStats, DEFAULT_LANE_CONFIG


class QueueManager:
    def __init__(self, lane_config: dict[LaneName, int] = DEFAULT_LANE_CONFIG):
        self._lane_config = lane_config
        self._queues: dict[LaneName, asyncio.Queue[HandoffMessage]] = {}
        self._active_counts: dict[LaneName, int] = {lane: 0 for lane in LaneName}
        self._draining: dict[LaneName, bool] = {lane: False for lane in LaneName}
        
        for lane in LaneName:
            max_size = lane_config.get(lane, 100)
            self._queues[lane] = asyncio.Queue(maxsize=max_size)

    async def enqueue(self, message: HandoffMessage, lane: LaneName) -> bool:
        """Enqueue a message to the specified lane. Returns False if queue is full."""
        queue = self._queues.get(lane)
        if queue is None:
            raise ValueError(f"Unknown lane: {lane}")
        
        if queue.full():
            return False
        
        await queue.put(message)
        return True

    async def dequeue(self, lane: LaneName) -> Optional[HandoffMessage]:
        """Dequeue a message from the specified lane. Returns None if empty."""
        queue = self._queues.get(lane)
        if queue is None:
            raise ValueError(f"Unknown lane: {lane}")
        
        try:
            message = queue.get_nowait()
            return message
        except asyncio.QueueEmpty:
            return None

    def increment_active(self, lane: LaneName) -> None:
        """Increment the active count for a lane."""
        if lane in self._active_counts:
            self._active_counts[lane] += 1

    def decrement_active(self, lane: LaneName) -> None:
        """Decrement the active count for a lane."""
        if lane in self._active_counts and self._active_counts[lane] > 0:
            self._active_counts[lane] -= 1

    def get_lane_stats(self, lane: LaneName) -> LaneStats:
        """Get statistics for a specific lane."""
        if lane not in self._queues:
            raise ValueError(f"Unknown lane: {lane}")
        
        return LaneStats(
            lane=lane.value,
            active=self._active_counts.get(lane, 0),
            queued=self._queues[lane].qsize(),
            max_concurrent=self._lane_config.get(lane, 100),
            draining=self._draining.get(lane, False)
        )

    def size(self, lane: LaneName) -> int:
        """Get the number of queued messages in a lane."""
        queue = self._queues.get(lane)
        if queue is None:
            raise ValueError(f"Unknown lane: {lane}")
        return queue.qsize()

    def is_full(self, lane: LaneName) -> bool:
        """Check if a lane is at maximum concurrent capacity."""
        if lane not in self._active_counts or lane not in self._lane_config:
            raise ValueError(f"Unknown lane: {lane}")
        return self._active_counts[lane] >= self._lane_config[lane]

    def set_draining(self, lane: LaneName, draining: bool) -> None:
        """Set the draining state for a lane."""
        if lane in self._draining:
            self._draining[lane] = draining

    def get_all_stats(self) -> list[LaneStats]:
        """Get statistics for all lanes."""
        return [self.get_lane_stats(lane) for lane in LaneName]
