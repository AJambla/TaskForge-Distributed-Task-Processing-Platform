"""Regression tests for worker retry routing in on_message.

Guards against the bug where terminal statuses (succeeded/cancelled) were
re-published to the retry queue whenever attempt_count < max_attempts,
causing an endless re-delivery loop.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.worker import main as worker_main


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Override the DB-backed autouse fixture from tests/conftest.py."""
    yield


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
    publisher._exchange = MagicMock()
    publisher._exchange.publish = AsyncMock()

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
    publisher._exchange.publish.assert_not_awaited()


async def test_cancelled_task_is_not_republished(env):
    publisher = env(("cancelled", 2, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    publisher._exchange.publish.assert_not_awaited()


async def test_failed_task_below_max_is_republished_to_retry(env):
    publisher = env(("failed", 1, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher._exchange.publish.assert_awaited_once()
    _, kwargs = publisher._exchange.publish.await_args
    assert kwargs["routing_key"] == "tasks.email_send.retry"
    msg.ack.assert_awaited_once()


async def test_timeout_task_below_max_is_republished_to_retry(env):
    publisher = env(("timeout", 2, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher._exchange.publish.assert_awaited_once()


async def test_failed_task_at_max_goes_to_dead_letter(env):
    publisher = env(("failed", 3, 3, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    publisher._exchange.publish.assert_not_awaited()
    msg.ack.assert_awaited_once()


async def test_not_found_task_is_acked_without_republish(env):
    publisher = env(("not_found", 0, 0, None))
    msg = FakeMessage()

    await worker_main.on_message(msg, publisher)

    msg.ack.assert_awaited_once()
    publisher._exchange.publish.assert_not_awaited()


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

    publisher._exchange.publish.assert_awaited_once()
    args, kwargs = publisher._exchange.publish.await_args
    assert kwargs["routing_key"] == "tasks.email_send.retry"
    assert args[0].expiration == "120000"
    msg.ack.assert_awaited_once()
