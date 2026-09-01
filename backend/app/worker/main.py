"""Stub worker — consumes tasks from RabbitMQ and logs them.

This is a Phase 2 stub. In Phase 3, real task handlers (email, image, webhook)
will be added here.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import aio_pika
from sqlalchemy import select

from app.core.rabbitmq import close_publisher, get_publisher
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.task import Task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

EXCHANGE_NAME = "task_main_exchange"
TASK_TYPES = ["email_send", "image_resize", "webhook_delivery"]


async def consume_task(task_id: str, task_type: str) -> None:
    """Process a single task (stub — logs and marks succeeded)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            logger.warning("Task %s not found in DB — skipping.", task_id)
            return

        if task.status in ("cancelled", "succeeded"):
            logger.info("Task %s already terminal — skipping.", task_id)
            return

        logger.info(
            "Processing task %s (type=%s, status=%s)",
            task_id,
            task_type,
            task.status,
        )

        # Stub: simulate work with a short sleep
        await asyncio.sleep(0.1)

        task.status = "succeeded"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Task %s marked succeeded.", task_id)


async def on_message(message: aio_pika.Message) -> None:
    """Callback invoked for each consumed message."""
    task_id = message.body.decode("utf-8")
    task_type = message.headers.get("x-task-type", "unknown")
    try:
        await consume_task(task_id, task_type)
        await message.ack()
    except Exception:
        logger.exception("Error processing task %s", task_id)
        await message.nack(requeue=True)


async def subscribe_queues(publisher) -> None:
    """Declare queues and bind them to the exchange for each task type."""
    channel = publisher._channel
    if channel is None:
        raise RuntimeError("RabbitMQ channel not available.")

    exchange = publisher._exchange
    if exchange is None:
        raise RuntimeError("RabbitMQ exchange not available.")

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
        await queue.consume(on_message)
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
                "x-message-ttl": 5000,
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": main_queue_name,
            },
        )
        await retry_queue.bind(
            exchange, routing_key=f"tasks.{task_type}.retry"
        )
        await retry_queue.consume(on_message)
        logger.info("Subscribed to retry queue '%s'.", retry_queue_name)

        dlq_queue_name = f"tasks.{task_type}.dlq"
        dlq_queue = await channel.declare_queue(
            dlq_queue_name,
            durable=True,
        )
        await dlq_queue.bind(exchange, routing_key=f"tasks.{task_type}.dlq")
        logger.info("Declared DLQ '%s' (messages are terminal).", dlq_queue_name)


async def main() -> None:
    """Worker entrypoint."""
    logger.info("Starting TaskForge worker...")

    publisher = await get_publisher()
    try:
        await subscribe_queues(publisher)
        logger.info("Worker ready. Waiting for messages...")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
    finally:
        await close_publisher()
        await engine.dispose()
        await close_redis()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
