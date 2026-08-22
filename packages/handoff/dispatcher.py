import asyncio
import logging
from typing import Callable, Any, Optional
from .types import HandoffMessage, ProcessResult, ProcessorPolicy, LaneName
from .queues import QueueManager

logger = logging.getLogger(__name__)


class HandoffDispatcher:
    def __init__(self, queue_manager: QueueManager):
        self._queue_manager = queue_manager
        self._processors: dict[str, Callable[..., Any]] = {}
        self._policies: dict[str, ProcessorPolicy] = {}

    def register_processor(
        self, 
        message_type: str, 
        processor: Callable[..., Any],
        policy: Optional[ProcessorPolicy] = None
    ) -> None:
        """Register a processor for a specific message type."""
        self._processors[message_type] = processor
        if policy:
            self._policies[message_type] = policy
        logger.info(f"Registered processor for message type: {message_type}")

    def _get_processor(self, message_type: str) -> Optional[Callable[..., Any]]:
        """Get processor for a message type."""
        return self._processors.get(message_type)

    def _get_policy(self, message_type: str) -> ProcessorPolicy:
        """Get policy for a message type."""
        return self._policies.get(message_type, ProcessorPolicy())

    async def dispatch(self, message: HandoffMessage) -> ProcessResult:
        """Dispatch a message to its registered processor."""
        processor = self._get_processor(message.type)
        if not processor:
            logger.error(f"No processor registered for message type: {message.type}")
            return ProcessResult(
                status="dead",
                reason=f"No processor registered for type: {message.type}"
            )

        policy = self._get_policy(message.type)
        lane = policy.lane
        timeout_seconds = policy.timeout_ms / 1000.0

        if self._queue_manager.is_full(lane):
            logger.warning(f"Lane {lane.value} is full, retrying message {message.id}")
            return ProcessResult(
                status="retry",
                delay_ms=1000,
                reason=f"Lane {lane.value} is at capacity"
            )

        self._queue_manager.increment_active(lane)
        try:
            try:
                result = await asyncio.wait_for(
                    self._process_message(processor, message),
                    timeout=timeout_seconds
                )
                await self._handle_outbound(result)
                return result
            except asyncio.TimeoutError:
                logger.error(f"Timeout processing message {message.id} of type {message.type}")
                return await self._handle_failure(
                    message, 
                    f"Processing timeout after {timeout_seconds}s"
                )
            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
                return await self._handle_failure(message, str(e))
        finally:
            self._queue_manager.decrement_active(lane)

    async def _process_message(
        self, 
        processor: Callable[..., Any], 
        message: HandoffMessage
    ) -> ProcessResult:
        """Process a message with the registered processor."""
        result = await processor(message)
        
        if isinstance(result, ProcessResult):
            return result
        
        if isinstance(result, dict):
            return ProcessResult(
                status=result.get("status", "ok"),
                outbound=result.get("outbound", []),
                delay_ms=result.get("delay_ms", 0),
                reason=result.get("reason", "")
            )
        
        return ProcessResult(status="ok", outbound=[])

    async def _handle_failure(
        self, 
        message: HandoffMessage, 
        reason: str
    ) -> ProcessResult:
        """Handle processing failure with retry logic."""
        message.attempt += 1
        
        if message.attempt >= message.max_attempts:
            logger.error(
                f"Message {message.id} exceeded max attempts "
                f"({message.max_attempts}), moving to dead queue"
            )
            return ProcessResult(
                status="dead",
                reason=f"Exceeded max attempts: {reason}"
            )
        
        delay_ms = min(1000 * (2 ** (message.attempt - 1)), 30000)
        logger.warning(
            f"Retrying message {message.id} (attempt {message.attempt}/"
            f"{message.max_attempts}) after {delay_ms}ms"
        )
        
        return ProcessResult(
            status="retry",
            delay_ms=delay_ms,
            reason=reason
        )

    async def _handle_outbound(self, result: ProcessResult) -> None:
        """Handle outbound messages from a successful result."""
        for outbound_msg in result.outbound:
            if isinstance(outbound_msg, HandoffMessage):
                lane = LaneName.MAIN
                if outbound_msg.headers.get("lane"):
                    try:
                        lane = LaneName(outbound_msg.headers["lane"])
                    except ValueError:
                        pass
                
                enqueued = await self._queue_manager.enqueue(outbound_msg, lane)
                if not enqueued:
                    logger.warning(
                        f"Failed to enqueue outbound message {outbound_msg.id} "
                        f"to lane {lane.value}"
                    )

    def has_processor(self, message_type: str) -> bool:
        """Check if a processor is registered for a message type."""
        return message_type in self._processors

    def get_registered_types(self) -> list[str]:
        """Get list of registered message types."""
        return list(self._processors.keys())
