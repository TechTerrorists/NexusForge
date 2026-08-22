import asyncio
import logging
import time
from typing import Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatInfo:
    interval: float
    callback: Callable[..., None]
    last_heartbeat: float = field(default_factory=time.time)
    task: Optional[asyncio.Task] = None


class CooperativeCancellation:
    def __init__(self):
        self._controllers: dict[str, asyncio.Event] = {}
        self._heartbeats: dict[str, HeartbeatInfo] = {}
        self._reasons: dict[str, str] = {}

    def create_controller(self, run_id: str) -> asyncio.Event:
        """Create a cancellation controller for a run."""
        if run_id not in self._controllers:
            self._controllers[run_id] = asyncio.Event()
            logger.debug(f"Created cancellation controller for run: {run_id}")
        return self._controllers[run_id]

    def cancel(self, run_id: str, reason: str = "Cancelled by user") -> bool:
        """Cancel a run. Returns True if cancellation was successful."""
        if run_id not in self._controllers:
            logger.warning(f"No controller found for run: {run_id}")
            return False
        
        self._reasons[run_id] = reason
        self._controllers[run_id].set()
        
        if run_id in self._heartbeats and self._heartbeats[run_id].task:
            self._heartbeats[run_id].task.cancel()
        
        logger.info(f"Cancelled run {run_id}: {reason}")
        return True

    def is_cancelled(self, run_id: str) -> bool:
        """Check if a run has been cancelled."""
        if run_id not in self._controllers:
            return False
        return self._controllers[run_id].is_set()

    async def wait(self, run_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for cancellation. Returns True if cancelled, False if timeout."""
        if run_id not in self._controllers:
            return False
        
        event = self._controllers[run_id]
        try:
            if timeout is not None:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    def register_heartbeat(
        self, 
        run_id: str, 
        interval: float, 
        callback: Callable[..., None]
    ) -> None:
        """Register a heartbeat for a run to detect stalls."""
        if run_id in self._heartbeats:
            logger.warning(f"Heartbeat already registered for run: {run_id}")
            return
        
        heartbeat = HeartbeatInfo(interval=interval, callback=callback)
        heartbeat.task = asyncio.create_task(
            self._heartbeat_loop(run_id, heartbeat)
        )
        self._heartbeats[run_id] = heartbeat
        logger.debug(f"Registered heartbeat for run {run_id} with interval {interval}s")

    async def _heartbeat_loop(self, run_id: str, heartbeat: HeartbeatInfo) -> None:
        """Internal heartbeat loop."""
        try:
            while not self.is_cancelled(run_id):
                await asyncio.sleep(heartbeat.interval)
                
                try:
                    heartbeat.callback(run_id)
                    heartbeat.last_heartbeat = time.time()
                except Exception as e:
                    logger.error(f"Heartbeat callback error for run {run_id}: {e}")
                    self.cancel(run_id, f"Heartbeat callback failed: {e}")
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if run_id in self._heartbeats:
                del self._heartbeats[run_id]

    def unregister_heartbeat(self, run_id: str) -> None:
        """Unregister heartbeat for a run."""
        if run_id in self._heartbeats:
            if self._heartbeats[run_id].task:
                self._heartbeats[run_id].task.cancel()
            del self._heartbeats[run_id]
            logger.debug(f"Unregistered heartbeat for run: {run_id}")

    def get_cancellation_reason(self, run_id: str) -> Optional[str]:
        """Get the reason for cancellation."""
        return self._reasons.get(run_id)

    def cleanup(self, run_id: str) -> None:
        """Clean up resources for a run."""
        self.unregister_heartbeat(run_id)
        if run_id in self._controllers:
            del self._controllers[run_id]
        if run_id in self._reasons:
            del self._reasons[run_id]
        logger.debug(f"Cleaned up cancellation resources for run: {run_id}")

    def get_active_runs(self) -> list[str]:
        """Get list of active (non-cancelled) run IDs."""
        return [
            run_id for run_id, event in self._controllers.items()
            if not event.is_set()
        ]
