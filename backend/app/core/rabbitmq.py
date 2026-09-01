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
from aio_pika import ExchangeType, Message, delivery_mode

from app.config import get_settings

logger = logging.getLogger(__name__)

EXCHANGE_NAME: Final[str] = "task_main_exchange"


class RabbitMQPublisher:
    """Thin wrapper around aio-pika for publishing task messages."""

    def __init__(self) -> None:
        self._connection: aio_pika.Connection | None = None
        self._channel: aio_pika.Channel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        """Establish connection, channel, and declare the main exchange."""
        settings = get_settings()
        self._connection = await aio_pika.connect(
            settings.rabbitmq_url,
            timeout=10,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=100)

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

    async def publish(self, task_id: str, task_type: str) -> None:
        """Publish a task message to the main exchange.

        Args:
            task_id: UUID string of the task to process.
            task_type: routing key (e.g. 'email_send').
        """
        if self._exchange is None:
            raise RuntimeError("RabbitMQ not connected. Call connect() first.")

        body = task_id.encode("utf-8")
        message = Message(
            body,
            content_type="text/plain",
            delivery_mode=delivery_mode.PERSISTENT,
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
    if _publisher is None:
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
