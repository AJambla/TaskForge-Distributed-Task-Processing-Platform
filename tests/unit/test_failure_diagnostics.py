"""Unit tests for Step 5.1 & 5.2: Deterministic Failure Diagnostics & Task Timelines."""
from datetime import datetime, timedelta, timezone
import uuid

from app.schemas.diagnostics import (
    FailureClassification,
    FailureDiagnostics,
    classify_failure,
    synthesize_diagnostics,
)
from app.schemas.tasks import TaskResponse


class DummyAttempt:
    """Mock TaskAttempt for deterministic diagnostics testing."""

    def __init__(
        self,
        attempt_number: int = 1,
        outcome: str = "failure",
        error_message: str | None = None,
        error_detail: dict | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        worker_id: uuid.UUID | None = None,
        trace_id: str | None = None,
    ):
        self.id = uuid.uuid4()
        self.task_id = uuid.uuid4()
        self.attempt_number = attempt_number
        self.outcome = outcome
        self.error_message = error_message
        self.error_detail = error_detail or {}
        self.started_at = started_at or datetime.now(timezone.utc)
        self.finished_at = finished_at or (self.started_at + timedelta(seconds=2))
        self.worker_id = worker_id or uuid.uuid4()
        self.trace_id = trace_id or "trace-123"


class DummyTask:
    """Mock Task for deterministic diagnostics testing."""

    def __init__(
        self,
        status: str = "failed",
        attempt_count: int = 1,
        max_attempts: int = 5,
        run_at: datetime | None = None,
        attempts: list[DummyAttempt] | None = None,
    ):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.task_type = "email_send"
        self.status = status
        self.priority = 5
        self.idempotency_key = "idemp-key-1"
        self.max_attempts = max_attempts
        self.attempt_count = attempt_count
        self.run_at = run_at
        self.recurrence_rule = None
        self.created_at = datetime.now(timezone.utc)
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = datetime.now(timezone.utc)
        self.result = None
        self.trace_id = "trace-456"
        self.attempts = attempts or []


def test_classify_failure_timeout():
    """Verify outcome='timeout' or timeout message categorizes as TIMEOUT."""
    assert classify_failure("timeout", "Operation timed out") == FailureClassification.TIMEOUT
    assert classify_failure("failure", "Task execution timed out after 30s") == FailureClassification.TIMEOUT
    assert classify_failure("failure", None, {"error_type": "TimeoutError"}) == FailureClassification.TIMEOUT


def test_classify_failure_worker_crash():
    """Verify worker disconnects or heartbeat loss categorizes as WORKER_CRASH."""
    assert classify_failure("failure", "Worker crashed unexpectedly") == FailureClassification.WORKER_CRASH
    assert (
        classify_failure("failure", "Task execution failed due to worker heartbeat timeout")
        == FailureClassification.WORKER_CRASH
    )
    assert classify_failure("failure", "Task abandoned by dead worker") == FailureClassification.WORKER_CRASH


def test_classify_failure_rate_limited():
    """Verify downstream HTTP 429 or rate limit messages categorize as RATE_LIMITED."""
    assert classify_failure("failure", "HTTP 429 Too Many Requests") == FailureClassification.RATE_LIMITED
    assert classify_failure("failure", "Rate limit exceeded for endpoint") == FailureClassification.RATE_LIMITED
    assert classify_failure("failure", None, {"error_type": "RateLimitExceeded"}) == FailureClassification.RATE_LIMITED


def test_classify_failure_transient_error():
    """Verify intermittent network/5xx server errors categorize as TRANSIENT_ERROR."""
    assert classify_failure("failure", "Connection refused by peer") == FailureClassification.TRANSIENT_ERROR
    assert classify_failure("failure", "503 Service Unavailable") == FailureClassification.TRANSIENT_ERROR
    assert classify_failure("failure", "Broken pipe during socket write") == FailureClassification.TRANSIENT_ERROR


def test_classify_failure_fatal_error():
    """Verify business logic errors categorize as FATAL_ERROR."""
    assert classify_failure("failure", "ValueError: invalid recipient format") == FailureClassification.FATAL_ERROR
    assert classify_failure("failure", "KeyError: 'auth_token'") == FailureClassification.FATAL_ERROR


def test_synthesize_diagnostics_succeeded_task_is_none():
    """Succeeded tasks with no failures return None diagnostics."""
    success_attempt = DummyAttempt(outcome="success", error_message=None)
    task = DummyTask(status="succeeded", attempts=[success_attempt])
    assert synthesize_diagnostics(task, task.attempts) is None


def test_synthesize_diagnostics_retrying_timeout():
    """Verify retrying timeout generates actionable diagnostics with will_retry=True."""
    start = datetime.now(timezone.utc)
    finish = start + timedelta(seconds=30.05)
    worker_id = uuid.uuid4()
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=10)

    timeout_attempt = DummyAttempt(
        attempt_number=2,
        outcome="timeout",
        error_message="Task execution timed out after 30s",
        started_at=start,
        finished_at=finish,
        worker_id=worker_id,
    )
    task = DummyTask(
        status="retrying",
        attempt_count=2,
        max_attempts=5,
        run_at=next_retry,
        attempts=[timeout_attempt],
    )

    diag = synthesize_diagnostics(task, task.attempts)
    assert isinstance(diag, FailureDiagnostics)
    assert diag.failed_attempt == 2
    assert diag.classification == FailureClassification.TIMEOUT
    assert diag.will_retry is True
    assert diag.recovery_worker_id == worker_id
    assert diag.recovery_duration_seconds == 30.05
    assert diag.next_retry_at == next_retry
    assert "exceeded time limit" in diag.cause_description
    assert "automated retry" in diag.recovery_action


def test_synthesize_diagnostics_dead_letter_worker_crash():
    """Verify max-attempts dead letter worker crash generates DLQ diagnostic with will_retry=False."""
    worker_id = uuid.uuid4()
    crash_attempt = DummyAttempt(
        attempt_number=5,
        outcome="failure",
        error_message="Task execution failed due to worker heartbeat timeout (worker crashed)",
        worker_id=worker_id,
    )
    task = DummyTask(
        status="dead_letter",
        attempt_count=5,
        max_attempts=5,
        attempts=[crash_attempt],
    )

    diag = synthesize_diagnostics(task, task.attempts)
    assert isinstance(diag, FailureDiagnostics)
    assert diag.failed_attempt == 5
    assert diag.classification == FailureClassification.WORKER_CRASH
    assert diag.will_retry is False
    assert "unresponsive" in diag.cause_description
    assert "Dead Letter Queue" in diag.recovery_action


def test_task_response_serializes_timeline_and_diagnostics():
    """Verify TaskResponse includes attempt timeline and synthesized diagnostics."""
    worker_id = uuid.uuid4()
    attempt1 = DummyAttempt(
        attempt_number=1,
        outcome="failure",
        error_message="HTTP 429 Too Many Requests",
        worker_id=worker_id,
    )
    task = DummyTask(
        status="retrying",
        attempt_count=1,
        max_attempts=3,
        attempts=[attempt1],
    )

    resp = TaskResponse.from_task(task)
    assert len(resp.attempts) == 1
    assert resp.attempts[0].attempt_number == 1
    assert resp.attempts[0].worker_id == worker_id
    assert resp.diagnostics is not None
    assert resp.diagnostics.classification == FailureClassification.RATE_LIMITED
    assert resp.diagnostics.will_retry is True
    assert "throttled" in resp.diagnostics.cause_description

    dumped = resp.model_dump()
    assert "attempts" in dumped
    assert "diagnostics" in dumped
    assert dumped["diagnostics"]["classification"] == "RATE_LIMITED"
