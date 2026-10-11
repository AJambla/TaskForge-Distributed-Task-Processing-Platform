"""W3C Distributed Tracing context propagation utilities (IMP-20).

Adheres to W3C Trace Context recommendation:
Format: traceparent: 00-{trace_id}-{parent_id/span_id}-{trace_flags}
- version: 2 hex characters ("00")
- trace_id: 32 hex characters (16 bytes)
- parent_id: 16 hex characters (8 bytes)
- trace_flags: 2 hex characters ("01" for sampled)
"""
from __future__ import annotations

import os
import re
import secrets
from typing import Mapping

_TRACEPARENT_PATTERN = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
    re.IGNORECASE,
)


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
    version, trace_id, parent_id, flags = match.groups()
    if version != "00":
        return None, None, False
    # Validate trace_id is not all zeros
    if trace_id == "00000000000000000000000000000000":
        return None, None, False
    # Validate parent_id is not all zeros
    if parent_id == "0000000000000000":
        return None, None, False

    is_sampled = (int(flags, 16) & 0x01) == 1
    return trace_id, parent_id, is_sampled


def extract_trace_context(headers: Mapping[str, str] | None) -> tuple[str, str]:
    """Extract trace_id and generate a child span_id from inbound headers, or generate new ones.

    Returns:
        (trace_id, current_span_id)
    """
    if headers:
        for key in ("traceparent", "Traceparent", "TRACEPARENT"):
            if key in headers:
                trace_id, parent_id, _ = parse_traceparent(headers[key])
                if trace_id:
                    return trace_id, generate_span_id()

    # Generate new trace context
    return generate_trace_id(), generate_span_id()
