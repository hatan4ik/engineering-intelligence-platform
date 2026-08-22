from __future__ import annotations

from dataclasses import dataclass

from intelligence.incidents import IncidentAnalysis


@dataclass(frozen=True)
class RemediationPlan:
    runbook_id: str
    reason: str
    evidence_ids: tuple[str, ...]
    confidence: float


def plan_from_incident(analysis: IncidentAnalysis) -> RemediationPlan | None:
    """Map evidence-backed hypotheses to a registered runbook ID.

    This is intentionally deterministic. LLM prose is never converted into an
    executable command; only known hypothesis classes can select known runbooks.
    """
    for hypothesis in analysis.hypotheses:
        title = hypothesis.title.lower()
        if "deployment" in title and "incident" in title:
            return RemediationPlan(
                "aks.rollout.undo",
                "recent deployment is correlated with incident onset",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )
    for hypothesis in analysis.hypotheses:
        title = hypothesis.title.lower()
        if "memory pressure" in title:
            return RemediationPlan(
                "aks.restart.workload",
                "memory-pressure evidence requires bounded workload recovery before deeper repair",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )
    return None
