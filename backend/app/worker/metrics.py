"""Worker Prometheus metrics — counters and histograms for task processing.

Exposes a /metrics HTTP endpoint on port 9001 (or PORT_METRICS env var).
"""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from prometheus_client import Counter, Histogram, generate_latest, REGISTRY

logger = logging.getLogger(__name__)

tasks_processed_total = Counter(
    "tasks_processed_total",
    "Total number of tasks processed by outcome and type",
    labelnames=["outcome", "task_type"],
    registry=REGISTRY,
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Duration of task processing in seconds",
    labelnames=["task_type"],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
    registry=REGISTRY,
)

task_attempts_total = Counter(
    "task_attempts_total",
    "Total number of task attempts",
    registry=REGISTRY,
)

worker_heartbeat_missed_total = Counter(
    "worker_heartbeat_missed_total",
    "Total number of missed heartbeats",
    registry=REGISTRY,
)


class _MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(generate_latest(REGISTRY))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)


def start_metrics_server(port: int = 9001) -> None:
    server = HTTPServer(("0.0.0.0", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Worker metrics server started on port %d", port)
