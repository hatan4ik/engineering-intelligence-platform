from __future__ import annotations

from .incidents import EvidenceEvent, EvidenceKind, utc


def from_azure_monitor(row: dict) -> EvidenceEvent:
    kind = str(row.get("kind", "alert")).lower()
    mapped = {
        "alert": EvidenceKind.ALERT,
        "metric": EvidenceKind.METRIC,
        "log": EvidenceKind.LOG,
        "trace": EvidenceKind.TRACE,
    }.get(kind, EvidenceKind.LOG)
    return EvidenceEvent(
        id=str(row["id"]),
        kind=mapped,
        service=str(row["service"]),
        timestamp=utc(str(row["timestamp"])),
        summary=str(row.get("summary") or row.get("message") or kind),
        source=str(row.get("source", "azure-monitor")),
        severity=int(row.get("severity", 1)),
        attributes=tuple(sorted((str(k), str(v)) for k, v in row.get("attributes", {}).items())),
    )


def from_kubernetes_event(event: dict) -> EvidenceEvent:
    involved = event.get("involvedObject", {})
    metadata = event.get("metadata", {})
    reason = str(event.get("reason", "KubernetesEvent"))
    message = str(event.get("message", reason))
    annotations = metadata.get("annotations", {}) or {}
    service = (
        annotations.get("eip.openai/service")
        or metadata.get("labels", {}).get("app")
        or involved.get("name")
        or "unknown"
    )
    severity = 4 if reason.lower() in {"oomkilled", "backoff", "failed", "unhealthy"} else 2
    timestamp = event.get("eventTime") or event.get("lastTimestamp") or metadata.get("creationTimestamp")
    return EvidenceEvent(
        id=str(metadata.get("uid") or f"k8s:{service}:{reason}:{timestamp}"),
        kind=EvidenceKind.K8S_EVENT,
        service=str(service),
        timestamp=utc(str(timestamp)),
        summary=f"{reason}: {message}",
        source="kubernetes",
        severity=severity,
        attributes=(("object_kind", str(involved.get("kind", ""))), ("object_name", str(involved.get("name", "")))),
    )
