"""W3C Distributed Tracing and OpenTelemetry context propagation utilities (FEAT-03 & IMP-20).

Adheres to OpenTelemetry Python API and W3C Trace Context specifications.
Provides:
- OpenTelemetry SDK TracerProvider & OTLP SpanExporter initialization
- Carrier injection/extraction using TraceContextTextMapPropagator
- Span context helpers (trace_id formatting, span lifecycle)
- Backward-compatible W3C traceparent formatting/parsing
"""
from __future__ import annotations

import logging
import re
import secrets
from typing import Mapping

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

_TRACEPARENT_PATTERN = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
    re.IGNORECASE,
)
_PROPAGATOR = TraceContextTextMapPropagator()


def init_tracer(service_name: str = "taskforge", otlp_endpoint: str | None = None) -> Tracer:
    """Initialize OpenTelemetry TracerProvider with optional OTLP HTTP SpanExporter."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry OTLP exporter configured for %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("Failed to configure OTLP exporter: %s", exc)

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def get_tracer(service_name: str = "taskforge") -> Tracer:
    """Get or return the active OpenTelemetry tracer."""
    return trace.get_tracer(service_name)


def get_current_trace_id() -> str | None:
    """Return the current active 32-character hex trace ID, or None if no active span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """Return the current active 16-character hex span ID, or None if no active span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.span_id, "016x")
    return None


def inject_carrier() -> dict[str, str]:
    """Inject current span context into a W3C carrier dictionary (e.g. for HTTP/AMQP headers)."""
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return carrier


def extract_context_from_carrier(carrier: Mapping[str, str] | None):
    """Extract OpenTelemetry context from an inbound carrier dictionary."""
    if not carrier:
        return None
    # Normalize header casing if necessary
    normalized = {k.lower(): v for k, v in carrier.items() if isinstance(v, str)}
    return _PROPAGATOR.extract(carrier=normalized)


# --- Backward-compatible & fallback utilities ---

def generate_trace_id() -> str:
    """Generate a random 32-character hex trace ID."""
    return secrets.token_hex(16)


def generate_span_id() -> str:
    """Generate a random 16-character hex span ID."""
    return secrets.token_hex(8)


def create_traceparent(trace_id: str | None = None, span_id: str | None = None, sampled: bool = True) -> str:
    """Create a W3C traceparent header string."""
    t_id = trace_id or generate_trace_id()
    s_id = span_id or generate_span_id()
    flags = "01" if sampled else "00"
    return f"00-{t_id}-{s_id}-{flags}"


def parse_traceparent(traceparent: str | None) -> tuple[str | None, str | None, bool]:
    """Parse a W3C traceparent header into (trace_id, parent_id, is_sampled).

    Returns (None, None, False) if the header is invalid or missing.
    """
    if not traceparent:
        return None, None, False
    match = _TRACEPARENT_PATTERN.match(traceparent.strip())
    if not match:
        return None, None, False
    version, trace_id_val, parent_id_val, flags = match.groups()
    if version != "00":
        return None, None, False
    if trace_id_val == "00000000000000000000000000000000":
        return None, None, False
    if parent_id_val == "0000000000000000":
        return None, None, False

    is_sampled = (int(flags, 16) & 0x01) == 1
    return trace_id_val, parent_id_val, is_sampled


def extract_trace_context(headers: Mapping[str, str] | None) -> tuple[str, str]:
    """Extract trace_id and generate a child span_id from inbound headers, or generate new ones.

    Returns:
        (trace_id, current_span_id)
    """
    if headers:
        for key in ("traceparent", "Traceparent", "TRACEPARENT"):
            if key in headers:
                trace_id_val, parent_id_val, _ = parse_traceparent(headers[key])
                if trace_id_val:
                    return trace_id_val, generate_span_id()

    return generate_trace_id(), generate_span_id()
