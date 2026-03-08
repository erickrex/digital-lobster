from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


class SpanStatus(str, Enum):
    """Possible terminal states for a trace span."""

    OK = "ok"
    ERROR = "error"


@dataclass
class ReasoningStep:
    """A single reasoning step within an agent span."""

    step_index: int
    description: str
    timestamp: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceSpan:
    """A structured trace span capturing one agent execution."""

    span_id: str
    run_id: str
    agent_name: str
    status: SpanStatus | None = None
    start_time: float | None = None
    end_time: float | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    error_type: str | None = None
    reasoning_chain: list[ReasoningStep] = field(default_factory=list)
    artifacts_produced: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_reasoning_step(
        self, description: str, **metadata: Any
    ) -> ReasoningStep:
        """Record a reasoning step in this span."""
        step = ReasoningStep(
            step_index=len(self.reasoning_chain),
            description=description,
            metadata=metadata,
        )
        self.reasoning_chain.append(step)
        return step

    def set_error(self, exc: BaseException) -> None:
        """Mark the span as failed with error details."""
        self.status = SpanStatus.ERROR
        self.error_type = type(exc).__qualname__
        self.error_message = str(exc)

    def set_ok(self, artifacts: list[str] | None = None) -> None:
        """Mark the span as successfully completed."""
        self.status = SpanStatus.OK
        if artifacts:
            self.artifacts_produced = artifacts

    def to_dict(self) -> dict[str, Any]:
        """Serialize the span to a plain dict for logging / export."""
        return {
            "span_id": self.span_id,
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "status": self.status.value if self.status else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "reasoning_steps": len(self.reasoning_chain),
            "artifacts_produced": self.artifacts_produced,
            "metadata": self.metadata,
        }


# ------------------------------------------------------------------
# Backend protocol (pluggable)
# ------------------------------------------------------------------


@runtime_checkable
class TracingBackend(Protocol):
    """Protocol for pushing trace spans to an observability backend."""

    async def send_span(self, span: TraceSpan) -> None: ...


class LoggingBackend:
    """Default backend that writes spans to the Python logger."""

    async def send_span(self, span: TraceSpan) -> None:
        """Log the completed span at INFO (ok) or ERROR level."""
        data = span.to_dict()
        if span.status == SpanStatus.ERROR:
            logger.error(
                "Trace span FAILED for agent %s [run=%s]: %s",
                span.agent_name,
                span.run_id,
                span.error_message,
                extra={"trace_span": data},
            )
        else:
            logger.info(
                "Trace span OK for agent %s [run=%s] (%.2fs, %d steps)",
                span.agent_name,
                span.run_id,
                span.duration_seconds or 0,
                len(span.reasoning_chain),
                extra={"trace_span": data},
            )


# ------------------------------------------------------------------
# Tracer — the main entry point
# ------------------------------------------------------------------


class Tracer:
    """Creates and manages trace spans for pipeline runs.

    Usage::

        tracer = Tracer(run_id="abc-123")

        async with tracer.agent_span("BlueprintIntakeAgent") as span:
            span.add_reasoning_step("Downloading ZIP from Spaces")
            # ... agent work ...
            span.set_ok(artifacts=["inventory", "kb_ref"])
    """

    def __init__(
        self,
        run_id: str,
        backend: TracingBackend | None = None,
    ) -> None:
        self._run_id = run_id
        self._backend: TracingBackend = backend or LoggingBackend()
        self._spans: list[TraceSpan] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def spans(self) -> list[TraceSpan]:
        """All spans recorded during this tracer's lifetime."""
        return list(self._spans)

    @asynccontextmanager
    async def agent_span(self, agent_name: str) -> AsyncIterator[TraceSpan]:
        """Async context manager that wraps an agent execution.

        Records start time on entry, end time on exit, and sends the
        span to the backend. If an exception propagates out, the span
        is marked as an error before re-raising.
        """
        span = TraceSpan(
            span_id=uuid.uuid4().hex,
            run_id=self._run_id,
            agent_name=agent_name,
        )
        span.start_time = time.monotonic()
        logger.info(
            "Agent %s started [run=%s, span=%s]",
            agent_name,
            self._run_id,
            span.span_id,
        )

        try:
            yield span
        except BaseException as exc:
            span.set_error(exc)
            raise
        finally:
            span.end_time = time.monotonic()
            span.duration_seconds = span.end_time - span.start_time
            # Default to OK if the caller didn't set status explicitly
            if span.status is None:
                span.set_ok()
            self._spans.append(span)
            await self._backend.send_span(span)

    def get_agent_durations(self) -> dict[str, float]:
        """Return a mapping of agent name → duration in seconds."""
        return {
            s.agent_name: s.duration_seconds or 0.0
            for s in self._spans
        }

    def get_failed_spans(self) -> list[TraceSpan]:
        """Return all spans that ended with an error."""
        return [s for s in self._spans if s.status == SpanStatus.ERROR]
