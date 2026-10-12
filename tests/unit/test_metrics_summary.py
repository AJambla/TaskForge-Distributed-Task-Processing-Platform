"""Unit tests for GET /api/v1/metrics/summary operational snapshot endpoint (Step 6.3)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration


@pytest.fixture
def mock_db_session():
    """Mock database session returning sample data for metrics aggregation."""
    db = AsyncMock()

    # Status counts mock
    status_result = MagicMock()
    status_result.all.return_value = [
        ("succeeded", 95),
        ("failed", 3),
        ("dead_letter", 2),
        ("running", 4),
        ("queued", 10),
    ]

    # Scalar counts mock
    count_res_0 = MagicMock()
    count_res_0.scalar_one.return_value = 0

    count_res_recovered = MagicMock()
    count_res_recovered.scalar_one.return_value = 5

    count_res_retries = MagicMock()
    count_res_retries.scalar_one.return_value = 8

    # Latencies
    avg_pickup = MagicMock()
    avg_pickup.scalar_one.return_value = 0.045

    avg_exec = MagicMock()
    avg_exec.scalar_one.return_value = 0.850

    # Workers
    worker1 = WorkerRegistration(
        id=uuid.uuid4(),
        hostname="worker-test-1",
        status="online",
        concurrency_limit=8,
        current_task_count=3,
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    worker2 = WorkerRegistration(
        id=uuid.uuid4(),
        hostname="worker-test-2",
        status="online",
        concurrency_limit=8,
        current_task_count=0,
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    workers_res = MagicMock()
    workers_res.scalars.return_value.all.return_value = [worker1, worker2]

    # Last recovery attempt
    attempt = TaskAttempt(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        attempt_number=2,
        worker_id=worker1.id,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        outcome="failure",
        error_message="Worker heartbeat timeout; reclaimed",
    )
    last_rec_res = MagicMock()
    last_rec_res.scalar_one_or_none.return_value = attempt

    stale_res = MagicMock()
    stale_res.scalar_one.return_value = 0

    # Dispatch responses according to query
    def execute_side_effect(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from tasks" in stmt_str and "group by" in stmt_str:
            return status_result
        if "from task_attempts" in stmt_str and "where" in stmt_str and "attempt_number >" in stmt_str:
            return count_res_retries
        if "from task_attempts" in stmt_str and "order by" in stmt_str:
            return last_rec_res
        if "from task_attempts" in stmt_str:
            return count_res_recovered
        if "tasks.started_at" in stmt_str and "tasks.created_at" in stmt_str:
            return avg_pickup
        if "tasks.completed_at" in stmt_str and "tasks.started_at" in stmt_str:
            return avg_exec
        if "from worker_registrations" in stmt_str:
            return workers_res
        if "status = 'running'" in stmt_str:
            return stale_res
        return count_res_0

    db.execute.side_effect = execute_side_effect
    return db


@pytest.mark.asyncio
async def test_get_metrics_summary_structure(mock_db_session):
    """Verify /api/v1/metrics/summary returns typed dashboard snapshot with all required sections."""
    from app.models.user import User
    from app.routers.metrics import get_metrics_summary

    dummy_user = User(id=uuid.uuid4(), email="user@example.com", role="user")

    with patch("app.routers.metrics.get_queue_depths", return_value={"taskforge.email_send.main": 12, "taskforge.email_send.retry": 2, "taskforge.email_send.dlq": 1}):
        with patch("app.routers.metrics._query_prometheus_instant", return_value=None):
            resp = await get_metrics_summary(current_user=dummy_user, db=mock_db_session)

    data = resp.model_dump(by_alias=True)

    # 1. Reliability invariants
    assert "reliability" in data
    assert data["reliability"]["tasks_lost"] == 0
    assert data["reliability"]["duplicate_executions"] == 0
    assert data["reliability"]["tasks_recovered"] == 5
    assert data["reliability"]["retries"] == 8
    assert data["reliability"]["dlq_tasks"] == 2
    assert data["reliability"]["success_rate_percent"] == 95.0

    # 2. Throughput
    assert "throughput" in data
    assert "5m" in data["throughput"]["submissions_per_min"]
    assert "60m" in data["throughput"]["submissions_per_min"]
    assert "5m" in data["throughput"]["completions_per_min"]
    assert "60m" in data["throughput"]["completions_per_min"]
    assert data["throughput"]["total_submitted"] == 114

    # 3. Workers
    assert "workers" in data
    assert data["workers"]["active"] == 2
    assert data["workers"]["healthy"] == 2
    assert data["workers"]["busy"] == 1
    assert data["workers"]["idle"] == 1
    assert data["workers"]["capacity"] == 16
    assert data["workers"]["running_tasks"] == 3
    assert data["workers"]["last_recovery"] is not None
    assert "worker-" in data["workers"]["last_recovery"]["worker_id"]

    # 4. Latency
    assert "latency" in data
    assert data["latency"]["pickup_seconds"]["avg"] == 0.045
    assert data["latency"]["execution_seconds"]["avg"] == 0.85
    assert data["latency"]["execution_seconds"]["p50"] is not None
    assert data["latency"]["execution_seconds"]["p95"] is not None
    assert data["latency"]["execution_seconds"]["p99"] is not None

    # 5. Backpressure
    assert "backpressure" in data
    assert data["backpressure"]["status"] in ("NORMAL", "THROTTLED", "SATURATED")
    assert "utilization_percent" in data["backpressure"]

    # 6. Recovery
    assert "recovery" in data
    assert "missed_heartbeats" in data["recovery"]
    assert "recovery_events" in data["recovery"]

    # 7. Queues
    assert "queues" in data
    assert data["queues"]["main"] == 12
    assert data["queues"]["retry"] == 2
    assert data["queues"]["dlq"] == 1
    assert len(data["queues"]["by_type"]) == 1
    assert data["queues"]["by_type"][0]["task_type"] == "email_send"

    # 8. Links
    assert "links" in data
    assert "grafana" in data["links"]
    assert "jaeger" in data["links"]
    assert "prometheus" in data["links"]
