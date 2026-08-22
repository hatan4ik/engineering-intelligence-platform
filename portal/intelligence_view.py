from __future__ import annotations

from dataclasses import dataclass

from feedback.store import FeedbackMetrics


@dataclass(frozen=True)
class KnowledgeHealth:
    stale: int = 0
    conflicts: int = 0
    missing_owner: int = 0


@dataclass(frozen=True)
class ArchitectureHealth:
    blocking_findings: int = 0
    advisory_findings: int = 0


@dataclass(frozen=True)
class IncidentHealth:
    active: int = 0
    recent_rca_confidence: float | None = None
    impacted_services: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceIntelligenceView:
    service: str
    owner: str | None
    tier: int
    repositories: tuple[str, ...]
    dependencies: tuple[str, ...]
    impacted_dependents: tuple[str, ...]
    slo_target: float | None
    slo_current: float | None
    change_risk_score: int | None
    knowledge: KnowledgeHealth
    architecture: ArchitectureHealth
    incidents: IncidentHealth
    feedback: FeedbackMetrics
    pending_approvals: int = 0
    last_remediation: str | None = None

    @property
    def attention_score(self) -> int:
        score = 0
        score += min(30, self.incidents.active * 10)
        score += min(20, self.architecture.blocking_findings * 10)
        score += min(15, self.knowledge.conflicts * 5)
        score += min(10, self.knowledge.stale * 2)
        if self.change_risk_score is not None:
            score += min(20, max(0, self.change_risk_score // 5))
        if self.slo_target is not None and self.slo_current is not None and self.slo_current < self.slo_target:
            score += 15
        return min(100, score)


def to_dict(view: ServiceIntelligenceView) -> dict[str, object]:
    return {
        "service": view.service,
        "owner": view.owner,
        "tier": view.tier,
        "repositories": list(view.repositories),
        "dependencies": list(view.dependencies),
        "impacted_dependents": list(view.impacted_dependents),
        "slo": {"target": view.slo_target, "current": view.slo_current},
        "change_risk_score": view.change_risk_score,
        "knowledge": {
            "stale": view.knowledge.stale,
            "conflicts": view.knowledge.conflicts,
            "missing_owner": view.knowledge.missing_owner,
        },
        "architecture": {
            "blocking_findings": view.architecture.blocking_findings,
            "advisory_findings": view.architecture.advisory_findings,
        },
        "incidents": {
            "active": view.incidents.active,
            "recent_rca_confidence": view.incidents.recent_rca_confidence,
            "impacted_services": list(view.incidents.impacted_services),
        },
        "feedback": {
            "total": view.feedback.total,
            "acceptance_rate": view.feedback.acceptance_rate,
            "precision": view.feedback.precision,
            "reverted": view.feedback.reverted,
        },
        "pending_approvals": view.pending_approvals,
        "last_remediation": view.last_remediation,
        "attention_score": view.attention_score,
    }
