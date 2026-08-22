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

    Specific failure classes take precedence over generic deployment correlation.
    Live adapter preconditions must still confirm the mutable runtime condition.
    """
    for hypothesis in analysis.hypotheses:
        title = hypothesis.title.lower()
        if "crashloopbackoff" in title:
            return RemediationPlan(
                "aks.restart.crashloop",
                "CrashLoopBackOff evidence selects a bounded restart with live pod-state preflight",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )
        if "readiness regression" in title:
            return RemediationPlan(
                "aks.rollback.readiness",
                "post-release readiness regression selects rollback with rollout-history preflight",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )
        if "oomkilled" in title or "memory pressure" in title:
            return RemediationPlan(
                "aks.restart.oom",
                "OOM evidence selects bounded recovery without silently changing resource policy",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )

    for hypothesis in analysis.hypotheses:
        title = hypothesis.title.lower()
        if "deployment" in title and "incident" in title:
            return RemediationPlan(
                "aks.rollout.undo",
                "recent deployment is correlated with incident onset",
                hypothesis.evidence_ids,
                hypothesis.confidence,
            )
    return None
