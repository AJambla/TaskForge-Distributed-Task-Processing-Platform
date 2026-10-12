"""Unit tests for OpenTelemetry tracing foundation and context propagation (FEAT-03)."""
from __future__ import annotations


from app.core.tracing import (
    create_traceparent,
    extract_context_from_carrier,
    get_current_span_id,
    get_current_trace_id,
    init_tracer,
    inject_carrier,
    parse_traceparent,
)


def test_init_tracer_and_span_creation():
    """Verify tracer initialization and span creation with active trace context."""
    tracer = init_tracer("taskforge-test")
    assert tracer is not None

    with tracer.start_as_current_span("test-operation"):
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        assert trace_id is not None
        assert len(trace_id) == 32
        assert span_id is not None
        assert len(span_id) == 16

        # Test carrier injection inside active span
        carrier = inject_carrier()
        assert "traceparent" in carrier
        assert trace_id in carrier["traceparent"]


def test_extract_context_from_carrier():
    """Verify carrier extraction propagates context to child spans."""
    tracer = init_tracer("taskforge-test-extract")
    sample_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    carrier = {"traceparent": sample_traceparent}

    extracted_ctx = extract_context_from_carrier(carrier)
    assert extracted_ctx is not None

    with tracer.start_as_current_span("child-span", context=extracted_ctx):
        child_trace_id = get_current_trace_id()
        assert child_trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_w3c_backward_compatibility():
    """Verify legacy W3C functions create and parse correctly."""
    tp = create_traceparent(trace_id="4bf92f3577b34da6a3ce929d0e0e4736", span_id="00f067aa0ba902b7")
    assert tp == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    t_id, s_id, sampled = parse_traceparent(tp)
    assert t_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert s_id == "00f067aa0ba902b7"
    assert sampled is True
