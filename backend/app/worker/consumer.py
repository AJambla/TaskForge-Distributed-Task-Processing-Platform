"""AMQP consumer and queue topology for TaskForge workers (IMP-21)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aio_pika

from app.worker.retry import RETRY_BUCKETS

logger = logging.getLogger("worker.consumer")

EXCHANGE_NAME = "task_main_exchange"
TASK_TYPES = ["email_send", "image_resize", "webhook_delivery"]
_inflight_tasks: set[asyncio.Task] = set()


async def subscribe_queues(
    publisher,
    on_message_callback,
    worker_id=None,
    shutdown_event=None,
    task_types: list[str] | None = None,
) -> list[tuple[Any, str]]:
    """Declare main queues, retry buckets, DLQs, and subscribe consumers."""
    channel = publisher.channel
    if channel is None:
        raise RuntimeError("RabbitMQ channel not available.")

    exchange = publisher.exchange
    if exchange is None:
        raise RuntimeError("RabbitMQ exchange not available.")

    types = task_types or TASK_TYPES

    def _make_handler(pub):
        async def handler(msg):
            if shutdown_event and shutdown_event.is_set():
                await msg.reject(requeue=True)
                return
            current = asyncio.current_task()
            if current:
                _inflight_tasks.add(current)
            try:
                await on_message_callback(msg, pub, worker_id=worker_id)
            finally:
                if current:
                    _inflight_tasks.discard(current)
        return handler

    consumers = []
    for task_type in types:
        main_queue_name = f"tasks.{task_type}"
        queue = await channel.declare_queue(
            main_queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": f"tasks.{task_type}.dlq",
                "x-max-priority": 10,
            },
        )
        await queue.bind(exchange, routing_key=task_type)
        tag = await queue.consume(_make_handler(publisher))
        if tag:
            consumers.append((queue, tag))
        logger.info(
            "Subscribed to queue '%s' (routing key: %s).",
            main_queue_name,
            task_type,
        )

        # Discrete bucketed retry queues
        for bucket_sec in RETRY_BUCKETS:
            bucket_queue_name = f"tasks.{task_type}.retry.{bucket_sec}s"
            bucket_queue = await channel.declare_queue(
                bucket_queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": EXCHANGE_NAME,
                    "x-dead-letter-routing-key": task_type,
                    "x-message-ttl": bucket_sec * 1000,
                },
            )
            await bucket_queue.bind(
                exchange, routing_key=f"tasks.{task_type}.retry.{bucket_sec}s"
            )
            logger.info("Declared bucketed retry queue '%s' (TTL=%ds).", bucket_queue_name, bucket_sec)

        dlq_queue_name = f"tasks.{task_type}.dlq"
        dlq_queue = await channel.declare_queue(
            dlq_queue_name,
            durable=True,
        )
        await dlq_queue.bind(exchange, routing_key=f"tasks.{task_type}.dlq")
        logger.info("Declared DLQ '%s' (messages are terminal).", dlq_queue_name)

    return consumers
