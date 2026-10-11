"""Unit tests for JSON logging formatter (IMP-08)."""
import json
import logging
from app.core.logging import JSONFormatter, configure_logging


def test_json_formatter_outputs_valid_json_with_expected_fields():
    formatter = JSONFormatter(service_name="test-service")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Task processed successfully",
        args=(),
        exc_info=None,
    )
    record.task_id = "12345"
    record.worker_hostname = "worker-1"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["service"] == "test-service"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Task processed successfully"
    assert data["task_id"] == "12345"
    assert data["worker_hostname"] == "worker-1"
    assert "timestamp" in data


def test_configure_logging_switches_handlers():
    configure_logging(service_name="my-service", log_level="DEBUG", json_format=True)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)
