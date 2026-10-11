"""Unit tests for dynamic queue provisioning and API custom task handling (FEAT-06 Task 3)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field

from app.schemas.tasks import TaskCreateRequest
from app.worker.consumer import subscribe_queues
from app.worker.handlers import register_handler, list_handlers


class CustomInvoicePayload(BaseModel):
    invoice_number: str = Field(..., min_length=3)
    amount: float = Field(..., gt=0)


@pytest.mark.asyncio
async def test_dynamic_queue_provisioning():
    custom_type = "pdf_generator_queue_test"

    @register_handler(custom_type)
    def dummy_handler(payload: dict):
        return {}

    mock_channel = AsyncMock()
    mock_exchange = AsyncMock()
    mock_publisher = MagicMock()
    mock_publisher.channel = mock_channel
    mock_publisher.exchange = mock_exchange

    mock_queue = AsyncMock()
    mock_channel.declare_queue.return_value = mock_queue
    mock_queue.consume.return_value = "consumer_tag_123"

    mock_callback = AsyncMock()

    consumers = await subscribe_queues(mock_publisher, mock_callback)

    declared_queues = [
        call.args[0] for call in mock_channel.declare_queue.call_args_list
    ]
    # Verify main queue was declared for the custom handler
    assert f"tasks.{custom_type}" in declared_queues
    # Verify discrete bucket queues were declared
    assert f"tasks.{custom_type}.retry.5s" in declared_queues
    assert f"tasks.{custom_type}.dlq" in declared_queues


def test_custom_task_schema_validation_success_and_failure():
    custom_type = "invoice_processor"

    @register_handler(custom_type, schema=CustomInvoicePayload)
    def handle_inv(payload: dict):
        return {}

    # Valid payload should parse without errors
    valid_req = TaskCreateRequest(
        task_type=custom_type,
        payload={"invoice_number": "INV-1001", "amount": 99.50},
    )
    assert valid_req.task_type == custom_type
    assert valid_req.payload["invoice_number"] == "INV-1001"

    # Invalid payload should raise ValueError
    with pytest.raises(ValueError, match="Invalid payload for invoice_processor"):
        TaskCreateRequest(
            task_type=custom_type,
            payload={"invoice_number": "NO", "amount": -10},
        )


def test_list_handlers_contains_registered_metadata():
    handlers = list_handlers()
    assert "email_send" in handlers
    assert "webhook_delivery" in handlers
    assert handlers["email_send"]["timeout_seconds"] == 30


def test_unknown_task_type_rejected():
    with pytest.raises(ValueError, match="Unknown task_type: 'non_existent_random_type'"):
        TaskCreateRequest(
            task_type="non_existent_random_type",
            payload={"some": "data"},
        )
