"""Coordinator agent that manages inter-agent communication during execution."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from packages.handoff.redis_streams import AgentMessage, RedisMessageBus

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    def __init__(
        self,
        bus: RedisMessageBus,
        run_id: str,
        steps: list[dict[str, Any]],
        on_step_action: Callable[[str, str, dict], Awaitable[None]] | None = None,
    ) -> None:
        self.bus = bus
        self.run_id = run_id
        self.steps = {s["key"]: s for s in steps}
        self.step_statuses: dict[str, str] = {s["key"]: "pending" for s in steps}
        self.retry_counts: dict[str, int] = {s["key"]: 0 for s in steps}
        self.messages: list[AgentMessage] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_step_action = on_step_action

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Coordinator started for run %s", self.run_id)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        logger.info("Coordinator stopped for run %s", self.run_id)

    async def _loop(self) -> None:
        while self._running:
            try:
                messages = await self.bus.consume_coordinator(self.run_id, timeout_ms=2000)
                for msg in messages:
                    await self._handle_message(msg)
                if not messages:
                    # XREAD normally yields while blocking. This also prevents
                    # event-loop starvation if Redis fails and returns early.
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Coordinator loop error for run %s", self.run_id)
                await asyncio.sleep(1)

    async def _handle_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)
        handler = {
            "status": self._handle_status,
            "findings": self._handle_findings,
            "question": self._handle_question,
            "review": self._handle_review,
            "error": self._handle_error,
        }.get(msg.type)
        if handler:
            await handler(msg)

    async def _handle_status(self, msg: AgentMessage) -> None:
        step_id = msg.payload.get("step_id", "")
        status = msg.payload.get("status", "")
        if step_id in self.step_statuses:
            self.step_statuses[step_id] = status
            logger.info("Step %s status: %s", step_id, status)

            if status == "completed":
                await self._trigger_dependents(step_id)
            elif status == "failed":
                await self._handle_step_failure(step_id, msg.payload)

    async def _handle_findings(self, msg: AgentMessage) -> None:
        findings = msg.payload.get("findings", "")
        logger.info("Findings from %s: %s", msg.sender, findings[:200])

    async def _handle_question(self, msg: AgentMessage) -> None:
        question = msg.payload.get("question", "")
        logger.info("Question from %s to %s: %s", msg.sender, msg.recipient, question[:200])

        if msg.recipient == "coordinator":
            answer = await self._answer_question(msg.sender, question)
            reply = AgentMessage(
                sender="coordinator",
                recipient=msg.sender,
                type="answer",
                payload={"answer": answer, "reply_to": msg.id},
            )
            await self.bus.publish(self.run_id, reply)

    async def _handle_review(self, msg: AgentMessage) -> None:
        target = msg.payload.get("target_step", "")
        approved = msg.payload.get("approved", False)
        feedback = msg.payload.get("feedback", "")

        if target in self.step_statuses:
            if approved:
                self.step_statuses[target] = "reviewed"
                logger.info("Step %s reviewed and approved", target)
            else:
                logger.info("Step %s review rejected: %s", target, feedback[:200])
                await self._handle_step_failure(target, {"reason": f"Review rejected: {feedback}"})

    async def _handle_error(self, msg: AgentMessage) -> None:
        step_id = msg.payload.get("step_id", "")
        error = msg.payload.get("error", "Unknown error")
        logger.error("Error from %s: %s", msg.sender, error[:200])
        if step_id:
            await self._handle_step_failure(step_id, {"error": error})

    async def _trigger_dependents(self, completed_step: str) -> None:
        for step_key, step_def in self.steps.items():
            if completed_step in (step_def.get("depends_on") or []):
                all_deps_met = all(
                    self.step_statuses.get(dep) in ("completed", "reviewed")
                    for dep in (step_def.get("depends_on") or [])
                )
                if all_deps_met and self.step_statuses.get(step_key) == "pending":
                    self.step_statuses[step_key] = "ready"
                    if self._on_step_action:
                        await self._on_step_action(step_key, "start", {})

    async def _handle_step_failure(self, step_id: str, details: dict) -> None:
        max_retries = self.steps.get(step_id, {}).get("max_retries", 3)
        self.retry_counts[step_id] = self.retry_counts.get(step_id, 0) + 1

        if self.retry_counts[step_id] < max_retries:
            self.step_statuses[step_id] = "retrying"
            logger.info(
                "Retrying step %s (attempt %d/%d)",
                step_id,
                self.retry_counts[step_id],
                max_retries,
            )
            if self._on_step_action:
                await self._on_step_action(step_id, "retry", details)
        else:
            self.step_statuses[step_id] = "failed"
            logger.error("Step %s failed after %d retries", step_id, max_retries)
            if self._on_step_action:
                await self._on_step_action(step_id, "escalate", details)

    async def _answer_question(self, asker: str, question: str) -> str:
        step_info = self.steps.get(asker, {})
        context = (
            f"Step: {step_info.get('title', 'unknown')}. "
            f"Dependencies: {step_info.get('depends_on', [])}"
        )
        return (
            f"Coordinator context: {context}. Please proceed with your best judgment "
            "based on the task instructions."
        )

    def get_status_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step_statuses": dict(self.step_statuses),
            "retry_counts": dict(self.retry_counts),
            "total_messages": len(self.messages),
            "is_running": self._running,
        }

    def get_completed_steps(self) -> list[str]:
        return [k for k, v in self.step_statuses.items() if v in ("completed", "reviewed")]

    def get_failed_steps(self) -> list[str]:
        return [k for k, v in self.step_statuses.items() if v == "failed"]

    def are_all_steps_done(self) -> bool:
        return all(
            v in ("completed", "reviewed", "failed")
            for v in self.step_statuses.values()
        )
