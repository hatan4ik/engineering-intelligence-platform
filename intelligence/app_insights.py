from __future__ import annotations

from typing import Mapping

from .incidents import EvidenceEvent, EvidenceKind, utc


def from_app_insights_request(row: Mapping[str, object], *, service: str) -> EvidenceEvent:
    success = str(row.get("success", "true")).lower() == "true"
    result_code = str(row.get("resultCode") or row.get("result_code") or "")
    name = str(row.get("name") or "request")
    duration = str(row.get("duration") or "")
    severity = 1 if success else 4
    return EvidenceEvent(
        id=_event_id("request", row),
        kind=EvidenceKind.TRACE,
        service=service,
        timestamp=utc(_timestamp(row)),
        summary=f"request {name} result={result_code or 'unknown'} success={success} duration={duration or 'unknown'}",
        source="app-insights:requests",
        severity=severity,
        attributes=_attributes(row, ("operation_Id", "cloud_RoleName", "url", "resultCode", "duration")),
    )


def from_app_insights_dependency(row: Mapping[str, object], *, service: str) -> EvidenceEvent:
    success = str(row.get("success", "true")).lower() == "true"
    target = str(row.get("target") or "dependency")
    dep_type = str(row.get("type") or "dependency")
    name = str(row.get("name") or "call")
    result_code = str(row.get("resultCode") or "")
    return EvidenceEvent(
        id=_event_id("dependency", row),
        kind=EvidenceKind.TRACE,
        service=service,
        timestamp=utc(_timestamp(row)),
        summary=f"dependency {dep_type} {target} {name} result={result_code or 'unknown'} success={success}",
        source="app-insights:dependencies",
        severity=1 if success else 4,
        attributes=_attributes(row, ("operation_Id", "target", "type", "name", "resultCode", "duration")),
    )


def from_app_insights_exception(row: Mapping[str, object], *, service: str) -> EvidenceEvent:
    exc_type = str(row.get("type") or row.get("typeName") or "Exception")
    message = str(row.get("outerMessage") or row.get("message") or "")
    return EvidenceEvent(
        id=_event_id("exception", row),
        kind=EvidenceKind.LOG,
        service=service,
        timestamp=utc(_timestamp(row)),
        summary=f"{exc_type}: {message}".strip(),
        source="app-insights:exceptions",
        severity=5,
        attributes=_attributes(row, ("operation_Id", "problemId", "type", "outerMessage")),
    )


def from_otel_span(span: Mapping[str, object], *, service: str) -> EvidenceEvent:
    status = span.get("status") or {}
    status_code = str(status.get("code") or "UNSET") if isinstance(status, Mapping) else str(status)
    attrs = span.get("attributes") or {}
    if not isinstance(attrs, Mapping):
        attrs = {}
    name = str(span.get("name") or "span")
    error = status_code.upper() in {"ERROR", "STATUS_CODE_ERROR"} or str(attrs.get("error", "false")).lower() == "true"
    timestamp = str(span.get("start_time") or span.get("startTime") or span.get("timestamp") or "")
    if not timestamp:
        raise ValueError("OTel span timestamp is required")
    return EvidenceEvent(
        id=str(span.get("span_id") or span.get("spanId") or _event_id("span", span)),
        kind=EvidenceKind.TRACE,
        service=service,
        timestamp=utc(timestamp),
        summary=f"span {name} status={status_code}",
        source="opentelemetry",
        severity=4 if error else 1,
        attributes=tuple(sorted((str(k), str(v)) for k, v in attrs.items() if k in {
            "http.response.status_code", "rpc.system", "server.address", "db.system", "messaging.system", "error.type"
        })),
    )


def operation_id(event: EvidenceEvent) -> str | None:
    for key, value in event.attributes:
        if key == "operation_Id":
            return value
    return None


def correlated_operation_failures(events: list[EvidenceEvent]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for event in events:
        if event.severity < 3:
            continue
        op = operation_id(event)
        if op:
            grouped.setdefault(op, []).append(event.id)
    return {op: tuple(ids) for op, ids in grouped.items() if len(ids) >= 2}


def _event_id(prefix: str, row: Mapping[str, object]) -> str:
    return str(row.get("id") or row.get("itemId") or row.get("operation_Id") or f"{prefix}:{_timestamp(row)}")


def _timestamp(row: Mapping[str, object]) -> str:
    value = row.get("timestamp") or row.get("timeGenerated") or row.get("time")
    if not value:
        raise ValueError("telemetry timestamp is required")
    return str(value)


def _attributes(row: Mapping[str, object], keys: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, str(row[key])) for key in keys if row.get(key) is not None))
