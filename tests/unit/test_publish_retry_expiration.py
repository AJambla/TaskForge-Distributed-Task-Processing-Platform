"""Retry messages must carry an expiration aio_pika can encode (not a str)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.worker.main import _publish_retry


@pytest.mark.asyncio
async def test_publish_retry_sets_encodable_expiration():
    publisher = AsyncMock()

    await _publish_retry(publisher, "task-123", "email_send", 5)

    message = publisher.exchange.publish.await_args.args[0]
    routing_key = publisher.exchange.publish.await_args.kwargs["routing_key"]
    assert routing_key == "tasks.email_send.retry.5s"
    assert message.headers["x-task-id"] == "task-123"
    assert message.headers["x-task-type"] == "email_send"
