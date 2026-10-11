"""RabbitMQ publisher using aio-pika with a direct exchange per task type.

Per DATABASE.md:
- Exchange: `task_main_exchange` (direct)
- Routing key: task_type (e.g. `email_send`, `image_resize`, `webhook_delivery`)
- Message body: only the task_id (worker fetches payload from Postgres)
- Queues are declared lazily on first publish; workers bind the same queues.
"""
from __future__ import annotations

import logging
from typing import Final

import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode
from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)

EXCHANGE_NAME: Final[str] = "task_main_exchange"


class RabbitMQPublisher:
    """Thin wrapper around aio-pika for publishing task messages."""

    def __init__(self) -> None:
        self._connection: aio_pika.Connection | None = None
        self._channel: aio_pika.Channel | None = None
        self._exchange: aio_pika.Exchange | None = None

    @property
    def connection(self) -> aio_pika.Connection | None:
        return self._connection

    @property
    def channel(self) -> aio_pika.Channel | None:
        return self._channel

    @property
    def exchange(self) -> aio_pika.Exchange | None:
        return self._exchange

    async def connect(self) -> None:
        """Establish robust connection, channel, and declare the main exchange."""
        settings = get_settings()
        self._connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            timeout=10,
        )
        self._channel = await self._connection.channel()
        # prefetch == per-worker concurrency limit
        await self._channel.set_qos(prefetch_count=settings.worker_concurrency)

        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )
        logger.info("RabbitMQ connected and exchange '%s' declared.", EXCHANGE_NAME)

    async def close(self) -> None:
        """Close the connection gracefully."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed.")
        self._connection = None
        self._channel = None
        self._exchange = None

    async def publish(self, task_id: str, task_type: str) -> None:
        """Publish a task message to the main exchange.

        Args:
            task_id: UUID string of the task to process.
            task_type: routing key (e.g. 'email_send').
        """
        if self._connection is None or self._connection.is_closed:
            await self.connect()

        if self._exchange is None or self._channel is None or self._channel.is_closed:
            if self._channel is None or self._channel.is_closed:
                self._channel = await self._connection.channel()
                settings = get_settings()
                await self._channel.set_qos(prefetch_count=settings.worker_concurrency)
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME,
                ExchangeType.DIRECT,
                durable=True,
            )

        body = task_id.encode("utf-8")
        message = Message(
            body,
            content_type="text/plain",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={
                "x-task-type": task_type,
                "x-task-id": task_id,
            },
        )
        await self._exchange.publish(message, routing_key=task_type)
        logger.info(
            "Published task %s to exchange '%s' with routing key '%s'.",
            task_id,
            EXCHANGE_NAME,
            task_type,
        )


_publisher: RabbitMQPublisher | None = None


async def get_publisher() -> RabbitMQPublisher:
    """Lazily create and cache the RabbitMQ publisher singleton."""
    global _publisher
    if _publisher is None or _publisher.connection is None or _publisher.connection.is_closed:
        _publisher = RabbitMQPublisher()
        await _publisher.connect()
    return _publisher


async def close_publisher() -> None:
    """Close the cached publisher (called on shutdown)."""
    global _publisher
    if _publisher is not None:
        await _publisher.close()
        _publisher = None


async def publish_task(task_id: str, task_type: str) -> None:
    """Convenience function to publish a task message."""
    publisher = await get_publisher()
    await publisher.publish(task_id, task_type)


async def get_queue_depths() -> dict[str, int]:
    """Return {queue_name: message_count} for all taskforge queues.

    Queries the RabbitMQ management API. Returns empty dict on failure.
    """
    settings = get_settings()
    management_url = settings.rabbitmq_management_url
    vhost = settings.rabbitmq_vhost

    import httpx

    url = f"{management_url}/api/queues/{vhost}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "RabbitMQ management API returned %d — returning empty depths.",
                    resp.status_code,
                )
                return {}
            queues = resp.json()
            return {q["name"]: q.get("messages", 0) for q in queues}
    except Exception:
        logger.warning("Failed to query RabbitMQ management API for queue depths.", exc_info=True)
        return {}


async def check_backpressure() -> None:
    """Raise HTTPException(status=429) if queue depth exceeds threshold.

    Reads from Redis cache with a 2-second TTL to avoid hitting RabbitMQ
    management API on every request. Fails open if check fails.
    """
    settings = get_settings()
    if not settings.backpressure_enabled:
        return

    total: int | None = None
    redis_client = None
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        cached = await redis_client.get("backpressure:total_depth")
        if cached is not None:
            total = int(cached)
    except Exception:
        pass

    if total is None:
        depths = await get_queue_depths()
        total = sum(depths.values())
        if redis_client is not None:
            try:
                await redis_client.set("backpressure:total_depth", total, ex=2)
            except Exception:
                pass

    if total > settings.backpressure_queue_depth_threshold:
        logger.warning(
            "Backpressure triggered: total queue depth %d exceeds threshold %d.",
            total,
            settings.backpressure_queue_depth_threshold,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "QUEUE_FULL",
                    "message": "System is backpressuring. Please retry.",
                    "field": None,
                }
            },
            headers={"Retry-After": "30"},
        )
