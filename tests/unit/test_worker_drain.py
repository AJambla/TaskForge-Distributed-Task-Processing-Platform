"""Unit tests for worker graceful shutdown and drain."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.worker import main as worker_main


@pytest.mark.asyncio
async def test_shutdown_rejects_and_requeues_incoming_messages():
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    channel = AsyncMock()
    queue = AsyncMock()
    consumer_callbacks = []

    async def fake_consume(callback):
        consumer_callbacks.append(callback)
        return "ctag-1"

    queue.consume = fake_consume
    channel.declare_queue.return_value = queue

    publisher = AsyncMock()
    publisher.channel = channel
    publisher.exchange = AsyncMock()

    consumers = await worker_main.subscribe_queues(
        publisher, worker_id="w-1", shutdown_event=shutdown_event
    )
    assert len(consumers) == len(worker_main.TASK_TYPES)

    # Invoke the handler with a mock message while shutdown_event is set
    handler = consumer_callbacks[0]
    msg = AsyncMock()
    await handler(msg)

    # Message must be rejected with requeue=True so another worker picks it up
    msg.reject.assert_awaited_once_with(requeue=True)
    msg.ack.assert_not_awaited()
