"""Portable W3C trace-context helpers shared by transport adapters.

Trace headers are observability metadata, never authorization input.  Invalid
or absent headers produce a fresh local trace instead of being reflected into
responses or durable records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from opentelemetry import propagate, trace
from opentelemetry.context import Context


TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"


@dataclass(frozen=True)
class TraceContext:
    """The validated, serializable W3C trace context at an integration edge."""

    traceparent: str | None = None
    tracestate: str | None = None

    def __post_init__(self) -> None:
        if self.traceparent is not None and not isinstance(self.traceparent, str):
            raise TypeError("traceparent must be a string or None")
        if self.tracestate is not None and not isinstance(self.tracestate, str):
            raise TypeError("tracestate must be a string or None")
        supplied = self.headers()
        if supplied and _normalized_headers(supplied) != supplied:
            raise ValueError("trace context must contain a valid W3C traceparent/tracestate pair")

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "TraceContext":
        """Normalize a valid remote parent and discard malformed trace metadata."""

        return cls(**_normalized_headers(headers))

    @classmethod
    def current(cls) -> "TraceContext":
        """Capture the current span in a serializable form for a downstream hop."""

        carrier: dict[str, str] = {}
        propagate.inject(carrier)
        return cls(
            traceparent=carrier.get(TRACEPARENT_HEADER),
            tracestate=carrier.get(TRACESTATE_HEADER),
        )

    def headers(self) -> dict[str, str]:
        """Return only validated headers suitable for an outbound adapter call."""

        headers: dict[str, str] = {}
        if self.traceparent is not None:
            headers[TRACEPARENT_HEADER] = self.traceparent
        if self.tracestate is not None:
            headers[TRACESTATE_HEADER] = self.tracestate
        return headers

    def otel_context(self) -> Context:
        """Build the OpenTelemetry parent context used to create a server span."""

        return propagate.extract(self.headers())


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return OTel's canonical header representation, or no parent context."""

    extracted = propagate.extract(dict(headers))
    if not trace.get_current_span(extracted).get_span_context().is_valid:
        return {}
    carrier: dict[str, str] = {}
    propagate.inject(carrier, context=extracted)
    return {
        key: value
        for key, value in carrier.items()
        if key in {TRACEPARENT_HEADER, TRACESTATE_HEADER}
    }
