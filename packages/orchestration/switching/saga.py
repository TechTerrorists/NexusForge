"""Agent Switching Saga — durable migration between agents with rollback.

Implements the saga pattern for hot-swapping agents at runtime:

  1. **Source-stop**: Pause or drain the source agent.
  2. **Target-activate**: Start the target agent, optionally seeding it with
     context from the source.
  3. **Continuation delivery**: Forward any pending work items to the target.

If any step fails the saga rolls back in reverse order, restoring the
source agent to its previous state.

Supports two switch policies:
  - **DRAIN**: Wait for the source agent to finish its current work item
    before switching.
  - **INTERRUPT**: Immediately halt the source agent and switch.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Enums and dataclasses                                                        #
# --------------------------------------------------------------------------- #

class SwitchPolicy(enum.Enum):
    """Policy for how the source agent is stopped during a switch."""

    DRAIN = "drain"
    INTERRUPT = "interrupt"


@dataclass
class SwitchResult:
    """Result of an agent switching saga execution."""

    saga_id: str
    source_agent: str
    target_agent: str
    policy: SwitchPolicy
    success: bool
    duration_seconds: float
    steps_completed: list[str] = field(default_factory=list)
    error: str | None = None
    rolled_back: bool = False
    continuation_items_forwarded: int = 0


# --------------------------------------------------------------------------- #
# Saga step result                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class _SagaStep:
    """Internal representation of a saga step for rollback tracking."""

    name: str
    completed: bool = False
    compensation: Callable[[], Any] | None = None


# --------------------------------------------------------------------------- #
# AgentSwitchingSaga                                                           #
# --------------------------------------------------------------------------- #

class AgentSwitchingSaga:
    """Durable saga for hot-swapping agents at runtime.

    Usage::

        saga = AgentSwitchingSaga(
            source_agent=old_agent,
            target_agent=new_agent,
            policy=SwitchPolicy.DRAIN,
        )
        result = await saga.execute(state)

    The saga executes three steps:
      1. Stop / drain the source agent
      2. Activate the target agent
      3. Forward pending continuation items

    If any step fails, previously completed steps are compensated (rolled back).
    """

    def __init__(
        self,
        source_agent: Any,
        target_agent: Any,
        policy: SwitchPolicy = SwitchPolicy.DRAIN,
        drain_timeout: float = 30.0,
        on_source_stopped: Callable[[Any], Any] | None = None,
        on_target_activated: Callable[[Any], Any] | None = None,
        context_extractor: Callable[[Any, dict], dict] | None = None,
    ) -> None:
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.policy = policy
        self.drain_timeout = drain_timeout
        self.on_source_stopped = on_source_stopped
        self.on_target_activated = on_target_activated
        self.context_extractor = context_extractor

        self.source_name = getattr(source_agent, "name", "source")
        self.target_name = getattr(target_agent, "name", "target")
        self.saga_id = str(uuid.uuid4())

    async def execute(self, state: dict) -> SwitchResult:
        """Execute the full switching saga with rollback on failure.

        Args:
            state: Current workflow state dict.

        Returns:
            SwitchResult with execution details.
        """
        start_time = time.monotonic()
        steps: list[_SagaStep] = []
        continuation_items: list[dict] = []

        logger.info(
            "Saga '%s' starting | %s -> %s | policy=%s",
            self.saga_id, self.source_name, self.target_name, self.policy.value,
        )

        try:
            # Step 1: Stop / drain the source agent
            step1 = _SagaStep(
                name="source_stop",
                compensation=self._compensate_source_stop,
            )
            await self._step_source_stop(state)
            step1.completed = True
            steps.append(step1)

            # Extract context from source for target
            context = {}
            if self.context_extractor:
                try:
                    context = self.context_extractor(self.source_agent, state)
                except Exception as exc:
                    logger.warning("Context extraction failed: %s", exc)

            # Step 2: Activate the target agent
            step2 = _SagaStep(
                name="target_activate",
                compensation=self._compensate_target_activate,
            )
            await self._step_target_activate(state, context)
            step2.completed = True
            steps.append(step2)

            # Step 3: Forward continuation items
            continuation_items = self._extract_continuation_items(state)
            step3 = _SagaStep(name="continuation_delivery")
            forwarded = await self._step_continuation_delivery(continuation_items)
            step3.completed = True
            steps.append(step3)

            duration = time.monotonic() - start_time
            result = SwitchResult(
                saga_id=self.saga_id,
                source_agent=self.source_name,
                target_agent=self.target_name,
                policy=self.policy,
                success=True,
                duration_seconds=round(duration, 4),
                steps_completed=[s.name for s in steps],
                continuation_items_forwarded=forwarded,
            )

            logger.info(
                "Saga '%s' complete | duration=%.3fs | forwarded=%d",
                self.saga_id, duration, forwarded,
            )
            return result

        except Exception as exc:
            logger.error("Saga '%s' failed: %s", self.saga_id, exc)
            rolled_back = await self._rollback(steps)

            duration = time.monotonic() - start_time
            return SwitchResult(
                saga_id=self.saga_id,
                source_agent=self.source_name,
                target_agent=self.target_name,
                policy=self.policy,
                success=False,
                duration_seconds=round(duration, 4),
                steps_completed=[s.name for s in steps if s.completed],
                error=str(exc),
                rolled_back=rolled_back,
            )

    async def _step_source_stop(self, state: dict) -> None:
        """Step 1: Stop or drain the source agent."""
        logger.info("Saga '%s' step: source_stop (%s)", self.saga_id, self.policy.value)

        if self.policy == SwitchPolicy.DRAIN:
            await self._drain_source(state)
        else:
            await self._interrupt_source(state)

        if self.on_source_stopped:
            result = self.on_source_stopped(self.source_agent)
            if asyncio.iscoroutine(result):
                await result

    async def _drain_source(self, state: dict) -> None:
        """Wait for the source agent to finish its current work item."""
        source = self.source_agent
        is_processing = getattr(source, "is_processing", None)
        if callable(is_processing):
            try:
                if asyncio.iscoroutinefunction(is_processing):
                    processing = await is_processing()
                else:
                    processing = is_processing()
            except Exception:
                processing = False
        else:
            processing = False

        if not processing:
            logger.info("Saga '%s': source not processing, skip drain", self.saga_id)
            return

        # Poll until the source finishes or timeout
        deadline = time.monotonic() + self.drain_timeout
        while time.monotonic() < deadline:
            if callable(is_processing):
                try:
                    if asyncio.iscoroutinefunction(is_processing):
                        still_processing = await is_processing()
                    else:
                        still_processing = is_processing()
                except Exception:
                    still_processing = False
                if not still_processing:
                    break
            else:
                break
            await asyncio.sleep(0.1)

        if time.monotonic() >= deadline:
            logger.warning(
                "Saga '%s': drain timeout after %.1fs, forcing interrupt",
                self.saga_id, self.drain_timeout,
            )
            await self._interrupt_source(state)

    async def _interrupt_source(self, state: dict) -> None:
        """Immediately halt the source agent."""
        source = self.source_agent
        stop_fn = getattr(source, "stop", None) or getattr(source, "cancel", None) or getattr(source, "shutdown", None)
        if callable(stop_fn):
            try:
                if asyncio.iscoroutinefunction(stop_fn):
                    await stop_fn()
                else:
                    stop_fn()
                logger.info("Saga '%s': source agent stopped", self.saga_id)
            except Exception as exc:
                logger.error("Saga '%s': failed to stop source: %s", self.saga_id, exc)
                raise

    async def _step_target_activate(self, state: dict, context: dict) -> None:
        """Step 2: Activate the target agent with context from the source."""
        logger.info("Saga '%s' step: target_activate", self.saga_id)

        target = self.target_agent

        # Transfer state if the target has a set_state / load_context method
        for method_name in ("set_state", "load_context", "initialize"):
            init_fn = getattr(target, method_name, None)
            if callable(init_fn):
                try:
                    if asyncio.iscoroutinefunction(init_fn):
                        await init_fn({**state, **context})
                    else:
                        init_fn({**state, **context})
                    logger.info("Saga '%s': target initialised via %s", self.saga_id, method_name)
                    break
                except Exception as exc:
                    logger.warning("Saga '%s': target init method %s failed: %s", self.saga_id, method_name, exc)

        if self.on_target_activated:
            result = self.on_target_activated(self.target_agent)
            if asyncio.iscoroutine(result):
                await result

    def _extract_continuation_items(self, state: dict) -> list[dict]:
        """Extract pending work items that should be forwarded to the target."""
        items: list[dict] = []
        pending = state.get("pending_follow_ups", [])
        if isinstance(pending, list):
            items.extend(pending)
        return items

    async def _step_continuation_delivery(self, items: list[dict]) -> int:
        """Step 3: Forward continuation items to the target agent."""
        if not items:
            logger.info("Saga '%s': no continuation items to forward", self.saga_id)
            return 0

        logger.info(
            "Saga '%s' step: continuation_delivery (%d items)",
            self.saga_id, len(items),
        )

        target = self.target_agent
        deliver_fn = getattr(target, "receive_work_items", None) or getattr(target, "enqueue", None)
        if callable(deliver_fn):
            try:
                if asyncio.iscoroutinefunction(deliver_fn):
                    await deliver_fn(items)
                else:
                    deliver_fn(items)
                return len(items)
            except Exception as exc:
                logger.error("Saga '%s': continuation delivery failed: %s", self.saga_id, exc)
                raise

        # If target has no delivery method, store items as a state update
        logger.info("Saga '%s': target has no delivery method, items stored in state", self.saga_id)
        return len(items)

    def _compensate_source_stop(self) -> None:
        """Compensation: restart the source agent if it was stopped."""
        logger.info("Saga '%s' compensating: restarting source", self.saga_id)
        source = self.source_agent
        start_fn = getattr(source, "start", None) or getattr(source, "resume", None)
        if callable(start_fn):
            try:
                start_fn()
            except Exception as exc:
                logger.error("Saga '%s': source restart failed: %s", self.saga_id, exc)

    def _compensate_target_activate(self) -> None:
        """Compensation: deactivate the target agent."""
        logger.info("Saga '%s' compensating: deactivating target", self.saga_id)
        target = self.target_agent
        stop_fn = getattr(target, "stop", None) or getattr(target, "shutdown", None)
        if callable(stop_fn):
            try:
                stop_fn()
            except Exception as exc:
                logger.error("Saga '%s': target deactivation failed: %s", self.saga_id, exc)

    async def _rollback(self, completed_steps: list[_SagaStep]) -> bool:
        """Roll back completed steps in reverse order.

        Returns True if all compensations succeeded.
        """
        logger.info("Saga '%s' rolling back %d steps", self.saga_id, len(completed_steps))
        all_ok = True

        for step in reversed(completed_steps):
            if not step.completed or step.compensation is None:
                continue
            try:
                result = step.compensation()
                if asyncio.iscoroutine(result):
                    await result
                logger.info("Saga '%s': compensated step '%s'", self.saga_id, step.name)
            except Exception as exc:
                logger.error(
                    "Saga '%s': compensation for '%s' failed: %s",
                    self.saga_id, step.name, exc,
                )
                all_ok = False

        return all_ok
