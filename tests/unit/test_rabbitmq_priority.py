"""Unit tests for RabbitMQ queue priority (IMP-03)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.rabbitmq import RabbitMQPublisher, publish_task


@pytest.mark.asyncio
async def test_publish_passes_priority():
    """Verify RabbitMQPublisher.publish normalizes priority (0-10) and passes to Message."""
    publisher = RabbitMQPublisher()
    publisher._connection = AsyncMock()
    publisher._connection.is_closed = False
    publisher._channel = AsyncMock()
    publisher._channel.is_closed = False
    mock_exchange = AsyncMock()
    publisher._exchange = mock_exchange

    # Test with priority 5
    await publisher.publish("test-id-1", "email_send", priority=5)

    assert mock_exchange.publish.awaited
    published_msg, kwargs = mock_exchange.publish.call_args
    message = published_msg[0]
    assert message.priority == 5
    assert kwargs["routing_key"] == "email_send"

    # Test normalization bounds: priority > 10 clamped to 10, < 0 clamped to 0
    await publisher.publish("test-id-2", "email_send", priority=50)
    assert mock_exchange.publish.call_args[0][0].priority == 10

    await publisher.publish("test-id-3", "email_send", priority=-5)
    assert mock_exchange.publish.call_args[0][0].priority == 0


@pytest.mark.asyncio
async def test_subscribe_queues_declares_x_max_priority():
    """Verify subscribe_queues declares queues with x-max-priority = 10."""
    from app.worker.main import subscribe_queues

    mock_channel = AsyncMock()
    mock_exchange = AsyncMock()
    mock_publisher = MagicMock()
    mock_publisher.channel = mock_channel
    mock_publisher.exchange = mock_exchange

    # Run subscribe_queues
    await subscribe_queues(mock_publisher)

    # Check declare_queue arguments for main queues
    declared_queues = [call[0][0] for call in mock_channel.declare_queue.call_args_list]
    assert "tasks.email_send" in declared_queues

    # Check that main queues have x-max-priority: 10 in arguments
    for call in mock_channel.declare_queue.call_args_list:
        queue_name = call[0][0]
        args = call[1].get("arguments", {})
        if queue_name in ("tasks.email_send", "tasks.image_resize", "tasks.webhook_delivery"):
            assert args.get("x-max-priority") == 10
