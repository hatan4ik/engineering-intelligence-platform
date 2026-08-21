from __future__ import annotations

from dataclasses import dataclass

from .incidents import EvidenceEvent, EvidenceKind, Hypothesis


@dataclass(frozen=True)
class DeploymentFailureAnalysis:
    deployment_id: str
    service: str
    facts: tuple[str, ...]
    hypotheses: tuple[Hypothesis, ...]
    evidence_ids: tuple[str, ...]


def investigate_deployment_failure(
    events: list[EvidenceEvent], *, deployment_id: str, service: str
) -> DeploymentFailureAnalysis:
    deployment = next(
        (
            e
            for e in events
            if e.id == deployment_id
            and e.service == service
            and e.kind is EvidenceKind.DEPLOYMENT
        ),
        None,
    )
    if deployment is None:
        raise ValueError("deployment evidence not found")

    after = sorted(
        (e for e in events if e.service == service and e.timestamp >= deployment.timestamp),
        key=lambda e: e.timestamp,
    )
    failures = tuple(
        e
        for e in after
        if e.severity >= 3
        and e.kind in {EvidenceKind.ALERT, EvidenceKind.LOG, EvidenceKind.K8S_EVENT}
    )
    facts = (f"deployment {deployment.id} recorded at {deployment.timestamp.isoformat()}",) + tuple(
        f"{e.kind.value} {e.id}: {e.summary}" for e in failures[:6]
    )
    hypotheses: list[Hypothesis] = []
    if failures:
        first = failures[0]
        delta = int((first.timestamp - deployment.timestamp).total_seconds())
        if delta <= 1800:
            hypotheses.append(
                Hypothesis(
                    title="Deployment is temporally correlated with failure onset",
                    confidence=0.88 if delta <= 600 else 0.72,
                    facts=(
                        f"first severe failure occurred {delta} seconds after deployment",
                    ),
                    inferences=(
                        "the deployed change should be compared with the last known-good release",
                    ),
                    evidence_ids=(deployment.id, first.id),
                )
            )
    return DeploymentFailureAnalysis(
        deployment_id=deployment.id,
        service=service,
        facts=facts,
        hypotheses=tuple(hypotheses),
        evidence_ids=tuple(e.id for e in after),
    )
