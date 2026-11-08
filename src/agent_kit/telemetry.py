"""OpenTelemetry GenAI spans, emitted the same way on every adapter: invoke_agent -> execute_tool.

Uses the OpenTelemetry API if installed (`[otel]`); otherwise a no-op. Exporting is configured the standard way
(OTEL_EXPORTER_OTLP_ENDPOINT, or ADOT on AWS / the Telemetry API on Google Cloud). Message content is not recorded
unless KIT_CAPTURE_CONTENT=true, and then only after the redaction hook."""
from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from typing import Any

try:
    from opentelemetry import trace as _trace
    _tracer = _trace.get_tracer("agent_kit")
except ImportError:  # pragma: no cover - optional
    _trace, _tracer = None, None

CAPTURE = os.environ.get("KIT_CAPTURE_CONTENT", "false").lower() == "true"
_redact: Callable[[str], str] = lambda s: s  # noqa: E731 - replaced by the DPDP add-on


def set_redactor(fn: Callable[[str], str]) -> None:
    global _redact
    _redact = fn


def content(s: str | None) -> str | None:
    return _redact(s) if (CAPTURE and s) else None


@contextlib.contextmanager
def span(name: str, attrs: dict[str, Any]):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as sp:
        for k, v in attrs.items():
            if v is not None:
                sp.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
        yield sp


def trace_id() -> str | None:
    if _trace is None:
        return None
    ctx = _trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None
