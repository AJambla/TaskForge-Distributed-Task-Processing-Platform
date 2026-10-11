"""Prometheus instrumentation for Transactional Outbox (FEAT-02)."""
from prometheus_client import Counter, Gauge, Histogram

outbox_messages_relayed_total = Counter(
    "outbox_messages_relayed_total",
    "Total outbox messages successfully relayed to RabbitMQ",
    ["task_type"],
)

outbox_relay_errors_total = Counter(
    "outbox_relay_errors_total",
    "Total outbox message relay publication errors",
    ["task_type"],
)

outbox_retry_total = Counter(
    "outbox_retry_total",
    "Total outbox message retry attempts after publication failure",
    ["task_type"],
)

outbox_pending_count = Gauge(
    "outbox_pending_count",
    "Current count of pending outbox messages in database",
)

outbox_message_age_seconds = Histogram(
    "outbox_message_age_seconds",
    "Time between outbox event creation and successful relay",
    buckets=[0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 60.0, 300.0],
)

outbox_publish_latency_seconds = Histogram(
    "outbox_publish_latency_seconds",
    "Duration of RabbitMQ publish call in relay loop",
    buckets=[0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

outbox_pruned_total = Counter(
    "outbox_pruned_total",
    "Total published outbox records pruned from database by retention cleanup",
)
