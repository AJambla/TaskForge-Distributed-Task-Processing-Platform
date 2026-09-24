"""Retry messages must carry an expiration aio_pika can encode (not a str)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.worker.main import _publish_retry


@pytest.mark.asyncio
async def test_publish_retry_sets_encodable_expiration():
    publisher = AsyncMock()

    await _publish_retry(publisher, "task-123", "email_send", 5)

    message = publisher.exchange.publish.await_args.args[0]
    routing_key = publisher.exchange.publish.await_args.kwargs["routing_key"]
    assert routing_key == "tasks.email_send.retry"
    assert isinstance(message.expiration, timedelta)
    assert message.expiration == timedelta(milliseconds=5000)
    # raises ValueError on aio_pika >= 10 if expiration is a str
    props = message.properties
    assert props.expiration == "5000"
