"""Unit tests for enhanced TaskOutbox model (FEAT-02)."""
import uuid
from datetime import datetime, timezone

from app.models.task_outbox import TaskOutbox


def test_task_outbox_model_fields():
    task_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    outbox = TaskOutbox(
        task_id=task_id,
        task_type="email_send",
        payload={"to": "dev@test.com"},
        priority=3,
        event_type="task_created",
        status="pending",
        retry_count=0,
        next_attempt_at=now,
    )
    assert outbox.task_id == task_id
    assert outbox.task_type == "email_send"
    assert outbox.event_type == "task_created"
    assert outbox.status == "pending"
    assert outbox.retry_count == 0
    assert outbox.next_attempt_at == now
    assert outbox.last_attempt_at is None
    assert outbox.last_error is None
