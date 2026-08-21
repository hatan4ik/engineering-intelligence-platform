from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .policy import AutonomyCertification


class ExerciseKind(StrEnum):
    SUCCESSFUL_REMEDIATION = "successful_remediation"
    VERIFICATION_FAILURE = "verification_failure"
    ROLLBACK = "rollback"
    KILL_SWITCH = "kill_switch"
    POLICY_OUTAGE = "policy_outage"
    AUDIT_OUTAGE = "audit_outage"
    ERROR_BUDGET_EXHAUSTED = "error_budget_exhausted"


@dataclass(frozen=True)
class ExerciseResult:
    kind: ExerciseKind
    passed: bool
    service: str
    environment: str
    runbook_id: str
    observed_blast_radius: int
    evidence_ref: str


def certification_from_exercises(
    *,
    service: str,
    environment: str,
    runbook_id: str,
    certified_max_blast_radius: int,
    security_reviewed: bool,
    verification_independent: bool,
    exercises: tuple[ExerciseResult, ...],
    minimum_exercises: int = 3,
) -> AutonomyCertification:
    relevant = tuple(
        e
        for e in exercises
        if e.service == service
        and e.environment == environment
        and e.runbook_id == runbook_id
    )
    passed = tuple(e for e in relevant if e.passed)
    observed_within_budget = all(
        e.observed_blast_radius <= certified_max_blast_radius for e in passed
    )
    kinds = {e.kind for e in passed}
    return AutonomyCertification(
        service=service,
        environment=environment,
        runbook_id=runbook_id,
        max_blast_radius=certified_max_blast_radius if observed_within_budget else 0,
        rollback_tested=ExerciseKind.ROLLBACK in kinds,
        kill_switch_tested=ExerciseKind.KILL_SWITCH in kinds,
        verification_independent=verification_independent,
        security_reviewed=security_reviewed,
        error_budget_enforced=ExerciseKind.ERROR_BUDGET_EXHAUSTED in kinds,
        policy_fail_closed_tested=ExerciseKind.POLICY_OUTAGE in kinds,
        audit_fail_closed_tested=ExerciseKind.AUDIT_OUTAGE in kinds,
        successful_exercises=len(passed),
        minimum_exercises=minimum_exercises,
    )
