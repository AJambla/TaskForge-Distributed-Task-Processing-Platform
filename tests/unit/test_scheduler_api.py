"""Unit tests for recurring task schema and validation."""
import pytest
from pydantic import ValidationError

from app.schemas.tasks import TaskCreateRequest, TaskType


def test_valid_recurrence_rule():
    req = TaskCreateRequest(
        task_type=TaskType.EMAIL_SEND,
        payload={"to": "dev@example.com", "subject": "Test", "body": "Hello"},
        recurrence_rule="0 * * * *",
    )
    assert req.recurrence_rule == "0 * * * *"


def test_invalid_recurrence_rule():
    with pytest.raises(ValidationError) as exc:
        TaskCreateRequest(
            task_type=TaskType.EMAIL_SEND,
            payload={"to": "dev@example.com", "subject": "Test", "body": "Hello"},
            recurrence_rule="invalid-cron-rule",
        )
    assert "Invalid cron expression" in str(exc.value)


def test_none_or_blank_recurrence_rule():
    req1 = TaskCreateRequest(
        task_type=TaskType.EMAIL_SEND,
        payload={"to": "dev@example.com", "subject": "Test", "body": "Hello"},
        recurrence_rule=None,
    )
    assert req1.recurrence_rule is None

    req2 = TaskCreateRequest(
        task_type=TaskType.EMAIL_SEND,
        payload={"to": "dev@example.com", "subject": "Test", "body": "Hello"},
        recurrence_rule="   ",
    )
    assert req2.recurrence_rule is None
