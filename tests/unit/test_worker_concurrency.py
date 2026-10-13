"""Unit tests for Step 4.2: Worker Concurrency Limits & Capacity Reporting."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest

from app.models.worker_registration import WorkerRegistration
from app.schemas.workers import WorkerDetail, WorkerListItem
from app.worker.consumer import subscribe_queues
from app.worker.lifecycle import set_worker_offline, update_heartbeat
from app.worker.metrics import (
    REGISTRY,
    worker_active_tasks,
    worker_utilization_ratio,
)



@pytest.mark.asyncio
async def test_subscribe_queues_sets_prefetch_qos_and_semaphore():
    """Verify subscribe_queues sets channel QoS to worker_concurrency * 2."""
    channel = AsyncMock()
    exchange = AsyncMock()
    publisher = MagicMock()
    publisher.channel = channel
    publisher.exchange = exchange

    queue = AsyncMock()
    channel.declare_queue.return_value = queue
    queue.consume.return_value = "ctag-1"

    concurrency = 4
    await subscribe_queues(
        publisher=publisher,
        task_types=["test_task"],
        concurrency_limit=concurrency,
    )

    # Prefetch QoS must be 2 * concurrency
    channel.set_qos.assert_awaited_once_with(prefetch_count=8)


@pytest.mark.asyncio
async def test_consumer_bounded_semaphore_enforces_concurrency():
    """Verify that consumer handler restricts simultaneous executions to concurrency_limit."""
    channel = AsyncMock()
    exchange = AsyncMock()
    publisher = MagicMock()
    publisher.channel = channel
    publisher.exchange = exchange

    consumed_handlers = []

    async def fake_consume(callback):
        consumed_handlers.append(callback)
        return "ctag-1"

    queue = AsyncMock()
    queue.consume.side_effect = fake_consume
    channel.declare_queue.return_value = queue

    concurrency_limit = 2
    max_simultaneous = 0
    current_simultaneous = 0

    async def mock_callback(msg, pub, worker_id=None):
        nonlocal max_simultaneous, current_simultaneous
        current_simultaneous += 1
        if current_simultaneous > max_simultaneous:
            max_simultaneous = current_simultaneous
        await asyncio.sleep(0.02)
        current_simultaneous -= 1

    await subscribe_queues(
        publisher=publisher,
        on_message_callback=mock_callback,
        task_types=["test_type"],
        concurrency_limit=concurrency_limit,
    )

    assert len(consumed_handlers) == 1
    handler = consumed_handlers[0]

    # Dispatch 6 concurrent messages
    mock_msgs = [AsyncMock() for _ in range(6)]
    await asyncio.gather(*(handler(m) for m in mock_msgs))

    # Concurrency must not have exceeded 2
    assert max_simultaneous == 2


@pytest.mark.asyncio
async def test_update_heartbeat_persists_stats_and_updates_metrics():
    """Verify update_heartbeat updates DB, Redis snapshot, and Prometheus gauges."""
    db = AsyncMock()
    worker_id = uuid.uuid4()
    worker = WorkerRegistration(
        id=worker_id,
        hostname="worker-test-1",
        status="online",
        concurrency_limit=4,
        current_task_count=0,
    )

    fake_redis = AsyncMock()
    with patch("app.core.redis.get_redis", return_value=fake_redis):
        result = await update_heartbeat(
            db=db,
            worker=worker,
            active_count=3,
            concurrency_limit=4,
        )

        assert result["active_task_count"] == 3
        assert result["concurrency_limit"] == 4
        assert result["utilization_rate"] == 0.75

        # Verify DB executed and committed
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

        # Verify Prometheus gauge values
        assert REGISTRY.get_sample_value("worker_active_tasks") == 3.0
        assert REGISTRY.get_sample_value("worker_concurrency_limit") == 4.0
        assert REGISTRY.get_sample_value("worker_utilization_ratio") == 0.75

        # Verify Redis snapshot cached
        fake_redis.set.assert_awaited_once()
        set_call_args = fake_redis.set.call_args
        assert f"worker:heartbeat:{worker_id}" in set_call_args[0]
        assert set_call_args[1].get("ex") == 30


@pytest.mark.asyncio
async def test_set_worker_offline_resets_gauges():
    """Verify set_worker_offline resets utilization gauges to 0."""
    db = AsyncMock()
    worker_id = uuid.uuid4()

    worker_active_tasks.set(3)
    worker_utilization_ratio.set(0.75)

    await set_worker_offline(db, worker_id)

    assert REGISTRY.get_sample_value("worker_active_tasks") == 0.0
    assert REGISTRY.get_sample_value("worker_utilization_ratio") == 0.0


def test_worker_schemas_computed_utilization_rate():
    """Verify WorkerListItem and WorkerDetail schemas compute utilization_rate."""
    w_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    item = WorkerListItem(
        id=w_id,
        hostname="worker-node-1",
        status="online",
        concurrency_limit=8,
        current_task_count=6,
        last_heartbeat_at=now,
        tasks_processed=100,
        tasks_failed=2,
        registered_at=now,
    )
    assert item.utilization_rate == 0.75
    dumped = item.model_dump()
    assert dumped["utilization_rate"] == 0.75

    detail = WorkerDetail(
        id=w_id,
        hostname="worker-node-1",
        status="online",
        concurrency_limit=10,
        current_task_count=2,
        last_heartbeat_at=now,
        tasks_processed=50,
        tasks_failed=0,
        registered_at=now,
        recent_attempts=[],
    )
    assert detail.utilization_rate == 0.2
    assert detail.model_dump()["utilization_rate"] == 0.2


@pytest.mark.asyncio
async def test_register_worker_isolates_pid_and_prunes_offline():
    """Verify register_worker includes PID in hostname and executes offline update and pruning."""
    import os
    from app.worker.lifecycle import register_worker

    db = AsyncMock()
    async def fake_refresh(w):
        pass
    db.refresh = fake_refresh

    worker = await register_worker(db)
    assert f":{os.getpid()}" in worker.hostname
    assert worker.status == "online"
    assert db.execute.await_count == 2
    assert db.commit.await_count == 1

