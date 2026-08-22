from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from remediation.catalog import AutonomyLevel
from remediation.policy import ServiceAutonomy
from resilience.exercises import ExerciseKind, ExerciseResult, certification_from_exercises
from resilience.policy import AutonomyCertification


L3_REQUIRED_KINDS = frozenset({
    ExerciseKind.SUCCESSFUL_REMEDIATION,
    ExerciseKind.VERIFICATION_FAILURE,
    ExerciseKind.ROLLBACK,
    ExerciseKind.KILL_SWITCH,
    ExerciseKind.POLICY_OUTAGE,
    ExerciseKind.AUDIT_OUTAGE,
})
L4_REQUIRED_KINDS = L3_REQUIRED_KINDS | {ExerciseKind.ERROR_BUDGET_EXHAUSTED}


@dataclass(frozen=True)
class CertificationReport:
    service: str
    environment: str
    runbook_id: str
    generated_at: str
    evidence_digest: str
    passed_kinds: tuple[str, ...]
    failed_kinds: tuple[str, ...]
    l3_eligible: bool
    l4_eligible: bool
    missing_l3_controls: tuple[str, ...]
    missing_l4_controls: tuple[str, ...]


def certify_l4_policy(policy: ServiceAutonomy, certification: AutonomyCertification) -> None:
    if policy.level is not AutonomyLevel.BOUNDED_AUTONOMOUS:
        raise ValueError("L4 certification requires a bounded-autonomous service policy")
    if (policy.service, policy.environment) != (certification.service, certification.environment):
        raise ValueError("certification does not match service/environment policy scope")
    if certification.runbook_id not in policy.certified_runbooks:
        raise ValueError("certification runbook is not present in service policy")
    if policy.max_blast_radius > certification.max_blast_radius:
        raise ValueError("service policy blast radius exceeds certification evidence")
    if not certification.l4_eligible:
        raise PermissionError("L4 controls incomplete: " + ", ".join(certification.missing_controls))


def _digest(exercises: tuple[ExerciseResult, ...]) -> str:
    payload = [asdict(e) for e in sorted(exercises, key=lambda x: (x.kind.value, x.evidence_ref))]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_certification_report(
    *,
    service: str,
    environment: str,
    runbook_id: str,
    certified_max_blast_radius: int,
    security_reviewed: bool,
    verification_independent: bool,
    exercises: tuple[ExerciseResult, ...],
    generated_at: str | None = None,
) -> CertificationReport:
    relevant = tuple(
        e for e in exercises
        if e.service == service and e.environment == environment and e.runbook_id == runbook_id
    )
    passed = tuple(e for e in relevant if e.passed)
    failed = tuple(e for e in relevant if not e.passed)
    passed_kinds = {e.kind for e in passed}

    cert = certification_from_exercises(
        service=service,
        environment=environment,
        runbook_id=runbook_id,
        certified_max_blast_radius=certified_max_blast_radius,
        security_reviewed=security_reviewed,
        verification_independent=verification_independent,
        exercises=relevant,
        minimum_exercises=len(L4_REQUIRED_KINDS),
    )

    l3_missing: list[str] = []
    if certified_max_blast_radius <= 0:
        l3_missing.append("bounded-blast-radius")
    if not security_reviewed:
        l3_missing.append("security-review")
    if not verification_independent:
        l3_missing.append("independent-verification")
    for kind in sorted(L3_REQUIRED_KINDS - passed_kinds, key=lambda k: k.value):
        l3_missing.append(f"exercise:{kind.value}")
    if failed:
        l3_missing.append("failed-exercise-present")
    if any(not e.evidence_ref.strip() for e in passed):
        l3_missing.append("missing-evidence-reference")
    if any(e.observed_blast_radius > certified_max_blast_radius for e in passed):
        l3_missing.append("blast-radius-exceeded")

    l4_missing = list(l3_missing)
    for kind in sorted(L4_REQUIRED_KINDS - passed_kinds, key=lambda k: k.value):
        key = f"exercise:{kind.value}"
        if key not in l4_missing:
            l4_missing.append(key)
    for control in cert.missing_controls:
        if control not in l4_missing:
            l4_missing.append(control)

    l3_eligible = not l3_missing
    l4_eligible = l3_eligible and cert.l4_eligible and not l4_missing
    return CertificationReport(
        service=service,
        environment=environment,
        runbook_id=runbook_id,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        evidence_digest=_digest(relevant),
        passed_kinds=tuple(sorted(k.value for k in passed_kinds)),
        failed_kinds=tuple(sorted(e.kind.value for e in failed)),
        l3_eligible=l3_eligible,
        l4_eligible=l4_eligible,
        missing_l3_controls=tuple(l3_missing),
        missing_l4_controls=tuple(l4_missing),
    )
