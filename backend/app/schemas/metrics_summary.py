"""Data models for comprehensive operational metrics summary (Step 6.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReliabilitySnapshot(BaseModel):
    tasks_lost: int = Field(0, description="Guaranteed invariant: 0 tasks lost")
    duplicate_executions: int = Field(0, description="Guaranteed invariant: 0 duplicate executions")
    tasks_recovered: int = Field(0, description="Tasks reclaimed from dead or timed-out workers")
    retries: int = Field(0, description="Automated retries processed")
    dlq_tasks: int = Field(0, description="Tasks quarantined in Dead Letter Queue")
    success_rate_percent: float = Field(100.0, description="Percentage of completed tasks that succeeded")


class WindowedRate(BaseModel):
    m5: float = Field(0.0, alias="5m")
    m60: float = Field(0.0, alias="60m")

    model_config = {"populate_by_name": True}


class ThroughputSnapshot(BaseModel):
    submissions_per_min: WindowedRate
    completions_per_min: WindowedRate
    total_submitted: int
    history_points: list[float] = Field(
        default_factory=list,
        description="Recent 12-interval activity points for trend sparkline",
    )
    history_labels: list[str] = Field(
        default_factory=list,
        description="Labels for trend points",
    )


class LastRecoveryEvent(BaseModel):
    worker_id: str | None = None
    reason: str | None = None
    recovered_tasks: int = 0
    occurred_at: datetime | None = None


class WorkersSnapshot(BaseModel):
    active: int = 0
    healthy: int = 0
    busy: int = 0
    idle: int = 0
    recovering: int = 0
    unhealthy: int = 0
    running_tasks: int = 0
    capacity: int = 0
    last_recovery: LastRecoveryEvent | None = None


class PickupSeconds(BaseModel):
    avg: float | None = None


class ExecutionSeconds(BaseModel):
    avg: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None


class LatencySnapshot(BaseModel):
    pickup_seconds: PickupSeconds
    execution_seconds: ExecutionSeconds


class BackpressureSnapshot(BaseModel):
    status: Literal["NORMAL", "THROTTLED", "SATURATED"] = "NORMAL"
    rate_limited_requests: int = 0
    utilization_percent: float = 0.0


class RecoverySnapshot(BaseModel):
    missed_heartbeats: int = 0
    recovery_events: int = 0
    stale_tasks: int = 0


class QueueTypeDetail(BaseModel):
    task_type: str
    main_depth: int = 0
    retry_depth: int = 0
    dlq_depth: int = 0
    total_depth: int = 0
    status: Literal["Healthy", "Attention"] = "Healthy"


class QueuesSnapshot(BaseModel):
    main: int = 0
    retry: int = 0
    dlq: int = 0
    by_type: list[QueueTypeDetail] = Field(default_factory=list)


class ExternalLinks(BaseModel):
    grafana: str
    jaeger: str
    prometheus: str


class MetricsSummaryResponse(BaseModel):
    timestamp: datetime
    reliability: ReliabilitySnapshot
    throughput: ThroughputSnapshot
    workers: WorkersSnapshot
    latency: LatencySnapshot
    backpressure: BackpressureSnapshot
    recovery: RecoverySnapshot
    queues: QueuesSnapshot
    links: ExternalLinks

    model_config = {"populate_by_name": True}
