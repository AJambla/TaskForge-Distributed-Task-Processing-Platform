"""queue.consume must receive a callable coroutine function, not a coroutine object."""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from app.worker import main as worker_main


@pytest.mark.asyncio
async def test_subscribe_queues_passes_callable_coroutine(monkeypatch):
    consumed = []

    async def fake_consume(callback):
        consumed.append(callback)

    queue = AsyncMock()
    queue.consume.side_effect = fake_consume
    channel = AsyncMock()
    channel.declare_queue.return_value = queue

    publisher = AsyncMock()
    publisher._channel = channel
    publisher._exchange = AsyncMock()

    await worker_main.subscribe_queues(publisher)

    assert consumed, "no consumer was registered"
    for callback in consumed:
        assert callable(callback)
        assert inspect.iscoroutinefunction(callback)
