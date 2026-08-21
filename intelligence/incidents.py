from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class EvidenceKind(str, Enum):
    ALERT = "alert"
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    K8S_EVENT = "k8s_event"
    DEPLOYMENT = "deployment"
    INCIDENT = "incident"


@dataclass(frozen=True)
class EvidenceEvent:
    id: str
    kind: EvidenceKind
    service: str
    timestamp: datetime
    summary: str
    source: str
    severity: int = 1
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Hypothesis:
    title: str
    confidence: float
    facts: tuple[str, ...]
    inferences: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class IncidentAnalysis:
    timeline: tuple[EvidenceEvent, ...]
    hypotheses: tuple[Hypothesis, ...]


def analyze_incident(events: list[EvidenceEvent], *, service: str) -> IncidentAnalysis:
    relevant = sorted((e for e in events if e.service == service), key=lambda e: e.timestamp)
    hypotheses: list[Hypothesis] = []

    deployments = [e for e in relevant if e.kind == EvidenceKind.DEPLOYMENT]
    failures = [
        e for e in relevant
        if e.kind in {EvidenceKind.ALERT, EvidenceKind.K8S_EVENT, EvidenceKind.LOG}
        and e.severity >= 3
    ]
    if deployments and failures:
        latest_deploy = deployments[-1]
        first_failure = next((f for f in failures if f.timestamp >= latest_deploy.timestamp), None)
        if first_failure:
            delta = (first_failure.timestamp - latest_deploy.timestamp).total_seconds()
            if 0 <= delta <= 1800:
                confidence = 0.85 if delta <= 600 else 0.70
                hypotheses.append(Hypothesis(
                    title="Recent deployment is correlated with incident onset",
                    confidence=confidence,
                    facts=(
                        f"deployment {latest_deploy.id} occurred before failure {first_failure.id}",
                        f"failure began {int(delta)} seconds after deployment",
                    ),
                    inferences=("the deployment may have introduced the failing condition",),
                    evidence_ids=(latest_deploy.id, first_failure.id),
                ))

    oom = [e for e in relevant if "oom" in e.summary.lower() or "memory" in e.summary.lower()]
    if len(oom) >= 2:
        hypotheses.append(Hypothesis(
            title="Memory pressure is a likely contributing factor",
            confidence=min(0.95, 0.55 + 0.1 * len(oom)),
            facts=tuple(e.summary for e in oom[:4]),
            inferences=("memory limits, leaks, or workload growth should be investigated",),
            evidence_ids=tuple(e.id for e in oom[:4]),
        ))

    return IncidentAnalysis(tuple(relevant), tuple(sorted(hypotheses, key=lambda h: h.confidence, reverse=True)))


def utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
