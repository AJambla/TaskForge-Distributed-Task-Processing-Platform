"""Retry logic and bucketed backoff routing for TaskForge workers (IMP-09, IMP-21)."""
from __future__ import annotations

import logging
from typing import Sequence

import aio_pika

logger = logging.getLogger("worker.retry")

RETRY_BUCKETS: tuple[int, ...] = (5, 10, 20, 40, 60)
RETRY_BASE_DELAY_SECONDS = 5
RETRY_MAX_DELAY_SECONDS = 60


def calculate_retry_delay(attempt_count: int, buckets: Sequence[int] = RETRY_BUCKETS) -> int:
    """Calculate exponential backoff delay snapped to the nearest bucket queue."""
    delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt_count - 1))
    target = min(delay, RETRY_MAX_DELAY_SECONDS)
    for bucket in buckets:
        if bucket >= target:
            return bucket
    return buckets[-1]


async def publish_retry(
    publisher, task_id: str, task_type: str, delay_seconds: int
) -> None:
    """Publish a retry message to a discrete bucketed retry queue with uniform TTL."""
    # Find smallest bucket >= delay_seconds, or max bucket
    delay = RETRY_BUCKETS[-1]
    for b in RETRY_BUCKETS:
        if b >= delay_seconds:
            delay = b
            break

    body = task_id.encode("utf-8")
    message = aio_pika.Message(
        body,
        content_type="text/plain",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        headers={
            "x-task-type": task_type,
            "x-task-id": task_id,
        },
    )
    routing_key = f"tasks.{task_type}.retry.{delay}s"
    await publisher.exchange.publish(
        message,
        routing_key=routing_key,
    )
    logger.info(
        "Published retry for task %s to bucket '%s' (%ds delay).",
        task_id,
        routing_key,
        delay,
    )
