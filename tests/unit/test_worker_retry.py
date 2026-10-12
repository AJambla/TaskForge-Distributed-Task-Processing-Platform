"""Regression tests for worker retry routing in on_message.

Guards against the bug where terminal statuses (succeeded/cancelled) were
re-published to the retry queue whenever attempt_count < max_attempts,
causing an endless re-delivery loop.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.worker import main as worker_main


class FakeMessage:
    def __init__(self, task_id: str = "task-1", task_type: str = "email_send"):
        self.body = task_id.encode("utf-8")
        self.headers = {"x-task-type": task_type}
        self.ack = AsyncMock()
        self.reject = AsyncMock()


class FakeSession:
    def __init__(self, scalar_result=None):
        self._scalar_result = scalar_result
        self.execute = AsyncMock(
            return_value=self._make_result(scalar_result)
        )
        self.commit = AsyncMock()

    @staticmethod
    def _make_result(scalar_result):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=scalar_result)
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def env(monkeypatch):
    publisher = MagicMock()
    publisher.exchange = MagicMock()
    publisher.exchange.publish = AsyncMock()

    def make(consume_return, scalar_result=None):
        session = FakeSession(scalar_result=scalar_result)
        monkeypatch.setattr(worker_main, "AsyncSessionLocal", lambda: session)
        mock = AsyncMock(return_value=consume_return)
        monkeypatch.setattr(worker_main, "consume_task", mock)
        return publisher

    return make


async def test_succeeded_task_is_not_republished(env):
    publisher = env(("succeeded", 1, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    publisher.exchange.publish.assert_not_awaited()


async def test_cancelled_task_is_not_republished(env):
    publisher = env(("cancelled", 2, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    publisher.exchange.publish.assert_not_awaited()


async def test_failed_task_below_max_is_republished_to_retry(env):
    publisher = env(("failed", 1, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher.exchange.publish.assert_awaited_once()
    _, kwargs = publisher.exchange.publish.await_args
    assert kwargs["routing_key"] == "tasks.email_send.retry.5s"
    msg.ack.assert_awaited_once()


async def test_timeout_task_below_max_is_republished_to_retry(env):
    publisher = env(("timeout", 2, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher.exchange.publish.assert_awaited_once()


async def test_failed_task_at_max_goes_to_dead_letter(env):
    dead_row = MagicMock()
    dead_row.status = "failed"
    publisher = env(("failed", 3, 3, None), scalar_result=dead_row)
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher.exchange.publish.assert_not_awaited()
    assert dead_row.status == "dead_letter"
    # rejected without requeue → main-queue DLX deposits it in tasks.email_send.dlq
    msg.reject.assert_awaited_once_with(requeue=False)
    msg.ack.assert_not_awaited()


async def test_dead_letter_row_already_succeeded_acks_without_dropping_to_dlq(env):
    ok_row = MagicMock()
    ok_row.status = "succeeded"
    publisher = env(("failed", 3, 3, None), scalar_result=ok_row)
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    msg.reject.assert_not_awaited()


async def test_not_found_task_is_acked_without_republish(env):
    publisher = env(("not_found", 0, 0, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    publisher.exchange.publish.assert_not_awaited()


async def test_infra_error_requeues_instead_of_ackning(env, monkeypatch):
    publisher = env(("ignored", 0, 0, None))
    monkeypatch.setattr(
        worker_main, "consume_task", AsyncMock(side_effect=ConnectionError("db down"))
    )
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_not_awaited()
    msg.reject.assert_awaited_once_with(requeue=True)


async def test_future_run_at_task_is_deferred_via_retry_ttl(env):
    publisher = env(("scheduled", 0, 3, 120))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher.exchange.publish.assert_awaited_once()
    args, kwargs = publisher.exchange.publish.await_args
    assert kwargs["routing_key"] == "tasks.email_send.retry.60s"
    msg.ack.assert_awaited_once()


async def test_create_attempt_uses_current_attempt_count():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    task = MagicMock()
    task.id = "task-uuid-1"
    task.attempt_count = 1

    attempt = await worker_main.create_attempt(db, task, worker_id="worker-1")
    assert attempt.attempt_number == 1
    db.add.assert_called_once_with(attempt)
    db.flush.assert_awaited_once()


async def test_mark_failure_sets_retrying_status_below_max():
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()

    task = MagicMock()
    task.attempt_count = 1
    task.max_attempts = 3
    task.status = "running"

    attempt = MagicMock()

    await worker_main._mark_failure(db, task, attempt, "failure", exc=ValueError("boom"))
    assert task.status == "retrying"
    assert attempt.outcome == "failure"
    db.commit.assert_awaited_once()


async def test_mark_failure_sets_failed_status_at_max():
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()

    task = MagicMock()
    task.attempt_count = 3
    task.max_attempts = 3
    task.status = "running"

    attempt = MagicMock()

    await worker_main._mark_failure(db, task, attempt, "failure", exc=ValueError("boom"))
    assert task.status == "failed"
    db.commit.assert_awaited_once()

