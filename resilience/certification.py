"""Certification reports and the scoped L4 certification record.

Two things live here and they are not the same thing:

``build_certification_report``
    an *assessment* of a set of exercises. It is a reviewer's aid. It does not
    read ``ExerciseResult.evidence_grade``, so a rehearsal suite can still
    produce ``l4_eligible=True`` in it. Nothing in the execution path consumes
    it, and nothing should start to.

``evaluate_l4_eligibility`` / ``L4CertificationRecord``
    the *gate*. Rehearsal-graded exercises are never counted, the two controls
    no exercise can demonstrate must arrive as retained evidence records, and
    the resulting record is the only thing ``remediation.executor`` accepts as
    authority for an L4 mutation.

This module never grants autonomy on its own: a record only exists once
``scripts/certify_l4_scope.py`` has been run over real graded exercises and a
real evidence registry by a human who signs it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from remediation.catalog import AutonomyLevel, Runbook
from remediation.policy import ActionRequest, ServiceAutonomy
from resilience.exercises import ExerciseKind, ExerciseResult, certification_from_exercises
from resilience.policy import AutonomyCertification
from resilience.scope import CertificationScope

if TYPE_CHECKING:  # pragma: no cover - typing only; ``validation`` is not shipped.
    from validation.evidence_records import EvidenceRecord


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


# --- the scoped L4 gate ------------------------------------------------------

#: The nine mandatory evidence items of ``architecture/l4-certification.md``,
#: in the order the document lists them.
MANDATORY_L4_EVIDENCE: tuple[str, ...] = (
    "rollback-exercised",
    "kill-switch-exercised",
    "independent-verification",
    "security-review",
    "error-budget-enforced",
    "policy-fail-closed",
    "audit-fail-closed",
    "blast-radius-within-budget",
    "minimum-successful-exercises",
)

#: The doc gives no number, so the number is the existing one: the reference
#: suite's full set of L4 exercise kinds must each have succeeded.
MIN_SUCCESSFUL_EXERCISES: int = len(L4_REQUIRED_KINDS)

#: Mandatory items that map one-to-one onto an exercise kind.
EXERCISE_BACKED_CONTROLS: dict[ExerciseKind, str] = {
    ExerciseKind.ROLLBACK: "rollback-exercised",
    ExerciseKind.KILL_SWITCH: "kill-switch-exercised",
    ExerciseKind.ERROR_BUDGET_EXHAUSTED: "error-budget-enforced",
    ExerciseKind.POLICY_OUTAGE: "policy-fail-closed",
    ExerciseKind.AUDIT_OUTAGE: "audit-fail-closed",
}

#: Mandatory items no exercise can demonstrate. They must arrive as retained
#: evidence records: a human reviewed something and signed for it.
ATTESTED_CONTROLS: tuple[str, ...] = ("independent-verification", "security-review")

#: The evidence-registry decision an attesting record must carry
#: (``validation.evidence_records.DECISIONS``).
L4_EVIDENCE_DECISION = "l4-promotion"

#: ``ExerciseResult.evidence_grade`` for a simulated run (Stage 5). A rehearsal
#: is a rehearsal; it is never certification evidence.
REHEARSAL_GRADE = "rehearsal"

#: ``basis`` values an attesting evidence record may not carry: a simulation
#: cannot attest that a human reviewed something.
NON_ATTESTING_BASES: frozenset[str] = frozenset({"modeled"})

#: Prefix on every refusal this gate produces, so a refusal always names its check.
CERTIFICATION_CHECK = "l4-certification"


@dataclass(frozen=True)
class Eligibility:
    """Whether one scope may be certified, and precisely what is absent."""

    eligible: bool
    missing: tuple[str, ...]
    counted_exercises: int = 0
    rejected_rehearsals: int = 0
    exercises_digest: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class L4CertificationRecord:
    """One signed certification for one scope. The execution path's only authority."""

    scope: CertificationScope
    scope_hash: str
    inputs_hash: str
    exercises_digest: str
    issued_on: str
    expires_on: str
    issued_by: str
    evidence_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.canonical(),
            "scope_hash": self.scope_hash,
            "inputs_hash": self.inputs_hash,
            "exercises_digest": self.exercises_digest,
            "issued_on": self.issued_on,
            "expires_on": self.expires_on,
            "issued_by": self.issued_by,
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "L4CertificationRecord":
        scope = payload["scope"]
        return cls(
            scope=CertificationScope(
                service=str(scope["service"]),
                environment=str(scope["environment"]),
                runbook_id=str(scope["runbook_id"]),
                blast_radius_budget=int(scope["blast_radius_budget"]),
            ),
            scope_hash=str(payload["scope_hash"]),
            inputs_hash=str(payload["inputs_hash"]),
            exercises_digest=str(payload["exercises_digest"]),
            issued_on=str(payload["issued_on"]),
            expires_on=str(payload["expires_on"]),
            issued_by=str(payload["issued_by"]),
            evidence_ids=tuple(str(item) for item in payload.get("evidence_ids", ())),
        )


def _attests(record: "EvidenceRecord", *, scope: CertificationScope, control: str) -> bool:
    if str(getattr(record, "decision", "")) != L4_EVIDENCE_DECISION:
        return False
    if str(getattr(record, "scope", "")).strip() != scope.evidence_scope():
        return False
    if str(getattr(record, "basis", "")).strip().lower() in NON_ATTESTING_BASES:
        return False
    return control in str(getattr(record, "claim", "")).lower()


def evaluate_l4_eligibility(
    scope: CertificationScope,
    exercises: Sequence[ExerciseResult],
    evidence_records: Sequence["EvidenceRecord"],
    now: datetime,
) -> Eligibility:
    """Decide whether one scope meets every mandatory item in the L4 design doc.

    ``now`` is accepted for symmetry with the record it feeds and is not used to
    age exercises out: the retention window is a reviewed decision recorded in
    the evidence registry, not something this function may invent.
    """

    relevant = tuple(
        e
        for e in exercises
        if e.service == scope.service
        and e.environment == scope.environment
        and e.runbook_id == scope.runbook_id
    )
    # The grade is the whole point: Stage 5's simulated suite writes
    # ``rehearsal`` and a rehearsal must never reach a certification decision.
    graded = tuple(
        e for e in relevant if str(e.evidence_grade).strip().lower() != REHEARSAL_GRADE
    )
    rejected = len(relevant) - len(graded)
    passed = tuple(e for e in graded if e.passed)
    failed = tuple(e for e in graded if not e.passed)
    passed_kinds = {e.kind for e in passed}

    satisfied: dict[str, bool] = {}
    for kind, control in EXERCISE_BACKED_CONTROLS.items():
        satisfied[control] = kind in passed_kinds
    for control in ATTESTED_CONTROLS:
        satisfied[control] = any(
            _attests(record, scope=scope, control=control) for record in evidence_records
        )
    satisfied["blast-radius-within-budget"] = all(
        e.observed_blast_radius <= scope.blast_radius_budget for e in passed
    )
    satisfied["minimum-successful-exercises"] = len(passed) >= MIN_SUCCESSFUL_EXERCISES

    missing = [name for name in MANDATORY_L4_EVIDENCE if not satisfied.get(name, False)]
    if failed:
        missing.append("failed-exercise-present")
    if any(not str(e.evidence_ref).strip() for e in passed):
        missing.append("missing-evidence-reference")
    if rejected:
        missing.append("rehearsal-graded-exercises-excluded")

    evidence_ids = tuple(sorted({
        str(getattr(record, "evidence_id", ""))
        for record in evidence_records
        for control in ATTESTED_CONTROLS
        if _attests(record, scope=scope, control=control)
    }))
    return Eligibility(
        eligible=not missing,
        missing=tuple(missing),
        counted_exercises=len(passed),
        rejected_rehearsals=rejected,
        exercises_digest=_digest(passed),
        evidence_ids=evidence_ids,
    )


def _parse_instant(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def certification_refusal(
    record: L4CertificationRecord | None,
    *,
    scope_hash: str,
    inputs_hash: str,
    now: datetime,
) -> str | None:
    """Return why this record may not authorise this request, or ``None`` if it may.

    Precedence is fixed so a refusal reason is deterministic: exists, unexpired,
    right scope, unchanged material inputs.
    """

    if record is None:
        return f"{CERTIFICATION_CHECK}: no certification record for this L4 scope"
    expires = _parse_instant(record.expires_on)
    if expires is None:
        return f"{CERTIFICATION_CHECK}: record expires_on is not a readable timestamp"
    if expires <= now:
        return f"{CERTIFICATION_CHECK}: certification expired on {record.expires_on}"
    if record.scope_hash != scope_hash:
        return (
            f"{CERTIFICATION_CHECK}: record scope_hash does not match the requested "
            "service/environment/runbook/blast-radius scope"
        )
    if record.inputs_hash != inputs_hash:
        return (
            f"{CERTIFICATION_CHECK}: material inputs changed since certification; "
            "recertification is required"
        )
    return None


def certification_scope_for(
    *, policy: ServiceAutonomy, request: ActionRequest, runbook: Runbook
) -> CertificationScope:
    """The scope a request is asking to act within.

    The budget is the *service policy's* bounded blast radius, not the radius of
    this particular request: a certification authorises a budget, and a request
    that fits inside it is covered by the same certification.
    """

    return CertificationScope(
        service=request.service,
        environment=request.environment,
        runbook_id=runbook.id,
        blast_radius_budget=policy.max_blast_radius,
    )


def material_inputs_hash_for(
    scope: CertificationScope, runbook: Runbook, *, policy_bundle_version: str
) -> str:
    """The current material-inputs hash for a scope.

    Both the execution gate and ``scripts/certify_l4_scope.py`` call this, so the
    definition of "material" cannot drift between certifying and enforcing.
    """

    return scope.material_inputs_hash(
        runbook_definition=runbook,
        policy_bundle_version=policy_bundle_version,
        verification_signal=runbook.verify_signal,
        dependencies=runbook.preconditions,
    )
