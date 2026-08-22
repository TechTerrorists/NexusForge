from __future__ import annotations

import time
from typing import Any


class DurableFacts:
    """Utility functions for deriving execution and workflow state from durable facts."""

    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_RUNNING = "running"
    STATUS_PENDING = "pending"
    STATUS_CANCELLED = "cancelled"
    STATUS_STALE = "stale"

    @staticmethod
    def derive_execution_status(facts: dict[str, Any]) -> str:
        """Derive the overall execution status from a set of facts."""
        if not facts:
            return DurableFacts.STATUS_PENDING

        error = facts.get("error")
        if error:
            return DurableFacts.STATUS_FAILED

        status = facts.get("status")
        if status in (
            DurableFacts.STATUS_COMPLETED,
            DurableFacts.STATUS_FAILED,
            DurableFacts.STATUS_CANCELLED,
        ):
            return status

        started_at = facts.get("started_at")
        finished_at = facts.get("finished_at")
        if started_at and finished_at:
            return DurableFacts.STATUS_COMPLETED

        if started_at:
            return DurableFacts.STATUS_RUNNING

        return DurableFacts.STATUS_PENDING

    @staticmethod
    def derive_workflow_status(facts: dict[str, Any]) -> str:
        """Derive the overall workflow status from aggregated execution facts."""
        if not facts:
            return DurableFacts.STATUS_PENDING

        executions = facts.get("executions", [])
        if not executions:
            overall = facts.get("status")
            if overall:
                return overall
            return DurableFacts.STATUS_PENDING

        statuses = [
            DurableFacts.derive_execution_status(ex) if isinstance(ex, dict) else str(ex)
            for ex in executions
        ]

        if any(s == DurableFacts.STATUS_FAILED for s in statuses):
            return DurableFacts.STATUS_FAILED

        if any(s == DurableFacts.STATUS_CANCELLED for s in statuses):
            return DurableFacts.STATUS_CANCELLED

        if all(s == DurableFacts.STATUS_COMPLETED for s in statuses):
            return DurableFacts.STATUS_COMPLETED

        if any(s == DurableFacts.STATUS_RUNNING for s in statuses):
            return DurableFacts.STATUS_RUNNING

        return DurableFacts.STATUS_PENDING

    @staticmethod
    def is_stale(heartbeat: float | int | None, threshold: float = 30.0) -> bool:
        """Check if a heartbeat indicates the process is stale.

        Args:
            heartbeat: Unix timestamp of the last heartbeat.
            threshold: Seconds since the last heartbeat to consider stale.
        """
        if heartbeat is None:
            return True
        try:
            elapsed = time.time() - float(heartbeat)
            return elapsed > threshold
        except (TypeError, ValueError):
            return True

    @staticmethod
    def needs_human_input(execution: dict[str, Any]) -> bool:
        """Check if an execution is waiting for human input."""
        if not execution:
            return False
        status = execution.get("status", "")
        if status == "waiting_human":
            return True
        if status == "blocked":
            reason = execution.get("block_reason", "")
            if "human" in reason.lower() or "approval" in reason.lower():
                return True
        pending_input = execution.get("pending_human_input")
        if pending_input is True:
            return True
        if isinstance(pending_input, dict) and pending_input.get("required", False):
            return True
        return False

    @staticmethod
    def has_pending_work(execution: dict[str, Any]) -> bool:
        """Check if an execution has remaining work to do."""
        if not execution:
            return False
        status = execution.get("status", "")
        if status in (DurableFacts.STATUS_FAILED, DurableFacts.STATUS_CANCELLED, DurableFacts.STATUS_COMPLETED):
            return False
        if status == DurableFacts.STATUS_RUNNING:
            return True
        steps = execution.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    step_status = step.get("status", "")
                    if step_status in (DurableFacts.STATUS_PENDING, DurableFacts.STATUS_RUNNING):
                        return True
        queue = execution.get("pending_tasks", [])
        if isinstance(queue, list) and len(queue) > 0:
            return True
        next_action = execution.get("next_action")
        if next_action:
            return True
        return status == DurableFacts.STATUS_PENDING

    @staticmethod
    def compute_progress(facts: dict[str, Any]) -> dict[str, Any]:
        """Compute execution progress metrics."""
        if not facts:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "percent": 0.0}

        executions = facts.get("executions", [])
        total = len(executions)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "percent": 0.0}

        completed = 0
        failed = 0
        pending = 0
        running = 0

        for ex in executions:
            if not isinstance(ex, dict):
                continue
            status = DurableFacts.derive_execution_status(ex)
            if status == DurableFacts.STATUS_COMPLETED:
                completed += 1
            elif status == DurableFacts.STATUS_FAILED:
                failed += 1
            elif status == DurableFacts.STATUS_RUNNING:
                running += 1
            else:
                pending += 1

        percent = (completed / total * 100) if total > 0 else 0.0
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "percent": round(percent, 2),
        }
