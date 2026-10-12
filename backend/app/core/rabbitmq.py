"""RabbitMQ publisher using aio-pika with a direct exchange per task type.

Per DATABASE.md:
- Exchange: `task_main_exchange` (direct)
- Routing key: task_type (e.g. `email_send`, `webhook_delivery`)
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

    async def publish(
        self,
        task_id: str,
        task_type: str,
        priority: int = 0,
        traceparent: str | None = None,
        routing_key: str | None = None,
        route_by_priority: bool = False,
    ) -> None:
        """Publish a task message to the main exchange.

        Args:
            task_id: UUID string of the task to process.
            task_type: logical task type (e.g. 'email_send').
            priority: integer priority (clamped to 0-10 for AMQP priority queues).
            traceparent: optional W3C traceparent context string.
            routing_key: explicit AMQP routing key override.
            route_by_priority: if True, routes directly to tasks.{tier}.
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

        from app.core.tracing import create_traceparent
        from app.worker.priority import get_priority_tier

        tp = traceparent or create_traceparent()
        clamped_priority = max(0, min(10, int(priority)))
        tier = get_priority_tier(clamped_priority)

        if routing_key is not None:
            resolved_routing_key = routing_key
        elif route_by_priority:
            resolved_routing_key = f"tasks.{tier}"
        else:
            resolved_routing_key = task_type

        body = task_id.encode("utf-8")
        headers = {
            "x-task-type": task_type,
            "x-task-id": task_id,
            "traceparent": tp,
            "x-priority": clamped_priority,
            "x-priority-tier": tier,
        }
        message = Message(
            body,
            content_type="text/plain",
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=clamped_priority,
            headers=headers,
        )
        await self._exchange.publish(message, routing_key=resolved_routing_key)
        logger.info(
            "Published task %s to exchange '%s' with routing key '%s' (priority=%d, tier=%s, traceparent=%s).",
            task_id,
            EXCHANGE_NAME,
            resolved_routing_key,
            clamped_priority,
            tier,
            tp,
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


async def publish_task(
    task_id: str,
    task_type: str,
    priority: int = 0,
    traceparent: str | None = None,
    routing_key: str | None = None,
    route_by_priority: bool = False,
) -> None:
    """Convenience function to publish a task message."""
    publisher = await get_publisher()
    await publisher.publish(
        task_id,
        task_type,
        priority=priority,
        traceparent=traceparent,
        routing_key=routing_key,
        route_by_priority=route_by_priority,
    )



async def purge_queue(queue_name: str) -> int:
    """Purge all messages from a queue, returning the count of messages purged."""
    publisher = await get_publisher()
    if publisher.channel is None or publisher.channel.is_closed:
        await publisher.connect()
    try:
        queue = await publisher.channel.get_queue(queue_name, ensure=False)
        return await queue.purge()
    except Exception as exc:
        logger.warning("Could not purge queue %s: %s", queue_name, exc)
        return 0


async def get_queue_depths() -> dict[str, int]:
    """Return {queue_name: message_count} for all taskforge queues.

    Queries the RabbitMQ management API. Returns empty dict on failure.
    Uses a fast 1.0s timeout to avoid blocking callers on cache miss.
    """
    settings = get_settings()
    management_url = settings.rabbitmq_management_url
    vhost = settings.rabbitmq_vhost

    import httpx

    url = f"{management_url}/api/queues/{vhost}"
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
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


BACKPRESSURE_CACHE_KEY: Final[str] = "backpressure:total_depth"
QUEUE_DEPTH_CACHE_KEY: Final[str] = "queue:total_depth"

try:
    from prometheus_client import REGISTRY, Counter

    try:
        backpressure_shed_total = Counter(
            "backpressure_shed_total",
            "Total number of requests rejected by backpressure admission control (HTTP 429)",
            registry=REGISTRY,
        )
    except ValueError:
        backpressure_shed_total = getattr(REGISTRY, "_names_to_collectors", {}).get("backpressure_shed_total")
except Exception:
    backpressure_shed_total = None


async def sample_queue_depths(
    redis_client=None, key: str = BACKPRESSURE_CACHE_KEY
) -> int:
    """Sample current RabbitMQ queue depths and update Redis cache.

    Writes to Redis with a 2-second TTL. Returns total queue depth.
    """
    depths = await get_queue_depths()
    total = sum(depths.values())
    try:
        if redis_client is None:
            from app.core.redis import get_redis
            redis_client = await get_redis()
        if redis_client is not None:
            await redis_client.set(key, total, ex=2)
    except Exception:
        logger.warning("Failed to cache queue depth in Redis", exc_info=True)
    return total


async def check_backpressure() -> None:
    """Raise HTTPException(status=429) if queue depth exceeds threshold.

    Reads cached queue depth from Redis in <1ms.
    If cache misses, samples RabbitMQ depths with a fast 1s timeout.
    Fails open if Redis or RabbitMQ are unreachable.
    """
    settings = get_settings()
    if not settings.backpressure_enabled:
        return

    total: int | None = None
    redis_client = None
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        # Fast path: check Redis cache in <1ms
        cached = await redis_client.get(BACKPRESSURE_CACHE_KEY)
        if cached is None:
            cached = await redis_client.get(QUEUE_DEPTH_CACHE_KEY)
        if cached is not None:
            total = int(cached)
    except Exception:
        pass

    if total is None:
        total = await sample_queue_depths(redis_client=redis_client)

    threshold = getattr(settings, "backpressure_critical_depth", None)
    if threshold is None or not isinstance(threshold, (int, float)):
        threshold = settings.backpressure_queue_depth_threshold

    if total > threshold:
        logger.warning(
            "Backpressure triggered: total queue depth %d exceeds critical threshold %d.",
            total,
            threshold,
        )
        if backpressure_shed_total is not None:
            try:
                backpressure_shed_total.inc()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "QUEUE_FULL",
                    "message": "Task queue saturated, system in backpressure shedding mode",
                    "field": None,
                }
            },
            headers={"Retry-After": "5"},
        )


