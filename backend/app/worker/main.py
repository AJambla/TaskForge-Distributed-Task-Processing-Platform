"""TaskForge worker — consumes tasks from RabbitMQ and processes them.

Modular architecture (IMP-21):
- `consumer.py`: AMQP queue declaration, consumer subscriptions, message lifecycle.
- `executor.py`: Handler execution, sandbox processes, timeout enforcement.
- `lifecycle.py`: Worker DB registration, heartbeats, and status transitions.
- `retry.py`: Exponential backoff math and bucketed queue delay routing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import aio_pika
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.rabbitmq import close_publisher, get_publisher
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.task import Task
from app.models.worker_registration import WorkerRegistration
from app.worker.consumer import (
    TASK_TYPES,
    _inflight_tasks,
    subscribe_queues as _consumer_subscribe_queues,
)
from app.worker.context import TaskContext
from app.worker.executor import get_timeout as _get_timeout, run_handler_in_sandbox as _run_handler_in_sandbox
from app.worker.handlers import get_handler, get_handler_metadata
from app.worker.lifecycle import (
    _HEARTBEAT_INTERVAL_SECONDS,
    _WORKER_HOSTNAME,
    create_attempt,
    mark_failure as _mark_failure,
    mark_success as _mark_success,
    register_worker as _register_worker,
    set_worker_offline as _set_worker_offline,
    update_heartbeat as _update_heartbeat,
)
from app.worker.metrics import (
    start_metrics_server,
    task_attempts_total,
    task_duration_seconds,
    tasks_processed_total,
)
from app.worker.retry import (
    calculate_retry_delay as _calculate_retry_delay,
    publish_retry as _publish_retry,
)

_SETTINGS = get_settings()

configure_logging(
    service_name=f"worker-{_SETTINGS.worker_hostname}",
    log_level=_SETTINGS.log_level,
    json_format=(_SETTINGS.log_format == "json"),
)
logger = logging.getLogger("worker")

_active_task_count = 0
_SHUTDOWN_TIMEOUT_SECONDS = 30


async def consume_task(
    db, task_id: str, task_type: str, worker_id=None, traceparent: str | None = None
) -> tuple[str, int, int, int | None]:
    """Process a single task.

    Returns:
        (final_status, attempt_count, max_attempts, defer_seconds)
    """
    from app.core.tracing import extract_trace_context
    trace_id, span_id = extract_trace_context({"traceparent": traceparent} if traceparent else None)

    from app.core.tracing import extract_context_from_carrier, get_tracer
    from opentelemetry.trace import Status, StatusCode

    carrier = {"traceparent": traceparent} if traceparent else None
    extracted_ctx = extract_context_from_carrier(carrier)
    tracer = get_tracer("taskforge.worker")

    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.attempts))
    )
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("[trace=%s] Task %s not found in DB — skipping.", trace_id, task_id)
        return "not_found", 0, 0, None

    # Resolve trace_id from task or inbound trace
    resolved_trace_id = getattr(task, "trace_id", None) or trace_id

    if task.status in ("cancelled", "succeeded"):
        logger.info("[trace=%s] Task %s already terminal — skipping.", resolved_trace_id, task_id)
        return task.status, task.attempt_count, task.max_attempts, None

    if task.run_at and task.run_at > datetime.now(timezone.utc):
        defer_seconds = int((task.run_at - datetime.now(timezone.utc)).total_seconds()) + 1
        logger.info(
            "[trace=%s] Task %s scheduled for %s — deferring %ds.",
            resolved_trace_id,
            task_id,
            task.run_at.isoformat(),
            defer_seconds,
        )
        return "scheduled", task.attempt_count, task.max_attempts, defer_seconds

    # Measure queue latency if created_at exists
    now_utc = datetime.now(timezone.utc)
    queue_latency_ms = None
    if task.created_at:
        queue_latency_ms = max(0.0, (now_utc - task.created_at).total_seconds() * 1000.0)

    task.status = "running"
    task.started_at = now_utc
    task.attempt_count += 1
    max_attempts = task.max_attempts
    await db.flush()

    attempt = await create_attempt(db, task, worker_id=worker_id, trace_id=resolved_trace_id)
    task_attempts_total.inc()
    await db.commit()

    logger.info(
        "[trace=%s] Processing task %s (type=%s, attempt=%d, status=%s, worker=%s)",
        resolved_trace_id,
        task_id,
        task_type,
        attempt.attempt_number,
        task.status,
        worker_id,
    )

    handler = get_handler(task_type)
    timeout = _get_timeout(task_type)

    global _active_task_count
    _active_task_count += 1
    try:
        with tracer.start_as_current_span("task.execute", context=extracted_ctx) as span:
            span.set_attribute("task.id", str(task_id))
            span.set_attribute("task.type", str(task_type))
            span.set_attribute("task.priority", int(task.priority))
            span.set_attribute("task.attempt", int(attempt.attempt_number))
            if worker_id:
                span.set_attribute("worker.id", str(worker_id))
            span.set_attribute("worker.hostname", _SETTINGS.worker_hostname)
            if queue_latency_ms is not None:
                span.set_attribute("queue_latency_ms", float(queue_latency_ms))

            try:
                # Pluggable Handler Context support (FEAT-06)
                ctx = TaskContext(
                    task_id=task_id,
                    task_type=task_type,
                    attempt=attempt.attempt_number,
                    worker_id=worker_id,
                    trace_id=resolved_trace_id,
                )
                meta = get_handler_metadata(task_type)
                pass_ctx = meta.get("has_context", False) if meta else False

                start = asyncio.get_event_loop().time()
                if sys.platform != "win32" and _SETTINGS.sandbox_enabled:
                    result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, _run_handler_in_sandbox, handler, task.payload, ctx if pass_ctx else None
                        ),
                        timeout=timeout,
                    )
                else:
                    handler_coro = handler(task.payload, ctx) if pass_ctx else handler(task.payload)
                    result = await asyncio.wait_for(handler_coro, timeout=timeout)
                elapsed = asyncio.get_event_loop().time() - start
                span.set_attribute("execution_latency_ms", float(elapsed * 1000.0))
                span.set_attribute("task.status", "succeeded")
                span.set_status(Status(StatusCode.OK))
                task_duration_seconds.labels(task_type=task_type).observe(elapsed)

                await _mark_success(db, task, attempt, worker_id=worker_id, result=result)
                tasks_processed_total.labels(
                    outcome="success", task_type=task_type
                ).inc()
                return "succeeded", task.attempt_count, max_attempts, None

            except asyncio.TimeoutError as exc:
                elapsed = asyncio.get_event_loop().time() - start
                span.set_attribute("execution_latency_ms", float(elapsed * 1000.0))
                span.set_attribute("task.status", "timeout")
                span.set_attribute("error.type", "TimeoutError")
                span.set_attribute("error.message", str(exc))
                span.set_status(Status(StatusCode.ERROR, description=str(exc)))
                task_duration_seconds.labels(task_type=task_type).observe(elapsed)
                await _mark_failure(
                    db, task, attempt, "timeout", exc, worker_id=worker_id
                )
                tasks_processed_total.labels(
                    outcome="timeout", task_type=task_type
                ).inc()
                return "timeout", task.attempt_count, max_attempts, None

            except Exception as exc:
                elapsed = asyncio.get_event_loop().time() - start
                span.set_attribute("execution_latency_ms", float(elapsed * 1000.0))
                span.set_attribute("task.status", "failure")
                span.set_attribute("error.type", exc.__class__.__name__)
                span.set_attribute("error.message", str(exc))
                span.set_status(Status(StatusCode.ERROR, description=str(exc)))
                task_duration_seconds.labels(task_type=task_type).observe(elapsed)
                await _mark_failure(
                    db, task, attempt, "failure", exc, worker_id=worker_id
                )
                tasks_processed_total.labels(
                    outcome="failure", task_type=task_type
                ).inc()
                return "failed", task.attempt_count, max_attempts, None
    finally:
        _active_task_count -= 1


async def on_message(message: aio_pika.Message, publisher, worker_id=None) -> None:
    """AMQP message callback."""
    task_id = message.body.decode("utf-8")
    task_type = message.headers.get("x-task-type", "unknown")
    traceparent = message.headers.get("traceparent")
    try:
        async with AsyncSessionLocal() as db:
            final_status, attempt_count, max_attempts, defer_seconds = (
                await consume_task(
                    db,
                    task_id,
                    task_type,
                    worker_id=worker_id,
                    traceparent=traceparent,
                )
            )

        if final_status in ("not_found", "succeeded", "cancelled"):
            await message.ack()
            return

        if final_status == "scheduled":
            await _publish_retry(publisher, task_id, task_type, defer_seconds)
            await message.ack()
            return

        if attempt_count < max_attempts:
            await _publish_retry(
                publisher, task_id, task_type, _calculate_retry_delay(attempt_count)
            )
            await message.ack()
            return

        marked_dead = False
        async with AsyncSessionLocal() as db_retry:
            result = await db_retry.execute(select(Task).where(Task.id == task_id))
            dead_task = result.scalar_one_or_none()
            if dead_task and dead_task.status != "succeeded":
                dead_task.status = "dead_letter"
                dead_task.completed_at = datetime.now(timezone.utc)
                await db_retry.commit()
                marked_dead = True
                logger.info(
                    "Task %s moved to dead_letter after %d/%d attempts.",
                    task_id,
                    attempt_count,
                    max_attempts,
                )

        if marked_dead:
            await message.reject(requeue=False)
        else:
            await message.ack()

    except Exception:
        logger.exception(
            "Unexpected error processing task %s — requeueing.", task_id
        )
        await message.reject(requeue=True)


async def _heartbeat_loop(worker: WorkerRegistration) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                await _update_heartbeat(db, worker, active_count=_active_task_count)
        except Exception:
            logger.exception("Heartbeat update failed for worker %s", worker.id)


async def subscribe_queues(publisher, worker_id=None, shutdown_event=None) -> list[tuple[Any, str]]:
    """Backward-compatible helper redirecting to consumer.subscribe_queues."""
    return await _consumer_subscribe_queues(
        publisher=publisher,
        on_message_callback=on_message,
        worker_id=worker_id,
        shutdown_event=shutdown_event,
        task_types=TASK_TYPES,
    )


async def main() -> None:
    """Worker main entrypoint."""
    _metrics_port = int(os.environ.get("PORT_METRICS", 9001))
    start_metrics_server(_metrics_port)

    logger.info("Starting TaskForge worker (hostname=%s)...", _WORKER_HOSTNAME)

    publisher = await get_publisher()
    worker = None
    heartbeat_task: asyncio.Task | None = None
    consumers: list[tuple[Any, str]] = []

    try:
        async with AsyncSessionLocal() as db:
            worker = await _register_worker(db)

        heartbeat_task = asyncio.create_task(_heartbeat_loop(worker))

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        consumers = await subscribe_queues(publisher, worker_id=str(worker.id), shutdown_event=shutdown_event)
        logger.info("Worker ready. Waiting for messages...")

        async def _on_reconnect():
            nonlocal consumers
            logger.info("RabbitMQ connection restored — resubscribing worker queues...")
            try:
                consumers = await subscribe_queues(publisher, worker_id=str(worker.id), shutdown_event=shutdown_event)
                logger.info("Successfully resubscribed queues after reconnect.")
            except Exception:
                logger.exception("Failed to resubscribe queues after reconnect.")

        if hasattr(publisher.connection, "reconnect_callbacks"):
            publisher.connection.reconnect_callbacks.add(lambda conn: asyncio.create_task(_on_reconnect()))

        def _handle_signal() -> None:
            logger.info("Shutdown signal received — initiating graceful drain...")
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass

        await shutdown_event.wait()

        for queue, tag in consumers:
            try:
                await queue.cancel(tag)
            except Exception:
                pass

        if _inflight_tasks:
            logger.info("Waiting for %d in-flight task(s) to finish...", len(_inflight_tasks))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(_inflight_tasks), return_exceptions=True),
                    timeout=_SHUTDOWN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for in-flight tasks to drain.")

    except Exception:
        logger.exception("Unexpected error in worker main loop")
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        if worker is not None:
            try:
                async with AsyncSessionLocal() as db:
                    await _set_worker_offline(db, worker.id)
            except Exception:
                logger.exception("Failed to mark worker offline")

        await close_publisher()
        await engine.dispose()
        await close_redis()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
