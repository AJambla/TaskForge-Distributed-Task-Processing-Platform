"""Deterministic failure diagnostics data model and synthesis (Step 5.1)."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class FailureClassification(str, Enum):
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    WORKER_CRASH = "WORKER_CRASH"
    FATAL_ERROR = "FATAL_ERROR"


class FailureDiagnostics(BaseModel):
    failed_attempt: int = Field(
        ..., description="The attempt number that encountered the failure"
    )
    classification: FailureClassification = Field(
        ..., description="Deterministic category of the failure"
    )
    cause_description: str = Field(
        ..., description="Human-readable diagnosis of the root cause"
    )
    recovery_action: str = Field(
        ..., description="Action taken or required to recover"
    )
    will_retry: bool = Field(
        ..., description="Whether TaskForge will automatically retry the task"
    )
    next_retry_at: datetime | None = Field(
        None, description="Scheduled or projected time of the next attempt"
    )
    recovery_worker_id: uuid.UUID | None = Field(
        None, description="Worker that reclaimed/recovered the task, if applicable"
    )
    recovery_duration_seconds: float | None = Field(
        None, description="Seconds spent recovering/executing the failed attempt"
    )

    model_config = {"from_attributes": True}


def classify_failure(
    outcome: str | None,
    error_message: str | None,
    error_detail: dict[str, Any] | None = None,
) -> FailureClassification:
    """Deterministically categorize a task failure from its error artifacts."""
    msg = (error_message or "").lower()
    err_type = ""
    if isinstance(error_detail, dict):
        err_type = str(error_detail.get("error_type", "")).lower()

    # 1. Timeout classification
    if outcome == "timeout" or "timed out" in msg or "timeout" in err_type:
        return FailureClassification.TIMEOUT

    # 2. Worker crash / abandonment classification
    if (
        "worker crashed" in msg
        or "heartbeat timeout" in msg
        or "abandoned" in msg
        or "worker_crash" in err_type
    ):
        return FailureClassification.WORKER_CRASH

    # 3. Rate limiting / 429
    if "429" in msg or "rate limit" in msg or "rate_limit" in err_type:
        return FailureClassification.RATE_LIMITED

    # 4. Transient network/infrastructure errors
    transient_indicators = [
        "connection refused",
        "connection reset",
        "broken pipe",
        "temporary failure",
        "502",
        "503",
        "504",
        "bad gateway",
        "service unavailable",
        "network error",
        "lock_timeout",
    ]
    if any(indicator in msg for indicator in transient_indicators) or any(
        indicator in err_type for indicator in transient_indicators
    ):
        return FailureClassification.TRANSIENT_ERROR

    # 5. Default: Fatal error (unhandled business exception, validation, client error)
    return FailureClassification.FATAL_ERROR


def synthesize_diagnostics(
    task: Any,
    attempts: list[Any] | None = None,
) -> FailureDiagnostics | None:
    """Deterministically build FailureDiagnostics by analyzing task and attempt history.

    Returns None if the task is succeeded or has never experienced a failure.
    """
    # If task succeeded with no failed attempts, diagnostics are not applicable
    status = getattr(task, "status", None)
    task_attempts = attempts if attempts is not None else getattr(task, "attempts", [])

    failed_attempts = [
        a for a in task_attempts if getattr(a, "outcome", None) in ("failure", "timeout") or getattr(a, "error_message", None)
    ]

    # If no failed attempt records and task is not in an error state, return None
    if not failed_attempts and status not in ("failed", "retrying", "dead_letter"):
        return None

    # Pick the most recent failed attempt (or last attempt)
    recent_attempt = failed_attempts[-1] if failed_attempts else (task_attempts[-1] if task_attempts else None)

    attempt_number = getattr(recent_attempt, "attempt_number", None) or getattr(task, "attempt_count", 1)
    outcome = getattr(recent_attempt, "outcome", None)
    error_message = getattr(recent_attempt, "error_message", None)
    error_detail = getattr(recent_attempt, "error_detail", None)

    classification = classify_failure(outcome, error_message, error_detail)

    max_attempts = getattr(task, "max_attempts", 5)
    attempt_count = getattr(task, "attempt_count", attempt_number)

    will_retry = (
        status == "retrying"
        or (status not in ("succeeded", "cancelled", "dead_letter", "failed") and attempt_count < max_attempts)
    )
    if status in ("dead_letter", "failed", "cancelled"):
        will_retry = False

    # Cause description
    cause_desc = error_message or f"Attempt {attempt_number} failed with outcome '{outcome or 'unknown'}'"
    if classification == FailureClassification.TIMEOUT:
        cause_desc = f"Task execution exceeded time limit: {error_message or 'timed out'}"
    elif classification == FailureClassification.WORKER_CRASH:
        cause_desc = f"Assigned worker became unresponsive: {error_message or 'worker missed heartbeats'}"
    elif classification == FailureClassification.RATE_LIMITED:
        cause_desc = f"Execution throttled by external service: {error_message or 'rate limit reached'}"
    elif classification == FailureClassification.TRANSIENT_ERROR:
        cause_desc = f"Transient infrastructure issue: {error_message or 'network or service disruption'}"
    elif classification == FailureClassification.FATAL_ERROR:
        cause_desc = f"Non-recoverable error encountered: {error_message or 'unhandled exception'}"

    # Recovery action
    if will_retry:
        if classification == FailureClassification.RATE_LIMITED:
            recovery_action = "Backing off with exponential jitter to allow downstream rate quota replenishment."
        elif classification == FailureClassification.WORKER_CRASH:
            recovery_action = "Task reclaimed from crashed worker and re-queued via transactional outbox."
        elif classification == FailureClassification.TIMEOUT:
            recovery_action = "Scheduled for automated retry with refreshed execution deadline."
        else:
            recovery_action = "Scheduled for automated retry with exponential backoff."
    else:
        if status == "dead_letter" or attempt_count >= max_attempts:
            recovery_action = f"Max retry attempts ({max_attempts}) exhausted. Moved to Dead Letter Queue for inspection."
        elif status == "cancelled":
            recovery_action = "Execution halted by cooperative user cancellation."
        else:
            recovery_action = "Task transitioned to terminal failed state; manual replay or inspection required."

    # Timing metrics
    duration: float | None = None
    if recent_attempt and getattr(recent_attempt, "started_at", None) and getattr(recent_attempt, "finished_at", None):
        duration = round(
            max(0.0, (recent_attempt.finished_at - recent_attempt.started_at).total_seconds()), 3
        )

    # Next retry at
    next_retry: datetime | None = None
    run_at = getattr(task, "run_at", None)
    if run_at and run_at > datetime.now(timezone.utc):
        next_retry = run_at

    recovery_worker_id = getattr(recent_attempt, "worker_id", None)

    return FailureDiagnostics(
        failed_attempt=attempt_number,
        classification=classification,
        cause_description=cause_desc,
        recovery_action=recovery_action,
        will_retry=will_retry,
        next_retry_at=next_retry,
        recovery_worker_id=recovery_worker_id,
        recovery_duration_seconds=duration,
    )
