"""Publisher channel QoS must equal the configured per-worker concurrency."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core import rabbitmq


@pytest.mark.asyncio
async def test_connect_sets_prefetch_to_worker_concurrency(monkeypatch):
    monkeypatch.setattr(
        rabbitmq,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "rabbitmq_url": "amqp://guest:guest@localhost/",
                "worker_concurrency": 7,
            },
        )(),
    )

    channel = AsyncMock()
    connection = AsyncMock()
    connection.channel.return_value = channel

    with patch.object(
        rabbitmq.aio_pika, "connect", AsyncMock(return_value=connection)
    ):
        publisher = rabbitmq.RabbitMQPublisher()
        await publisher.connect()

    channel.set_qos.assert_awaited_once_with(prefetch_count=7)
