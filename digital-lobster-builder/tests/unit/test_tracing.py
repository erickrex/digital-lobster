"""Unit tests for Gradient tracing helpers."""

from __future__ import annotations

import pytest

from src.gradient.tracing import (
    LoggingBackend,
    ReasoningStep,
    SpanStatus,
    TraceSpan,
    Tracer,
    TracingBackend,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


class RecordingBackend:
    """In-memory backend that captures sent spans for assertions."""

    def __init__(self) -> None:
        self.sent: list[TraceSpan] = []

    async def send_span(self, span: TraceSpan) -> None:
        self.sent.append(span)


# ------------------------------------------------------------------
# TraceSpan unit tests
# ------------------------------------------------------------------


class TestTraceSpan:
    def test_add_reasoning_step(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        step = span.add_reasoning_step("Downloading ZIP", size=42)

        assert len(span.reasoning_chain) == 1
        assert step.step_index == 0
        assert step.description == "Downloading ZIP"
        assert step.metadata == {"size": 42}

    def test_reasoning_steps_auto_increment_index(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        span.add_reasoning_step("Step 0")
        span.add_reasoning_step("Step 1")
        span.add_reasoning_step("Step 2")

        assert [s.step_index for s in span.reasoning_chain] == [0, 1, 2]

    def test_set_error(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        span.set_error(ValueError("bad input"))

        assert span.status == SpanStatus.ERROR
        assert span.error_type == "ValueError"
        assert span.error_message == "bad input"

    def test_set_ok_without_artifacts(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        span.set_ok()

        assert span.status == SpanStatus.OK
        assert span.artifacts_produced == []

    def test_set_ok_with_artifacts(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        span.set_ok(artifacts=["inventory", "kb_ref"])

        assert span.status == SpanStatus.OK
        assert span.artifacts_produced == ["inventory", "kb_ref"]

    def test_to_dict_contains_all_fields(self):
        span = TraceSpan(
            span_id="s1",
            run_id="r1",
            agent_name="A0",
            start_time=100.0,
            end_time=105.0,
            duration_seconds=5.0,
        )
        span.set_ok(artifacts=["inv"])
        span.add_reasoning_step("step one")

        d = span.to_dict()
        assert d["span_id"] == "s1"
        assert d["run_id"] == "r1"
        assert d["agent_name"] == "A0"
        assert d["status"] == "ok"
        assert d["duration_seconds"] == 5.0
        assert d["reasoning_steps"] == 1
        assert d["artifacts_produced"] == ["inv"]

    def test_to_dict_with_no_status(self):
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        d = span.to_dict()
        assert d["status"] is None


# ------------------------------------------------------------------
# Tracer context manager tests
# ------------------------------------------------------------------


class TestTracer:
    @pytest.mark.asyncio
    async def test_agent_span_records_duration(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("BlueprintIntake") as span:
            span.add_reasoning_step("Validating bundle")

        assert len(backend.sent) == 1
        recorded = backend.sent[0]
        assert recorded.agent_name == "BlueprintIntake"
        assert recorded.status == SpanStatus.OK
        assert recorded.duration_seconds is not None
        assert recorded.duration_seconds >= 0
        assert recorded.start_time is not None
        assert recorded.end_time is not None

    @pytest.mark.asyncio
    async def test_agent_span_defaults_to_ok(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("PrdLite"):
            pass  # caller doesn't set status

        assert backend.sent[0].status == SpanStatus.OK

    @pytest.mark.asyncio
    async def test_agent_span_preserves_explicit_ok(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("Modeling") as span:
            span.set_ok(artifacts=["manifest"])

        assert backend.sent[0].artifacts_produced == ["manifest"]

    @pytest.mark.asyncio
    async def test_agent_span_marks_error_on_exception(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        with pytest.raises(RuntimeError, match="boom"):
            async with tracer.agent_span("QA") as span:
                span.add_reasoning_step("Running build")
                raise RuntimeError("boom")

        assert len(backend.sent) == 1
        recorded = backend.sent[0]
        assert recorded.status == SpanStatus.ERROR
        assert recorded.error_type == "RuntimeError"
        assert recorded.error_message == "boom"
        assert recorded.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_agent_span_re_raises_exception(self):
        tracer = Tracer(run_id="run-1", backend=RecordingBackend())

        with pytest.raises(ValueError):
            async with tracer.agent_span("Importer"):
                raise ValueError("bad content")

    @pytest.mark.asyncio
    async def test_spans_property_accumulates(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("A0"):
            pass
        async with tracer.agent_span("A1"):
            pass

        assert len(tracer.spans) == 2
        assert tracer.spans[0].agent_name == "A0"
        assert tracer.spans[1].agent_name == "A1"

    @pytest.mark.asyncio
    async def test_spans_returns_copy(self):
        tracer = Tracer(run_id="run-1", backend=RecordingBackend())
        async with tracer.agent_span("A0"):
            pass

        spans = tracer.spans
        spans.clear()
        assert len(tracer.spans) == 1  # original unaffected

    @pytest.mark.asyncio
    async def test_get_agent_durations(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("A0"):
            pass
        async with tracer.agent_span("A1"):
            pass

        durations = tracer.get_agent_durations()
        assert "A0" in durations
        assert "A1" in durations
        assert all(d >= 0 for d in durations.values())

    @pytest.mark.asyncio
    async def test_get_failed_spans(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("A0"):
            pass

        with pytest.raises(RuntimeError):
            async with tracer.agent_span("A1"):
                raise RuntimeError("fail")

        failed = tracer.get_failed_spans()
        assert len(failed) == 1
        assert failed[0].agent_name == "A1"

    @pytest.mark.asyncio
    async def test_run_id_property(self):
        tracer = Tracer(run_id="my-run", backend=RecordingBackend())
        assert tracer.run_id == "my-run"

    @pytest.mark.asyncio
    async def test_span_ids_are_unique(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-1", backend=backend)

        async with tracer.agent_span("A0"):
            pass
        async with tracer.agent_span("A1"):
            pass

        ids = [s.span_id for s in tracer.spans]
        assert len(set(ids)) == 2

    @pytest.mark.asyncio
    async def test_span_run_id_matches_tracer(self):
        backend = RecordingBackend()
        tracer = Tracer(run_id="run-42", backend=backend)

        async with tracer.agent_span("A0"):
            pass

        assert backend.sent[0].run_id == "run-42"


# ------------------------------------------------------------------
# LoggingBackend tests
# ------------------------------------------------------------------


class TestLoggingBackend:
    @pytest.mark.asyncio
    async def test_send_ok_span_logs_info(self, caplog):
        backend = LoggingBackend()
        span = TraceSpan(
            span_id="s1",
            run_id="r1",
            agent_name="A0",
            duration_seconds=1.5,
        )
        span.set_ok()

        with caplog.at_level("INFO", logger="src.gradient.tracing"):
            await backend.send_span(span)

        assert any("OK" in r.message and "A0" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_send_error_span_logs_error(self, caplog):
        backend = LoggingBackend()
        span = TraceSpan(span_id="s1", run_id="r1", agent_name="A0")
        span.set_error(RuntimeError("oops"))

        with caplog.at_level("ERROR", logger="src.gradient.tracing"):
            await backend.send_span(span)

        assert any("FAILED" in r.message and "oops" in r.message for r in caplog.records)


# ------------------------------------------------------------------
# TracingBackend protocol check
# ------------------------------------------------------------------


class TestTracingBackendProtocol:
    def test_recording_backend_satisfies_protocol(self):
        assert isinstance(RecordingBackend(), TracingBackend)

    def test_logging_backend_satisfies_protocol(self):
        assert isinstance(LoggingBackend(), TracingBackend)
