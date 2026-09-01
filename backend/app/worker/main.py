"""TaskForge worker — consumes tasks from RabbitMQ and processes them.

Phase 3: real handlers, TaskAttempt lifecycle tracking, exponential backoff
retries, and dead-letter queue routing.
Phase 4: worker registration, heartbeat loop, and graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import aio_pika
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.rabbitmq import close_publisher, get_publisher
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration
from app.worker.handlers import get_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

EXCHANGE_NAME = "task_main_exchange"
TASK_TYPES = ["email_send", "image_resize", "webhook_delivery"]

_RETRY_BASE_DELAY_SECONDS = 5
_RETRY_MAX_DELAY_SECONDS = 60

_TIMEOUT_MAP: dict[str, str] = {
    "email_send": "task_email_timeout_seconds",
    "image_resize": "task_image_resize_timeout_seconds",
    "webhook_delivery": "task_webhook_timeout_seconds",
}

_HEARTBEAT_INTERVAL_SECONDS = 15

_SETTINGS = get_settings()
_WORKER_HOSTNAME: str = os.environ.get("WORKER_HOSTNAME", socket.gethostname())


def _get_timeout(task_type: str) -> int:
    setting_name = _TIMEOUT_MAP.get(task_type, "task_webhook_timeout_seconds")
    return getattr(_SETTINGS, setting_name)


def _calculate_retry_delay(attempt_count: int) -> int:
    delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt_count - 1))
    return min(delay, _RETRY_MAX_DELAY_SECONDS)


async def create_attempt(db, task: Task, worker_id=None) -> TaskAttempt:
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=task.attempt_count + 1,
        worker_id=worker_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def _mark_success(db, task: Task, attempt: TaskAttempt, worker_id=None) -> None:
    task.status = "succeeded"
    task.completed_at = datetime.now(timezone.utc)
    attempt.outcome = "success"
    attempt.finished_at = datetime.now(timezone.utc)
    attempt.error_message = None
    attempt.error_detail = None
    await db.commit()
    await _update_worker_stats(db, worker_id, tasks_processed=1)


async def _mark_failure(
    db, task: Task, attempt: TaskAttempt, outcome: str, exc: Exception | None = None, worker_id=None
) -> None:
    attempt.outcome = outcome
    attempt.finished_at = datetime.now(timezone.utc)
    if exc is not None:
        attempt.error_message = str(exc)
        attempt.error_detail = {"traceback": traceback.format_exc()}
    await db.commit()
    if outcome == "failure":
        await _update_worker_stats(db, worker_id, tasks_failed=1)


async def _update_worker_stats(
    db,
    worker_id,
    tasks_processed: int = 0,
    tasks_failed: int = 0,
) -> None:
    if worker_id is None:
        return
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .values(
            tasks_processed=WorkerRegistration.tasks_processed + tasks_processed,
            tasks_failed=WorkerRegistration.tasks_failed + tasks_failed,
        )
    )
    await db.commit()


async def _register_worker(db) -> WorkerRegistration:
    worker = WorkerRegistration(
        hostname=_WORKER_HOSTNAME,
        status="online",
        concurrency_limit=_SETTINGS.worker_concurrency,
    )
    db.add(worker)
    await db.flush()
    await db.refresh(worker)
    logger.info("Worker registered: id=%s hostname=%s", worker.id, worker.hostname)
    return worker


async def _update_heartbeat(db, worker: WorkerRegistration) -> None:
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker.id)
        .values(
            last_heartbeat_at=datetime.now(timezone.utc),
            current_task_count=WorkerRegistration.current_task_count,
        )
    )
    await db.commit()


async def _set_worker_offline(db, worker_id) -> None:
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .values(status="offline")
    )
    await db.commit()
    logger.info("Worker marked offline: id=%s", worker_id)


async def consume_task(
    db, task_id: str, task_type: str, worker_id=None
) -> tuple[str, int, int]:
    """Process a single task.

    Returns:
        (final_status, attempt_count, max_attempts)
    """
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.attempts))
    )
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Task %s not found in DB — skipping.", task_id)
        return "not_found", 0, 0

    if task.status in ("cancelled", "succeeded"):
        logger.info("Task %s already terminal — skipping.", task_id)
        return task.status, task.attempt_count, task.max_attempts

    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    task.attempt_count += 1
    max_attempts = task.max_attempts
    await db.flush()

    attempt = await create_attempt(db, task, worker_id=worker_id)
    await db.commit()

    logger.info(
        "Processing task %s (type=%s, attempt=%d, status=%s, worker=%s)",
        task_id,
        task_type,
        attempt.attempt_number,
        task.status,
        worker_id,
    )

    handler = get_handler(task_type)
    timeout = _get_timeout(task_type)

    try:
        await asyncio.wait_for(handler(task.payload), timeout=timeout)
        await _mark_success(db, task, attempt, worker_id=worker_id)
        return "succeeded", task.attempt_count, max_attempts

    except asyncio.TimeoutError as exc:
        await _mark_failure(db, task, attempt, "timeout", exc, worker_id=worker_id)
        return "timeout", task.attempt_count, max_attempts

    except (ValueError, OSError) as exc:
        await _mark_failure(db, task, attempt, "failure", exc, worker_id=worker_id)
        return "failed", task.attempt_count, max_attempts


async def _publish_retry(publisher, task_id: str, task_type: str, attempt_count: int) -> None:
    delay = _calculate_retry_delay(attempt_count)
    body = task_id.encode("utf-8")
    message = aio_pika.Message(
        body,
        content_type="text/plain",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        headers={
            "x-task-type": task_type,
            "x-task-id": task_id,
        },
        expiration=str(delay * 1000),
    )
    await publisher._exchange.publish(
        message,
        routing_key=f"tasks.{task_type}.retry",
    )
    logger.info(
        "Published retry for task %s with %ds delay.",
        task_id,
        delay,
    )


async def on_message(message: aio_pika.Message, publisher, worker_id=None) -> None:
    task_id = message.body.decode("utf-8")
    task_type = message.headers.get("x-task-type", "unknown")
    try:
        async with AsyncSessionLocal() as db:
            final_status, attempt_count, max_attempts = await consume_task(
                db, task_id, task_type, worker_id=worker_id
            )

        if final_status == "not_found":
            await message.ack()
            return

        if attempt_count < max_attempts:
            await _publish_retry(publisher, task_id, task_type, attempt_count)

        await message.ack()

    except Exception:
        logger.exception("Error processing task %s", task_id)
        await message.ack()


async def _heartbeat_loop(worker: WorkerRegistration) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                await _update_heartbeat(db, worker)
        except Exception:
            logger.exception("Heartbeat update failed for worker %s", worker.id)


async def subscribe_queues(publisher, worker_id=None) -> None:
    channel = publisher._channel
    if channel is None:
        raise RuntimeError("RabbitMQ channel not available.")

    exchange = publisher._exchange
    if exchange is None:
        raise RuntimeError("RabbitMQ exchange not available.")

    async def _make_handler(pub):
        async def handler(msg):
            await on_message(msg, pub, worker_id=worker_id)
        return handler

    for task_type in TASK_TYPES:
        main_queue_name = f"tasks.{task_type}"
        queue = await channel.declare_queue(
            main_queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": f"tasks.{task_type}.dlq",
            },
        )
        await queue.bind(exchange, routing_key=task_type)
        await queue.consume(_make_handler(publisher))
        logger.info(
            "Subscribed to queue '%s' (routing key: %s).",
            main_queue_name,
            task_type,
        )

        retry_queue_name = f"tasks.{task_type}.retry"
        retry_queue = await channel.declare_queue(
            retry_queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": main_queue_name,
            },
        )
        await retry_queue.bind(
            exchange, routing_key=f"tasks.{task_type}.retry"
        )
        await retry_queue.consume(_make_handler(publisher))
        logger.info("Subscribed to retry queue '%s'.", retry_queue_name)

        dlq_queue_name = f"tasks.{task_type}.dlq"
        dlq_queue = await channel.declare_queue(
            dlq_queue_name,
            durable=True,
        )
        await dlq_queue.bind(exchange, routing_key=f"tasks.{task_type}.dlq")
        logger.info("Declared DLQ '%s' (messages are terminal).", dlq_queue_name)


async def main() -> None:
    logger.info("Starting TaskForge worker (hostname=%s)...", _WORKER_HOSTNAME)

    publisher = await get_publisher()
    worker = None

    try:
        async with AsyncSessionLocal() as db:
            worker = await _register_worker(db)

        heartbeat_task = asyncio.create_task(_heartbeat_loop(worker))

        await subscribe_queues(publisher, worker_id=str(worker.id))
        logger.info("Worker ready. Waiting for messages...")

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def _handle_signal() -> None:
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass

        await shutdown_event.wait()

    except Exception:
        logger.exception("Unexpected error in worker main loop")
    finally:
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
