"""Structured JSON log formatting for TaskForge (IMP-08)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Log formatter outputting single-line JSON with standard fields."""

    def __init__(self, service_name: str = "taskforge", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Contextual extra fields commonly logged
        for field in ("task_id", "worker_hostname", "task_type", "user_id"):
            val = getattr(record, field, None)
            if val is not None:
                log_obj[field] = str(val)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def configure_logging(service_name: str = "taskforge", log_level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger with either JSON or standard human-readable format."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    root.addHandler(handler)
