"""Unit tests for discrete bucketed retry queues (IMP-09)."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.worker.consumer import subscribe_queues
from app.worker.retry import (
    RETRY_BUCKETS,
    calculate_retry_delay as _calculate_retry_delay,
    publish_retry as _publish_retry,
)


def test_calculate_retry_delay_snaps_to_buckets():
    # Attempt 1: base delay 5 -> bucket 5
    assert _calculate_retry_delay(1) == 5
    # Attempt 2: base delay 5 * 2 = 10 -> bucket 10
    assert _calculate_retry_delay(2) == 10
    # Attempt 3: base delay 5 * 4 = 20 -> bucket 20
    assert _calculate_retry_delay(3) == 20
    # Attempt 4: base delay 5 * 8 = 40 -> bucket 40
    assert _calculate_retry_delay(4) == 40
    # Attempt 5: base delay 5 * 16 = 80 -> clamped to 60 -> bucket 60
    assert _calculate_retry_delay(5) == 60


@pytest.mark.asyncio
async def test_publish_retry_routes_to_bucket_routing_key():
    mock_publisher = MagicMock()
    mock_exchange = AsyncMock()
    mock_publisher.exchange = mock_exchange

    await _publish_retry(mock_publisher, "task-xyz", "email_send", delay_seconds=10)

    mock_exchange.publish.assert_called_once()
    call_args = mock_exchange.publish.call_args
    message = call_args[0][0]
    routing_key = call_args[1]["routing_key"]

    assert routing_key == "tasks.email_send.retry.10s"
    assert message.headers["x-task-id"] == "task-xyz"
    assert message.headers["x-task-type"] == "email_send"
    assert message.expiration is None  # Queue-level TTL used, not message-level


@pytest.mark.asyncio
async def test_subscribe_queues_declares_bucketed_queues():
    mock_publisher = MagicMock()
    mock_channel = AsyncMock()
    mock_exchange = MagicMock()
    mock_publisher.channel = mock_channel
    mock_publisher.exchange = mock_exchange

    declared_queues = {}

    async def mock_declare_queue(name, durable=True, arguments=None):
        mock_q = AsyncMock()
        mock_q.name = name
        mock_q.consume = AsyncMock(return_value="ctag-1")
        declared_queues[name] = arguments
        return mock_q

    mock_channel.declare_queue.side_effect = mock_declare_queue

    await subscribe_queues(mock_publisher)

    for task_type in ["email_send", "webhook_delivery"]:
        for bucket in RETRY_BUCKETS:
            q_name = f"tasks.{task_type}.retry.{bucket}s"
            assert q_name in declared_queues
            args = declared_queues[q_name]
            assert args["x-dead-letter-exchange"] == "task_main_exchange"
            assert args["x-dead-letter-routing-key"] == task_type
            assert args["x-message-ttl"] == bucket * 1000
