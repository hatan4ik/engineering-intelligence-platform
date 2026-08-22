from __future__ import annotations

from dataclasses import dataclass

from intelligence.app_insights import correlated_operation_failures
from intelligence.incidents import IncidentAnalysis


@dataclass(frozen=True)
class IncidentIntelligenceView:
    incident_id: str
    service: str
    impacted_services: tuple[str, ...]
    timeline: tuple[dict[str, object], ...]
    hypotheses: tuple[dict[str, object], ...]
    correlated_operations: dict[str, tuple[str, ...]]


def build_incident_view(
    *,
    incident_id: str,
    service: str,
    impacted_services: tuple[str, ...],
    analysis: IncidentAnalysis,
) -> IncidentIntelligenceView:
    timeline = tuple(
        {
            "id": event.id,
            "kind": event.kind.value,
            "timestamp": event.timestamp.isoformat(),
            "summary": event.summary,
            "source": event.source,
            "severity": event.severity,
        }
        for event in analysis.timeline
    )
    hypotheses = tuple(
        {
            "title": hypothesis.title,
            "confidence": hypothesis.confidence,
            "facts": list(hypothesis.facts),
            "inferences": list(hypothesis.inferences),
            "evidence_ids": list(hypothesis.evidence_ids),
        }
        for hypothesis in analysis.hypotheses
    )
    return IncidentIntelligenceView(
        incident_id=incident_id,
        service=service,
        impacted_services=tuple(sorted(set(impacted_services))),
        timeline=timeline,
        hypotheses=hypotheses,
        correlated_operations=correlated_operation_failures(list(analysis.timeline)),
    )
