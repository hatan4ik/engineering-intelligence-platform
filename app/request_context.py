"""Request-scoped, validated context owned by the HTTP transport boundary."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request

from control_plane.correlation import CorrelationId, resolve_correlation_id
from telemetry.trace_context import TraceContext


CORRELATION_ID_HEADER = "x-correlation-id"
GITHUB_DELIVERY_HEADER = "x-github-delivery"
_CORRELATION_ATTRIBUTE = "eip_correlation_id"
_TRACE_ATTRIBUTE = "eip_trace_context"


def inbound_correlation_id(headers: Mapping[str, str]) -> CorrelationId:
    """Use an explicit request ID, then GitHub delivery ID, or mint one once."""

    return resolve_correlation_id(
        headers.get(CORRELATION_ID_HEADER) or headers.get(GITHUB_DELIVERY_HEADER)
    )


def bind_request_context(request: Request) -> CorrelationId:
    """Validate and attach immutable request context before a route executes."""

    correlation_id = inbound_correlation_id(request.headers)
    setattr(request.state, _CORRELATION_ATTRIBUTE, correlation_id)
    setattr(request.state, _TRACE_ATTRIBUTE, TraceContext.from_headers(request.headers))
    return correlation_id


def request_correlation_id(request: Request) -> CorrelationId:
    """Return the correlation ID bound by the application middleware."""

    value: object = getattr(request.state, _CORRELATION_ATTRIBUTE, None)
    if isinstance(value, str):
        return resolve_correlation_id(value)
    raise RuntimeError("request correlation context was not bound by application middleware")


def request_trace_context(request: Request) -> TraceContext:
    """Return the trace context bound by the application middleware."""

    value: object = getattr(request.state, _TRACE_ATTRIBUTE, None)
    if isinstance(value, TraceContext):
        return value
    raise RuntimeError("request trace context was not bound by application middleware")
