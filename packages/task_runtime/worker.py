"""Durable NexusForge execution worker.

Jobs are leased from PostgreSQL. Redis is optional and only carries wake-ups
and ephemeral delivery; losing Redis never loses the execution ledger.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from contextlib import suppress
from datetime import datetime, timedelta

from sqlalchemy import select, update

from app import database
from app.database import close_db, init_db, init_engine
from app.models import ExecutionJob, ExecutionStatus, WorkflowRun, WorkflowTrigger
from packages.handoff.redis_streams import RedisMessageBus
from packages.task_runtime.cron import next_cron_fire
from packages.task_runtime.scheduler import TaskScheduler


logging.basicConfig(
    level=os.getenv("NEXUSFORGE_LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


class DurableWorker:
    def __init__(self, scheduler: TaskScheduler, *, worker_id: str) -> None:
        self.scheduler = scheduler
        self.worker_id = worker_id
        self.lease_seconds = int(os.getenv("NEXUSFORGE_JOB_LEASE_SECONDS", "90"))
        self.poll_seconds = float(os.getenv("NEXUSFORGE_WORKER_POLL_SECONDS", "1"))
        self._running = True

    async def claim(self) -> ExecutionJob | None:
        assert database.async_session_factory is not None
        now = datetime.utcnow()
        stale_before = now - timedelta(seconds=self.lease_seconds)
        async with database.async_session_factory() as db:
            # Claim and advance due cron triggers in the same transaction. A
            # deterministic idempotency key prevents duplicate delivery.
            due_triggers = list(
                (
                    await db.scalars(
                        select(WorkflowTrigger)
                        .where(
                            WorkflowTrigger.is_active.is_(True),
                            WorkflowTrigger.trigger_type == "cron",
                            WorkflowTrigger.next_fire_at <= now,
                        )
                        .with_for_update(skip_locked=True)
                        .limit(20)
                    )
                ).all()
            )
            for trigger in due_triggers:
                policy = str((trigger.config or {}).get("misfire_policy", "skip"))
                scheduled_for = now if policy == "latest" else trigger.next_fire_at or now
                idempotency_key = f"cron:{trigger.id}:{scheduled_for.isoformat()}"
                existing = await db.scalar(
                    select(WorkflowRun.id).where(WorkflowRun.idempotency_key == idempotency_key)
                )
                if existing is None:
                    run = WorkflowRun(
                        workflow_id=trigger.workflow_id,
                        workflow_version_id=trigger.workflow_version_id,
                        run_kind="deterministic_workflow",
                        idempotency_key=idempotency_key,
                        status=ExecutionStatus.QUEUED,
                        input_data={
                            "payload": {"scheduled_for": scheduled_for.isoformat()},
                            "test_mode": False,
                            "trigger_id": str(trigger.id),
                        },
                        tokens_used=0,
                        cost_usd=0,
                    )
                    db.add(run)
                    await db.flush()
                    db.add(
                        ExecutionJob(
                            run_id=run.id,
                            job_type="deterministic_workflow",
                            status="queued",
                            idempotency_key=f"workflow-run:{run.id}",
                        )
                    )
                next_from = scheduled_for if policy == "catch_up" else now
                trigger.next_fire_at = next_cron_fire(
                    str((trigger.config or {}).get("cron")),
                    str((trigger.config or {}).get("timezone")),
                    next_from,
                )
            await db.execute(
                update(ExecutionJob)
                .where(
                    ExecutionJob.status == "running",
                    ExecutionJob.leased_at < stale_before,
                    ExecutionJob.attempts < ExecutionJob.max_attempts,
                )
                .values(status="queued", leased_by=None, leased_at=None, error="Recovered stale lease")
            )
            job = await db.scalar(
                select(ExecutionJob)
                .where(
                    ExecutionJob.status == "queued",
                    ExecutionJob.available_at <= now,
                    ExecutionJob.attempts < ExecutionJob.max_attempts,
                )
                .order_by(ExecutionJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                await db.commit()
                return None
            job.status = "running"
            job.leased_by = self.worker_id
            job.leased_at = now
            job.attempts += 1
            await db.commit()
            return job

    async def heartbeat(self, job_id: uuid.UUID) -> None:
        assert database.async_session_factory is not None
        while self._running:
            await asyncio.sleep(max(5, self.lease_seconds // 3))
            async with database.async_session_factory() as db:
                job = await db.get(ExecutionJob, job_id)
                if job is None or job.status != "running" or job.leased_by != self.worker_id:
                    return
                job.leased_at = datetime.utcnow()
                await db.commit()

    async def execute(self, job: ExecutionJob) -> None:
        assert database.async_session_factory is not None
        heartbeat = asyncio.create_task(self.heartbeat(job.id))
        try:
            if job.job_type == "agentic_task" and job.plan_id is not None:
                await self.scheduler.execute(str(job.plan_id), str(job.run_id))
            elif job.job_type == "deterministic_workflow":
                from packages.task_runtime.workflow_executor import DeterministicWorkflowExecutor

                executor = DeterministicWorkflowExecutor(database.async_session_factory, self.scheduler)
                await executor.execute(job.run_id)
            else:
                raise RuntimeError(f"Unsupported execution job type: {job.job_type}")

            async with database.async_session_factory() as db:
                fresh_job = await db.get(ExecutionJob, job.id)
                run = await db.get(WorkflowRun, job.run_id)
                if fresh_job is not None and fresh_job.status != "cancelled":
                    fresh_job.status = "failed" if run and run.status in {ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT} else "completed"
                    fresh_job.completed_at = datetime.utcnow()
                    fresh_job.leased_at = None
                    fresh_job.leased_by = None
                await db.commit()
        except Exception as exc:
            logger.exception("Execution job %s failed", job.id)
            async with database.async_session_factory() as db:
                fresh_job = await db.get(ExecutionJob, job.id)
                run = await db.get(WorkflowRun, job.run_id)
                if fresh_job is not None:
                    fresh_job.error = str(exc)
                    fresh_job.leased_at = None
                    fresh_job.leased_by = None
                    if fresh_job.attempts < fresh_job.max_attempts:
                        fresh_job.status = "queued"
                        fresh_job.available_at = datetime.utcnow() + timedelta(seconds=min(60, 2 ** fresh_job.attempts))
                    else:
                        fresh_job.status = "failed"
                        fresh_job.completed_at = datetime.utcnow()
                if run is not None and run.status not in {
                    ExecutionStatus.CANCELLED,
                    ExecutionStatus.AWAITING_APPROVAL,
                    ExecutionStatus.AWAITING_REVIEW,
                    ExecutionStatus.NEEDS_REVIEW,
                }:
                    run.status = ExecutionStatus.FAILED
                    run.error = str(exc)
                    run.completed_at = datetime.utcnow()
                await db.commit()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def run_forever(self) -> None:
        logger.info("Durable worker %s started", self.worker_id)
        while self._running:
            job = await self.claim()
            if job is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            logger.info("Claimed job=%s type=%s run=%s", job.id, job.job_type, job.run_id)
            await self.execute(job)


async def main() -> None:
    init_engine()
    await init_db()
    assert database.async_session_factory is not None
    bus = RedisMessageBus(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    try:
        await bus.connect()
    except Exception:
        logger.warning("Redis unavailable; worker will use the durable database ledger only")
        bus = None  # type: ignore[assignment]
    scheduler = TaskScheduler(database.async_session_factory, message_bus=bus)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    worker = DurableWorker(scheduler, worker_id=worker_id)
    try:
        await worker.run_forever()
    finally:
        if bus is not None:
            await bus.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
