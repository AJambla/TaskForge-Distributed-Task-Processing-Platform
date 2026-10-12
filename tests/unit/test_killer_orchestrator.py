import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from killer_demo import (  # noqa: E402
    BenchmarkReport,
    KillerDemoOrchestrator,
    WorkerPoolManager,
)


def test_benchmark_report_zero_task_loss_invariant():
    """Verify zero task loss invariant calculation and throughput metric."""
    report = BenchmarkReport(
        tasks_submitted=1000,
        backpressure_shed_429=50,
        tasks_completed=940,
        tasks_in_dlq=10,
        duration_seconds=10.0,
    )
    # 1000 submitted - 50 shed = 950 admitted. 940 completed + 10 DLQ = 950 accounted.
    assert report.compute_invariants() is True
    assert report.tasks_lost == 0
    assert report.throughput_tps == 94.0

    table_output = report.to_table()
    assert "PASSED: ZERO TASK LOSS" in table_output
    assert "Tasks Submitted (Total Ingested)" in table_output
    assert "**TASKS LOST**" in table_output


def test_benchmark_report_detects_task_loss():
    """Verify report detects and calculates lost tasks if invariant is broken."""
    report = BenchmarkReport(
        tasks_submitted=1000,
        backpressure_shed_429=0,
        tasks_completed=900,
        tasks_in_dlq=0,
        duration_seconds=5.0,
    )
    # 1000 admitted, only 900 terminal -> 100 tasks lost
    assert report.compute_invariants() is False
    assert report.tasks_lost == 100
    assert "FAILED: TASK LOSS DETECTED" in report.to_table()


def test_worker_pool_manager_kill_fraction():
    """Verify worker pool abruptly terminates the requested fraction of workers."""
    mgr = WorkerPoolManager(count=6)
    mock_procs = []
    for i in range(6):
        proc = MagicMock()
        proc.pid = 1000 + i
        proc.poll.return_value = None  # alive
        mock_procs.append(proc)

    mgr.processes = mock_procs
    killed = mgr.kill_fraction(fraction=0.5)

    assert len(killed) == 3
    assert killed == [1000, 1001, 1002]
    for p in mock_procs[:3]:
        p.kill.assert_called_once()
    for p in mock_procs[3:]:
        p.kill.assert_not_called()

    # Verify stop_all cleans up remaining
    mgr.stop_all()
    for p in mock_procs[3:]:
        p.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_killer_orchestrator_simulation_mode():
    """Verify end-to-end killer demo orchestration workflow in simulation mode."""
    orchestrator = KillerDemoOrchestrator(
        base_url="http://mock-taskforge:8000",
        worker_count=10,
        task_count=500,
        simulation_mode=True,
    )
    report = await orchestrator.run()

    assert report.tasks_submitted == 500
    assert report.workers_started == 10
    assert report.workers_killed == 5
    assert report.tasks_lost == 0
    assert report.backpressure_shed_429 > 0
    assert report.tasks_completed > 0
    assert report.tasks_recovered > 0
    assert report.latency_p95_ms > 0
