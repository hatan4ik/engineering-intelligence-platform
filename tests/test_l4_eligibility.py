"""L4 eligibility: every mandatory item in architecture/l4-certification.md, and no rehearsals.

Stage 5 grades a simulated exercise ``rehearsal``. Nothing read that grade, so a
rehearsal counted exactly as much as a production exercise. These tests pin the
rule that makes the grade matter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from resilience.certification import (
    ATTESTED_CONTROLS,
    L4_EVIDENCE_DECISION,
    MANDATORY_L4_EVIDENCE,
    MIN_SUCCESSFUL_EXERCISES,
    evaluate_l4_eligibility,
)
from resilience.exercises import ExerciseKind, ExerciseResult
from resilience.scope import CertificationScope
from validation.evidence_records import validate_record


NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
SCOPE = CertificationScope(
    service="payments", environment="prod", runbook_id="aks.rollout.undo", blast_radius_budget=3
)


def exercise(kind, *, passed=True, radius=2, grade="cluster-exercise", ref=None) -> ExerciseResult:
    return ExerciseResult(
        kind=kind,
        passed=passed,
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        observed_blast_radius=radius,
        evidence_ref=ref if ref is not None else f"https://ci/{kind.value}",
        evidence_grade=grade,
    )


def full_exercises(**kwargs) -> tuple[ExerciseResult, ...]:
    return tuple(exercise(kind, **kwargs) for kind in ExerciseKind)


def evidence(control: str, *, basis="measured", scope="payments/prod/aks.rollout.undo"):
    return validate_record({
        "evidence_id": f"l4-{control}",
        "scope": scope,
        "change": "L4 promotion for the payments rollout-undo scope",
        "claim": f"{control} completed for this scope",
        "controls": [control],
        "method": "independent review",
        "result": "pass",
        "independence": "reviewed by security, not by the platform team",
        "artifacts": ["https://example.invalid/artifact"],
        "approval": "security@example.invalid",
        "basis": basis,
        "decision": L4_EVIDENCE_DECISION,
        "source_run_url": "https://example.invalid/run/1",
    })


def full_evidence():
    return tuple(evidence(control) for control in ATTESTED_CONTROLS)


def test_a_complete_graded_scope_is_eligible():
    result = evaluate_l4_eligibility(SCOPE, full_exercises(), full_evidence(), NOW)
    assert result.eligible
    assert result.missing == ()
    assert result.counted_exercises == len(ExerciseKind)


def test_the_mandatory_list_is_the_one_in_the_architecture_doc():
    assert MANDATORY_L4_EVIDENCE == (
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
    assert MIN_SUCCESSFUL_EXERCISES == 7


@pytest.mark.parametrize(
    "kind,control",
    [
        (ExerciseKind.ROLLBACK, "rollback-exercised"),
        (ExerciseKind.KILL_SWITCH, "kill-switch-exercised"),
        (ExerciseKind.ERROR_BUDGET_EXHAUSTED, "error-budget-enforced"),
        (ExerciseKind.POLICY_OUTAGE, "policy-fail-closed"),
        (ExerciseKind.AUDIT_OUTAGE, "audit-fail-closed"),
    ],
)
def test_each_missing_exercise_names_its_own_mandatory_item(kind, control):
    exercises = tuple(e for e in full_exercises() if e.kind is not kind)
    result = evaluate_l4_eligibility(SCOPE, exercises, full_evidence(), NOW)
    assert not result.eligible
    assert control in result.missing
    assert "minimum-successful-exercises" in result.missing


@pytest.mark.parametrize("control", ATTESTED_CONTROLS)
def test_each_attested_control_needs_a_retained_evidence_record(control):
    records = tuple(r for r in full_evidence() if control not in r.claim)
    result = evaluate_l4_eligibility(SCOPE, full_exercises(), records, NOW)
    assert not result.eligible
    assert control in result.missing


def test_a_modeled_evidence_record_does_not_attest_anything():
    records = tuple(evidence(control, basis="modeled") for control in ATTESTED_CONTROLS)
    result = evaluate_l4_eligibility(SCOPE, full_exercises(), records, NOW)
    assert not result.eligible
    assert set(ATTESTED_CONTROLS) <= set(result.missing)


def test_an_evidence_record_for_another_scope_does_not_attest_this_one():
    records = tuple(
        evidence(control, scope="payments/stage/aks.rollout.undo") for control in ATTESTED_CONTROLS
    )
    result = evaluate_l4_eligibility(SCOPE, full_exercises(), records, NOW)
    assert set(ATTESTED_CONTROLS) <= set(result.missing)


def test_rehearsal_graded_exercises_are_never_counted():
    result = evaluate_l4_eligibility(SCOPE, full_exercises(grade="rehearsal"), full_evidence(), NOW)
    assert not result.eligible
    assert result.counted_exercises == 0
    assert result.rejected_rehearsals == len(ExerciseKind)
    assert "rehearsal-graded-exercises-excluded" in result.missing
    # Every exercise-backed mandatory item is missing because no exercise counted.
    assert "rollback-exercised" in result.missing
    assert "minimum-successful-exercises" in result.missing


def test_a_blast_radius_over_the_budget_is_not_within_the_certified_budget():
    exercises = full_exercises(radius=SCOPE.blast_radius_budget + 1)
    result = evaluate_l4_eligibility(SCOPE, exercises, full_evidence(), NOW)
    assert not result.eligible
    assert "blast-radius-within-budget" in result.missing


def test_a_failed_exercise_blocks_eligibility():
    exercises = (*full_exercises(), exercise(ExerciseKind.ROLLBACK, passed=False))
    result = evaluate_l4_eligibility(SCOPE, exercises, full_evidence(), NOW)
    assert not result.eligible
    assert "failed-exercise-present" in result.missing


def test_a_counted_exercise_without_a_retained_reference_blocks_eligibility():
    exercises = tuple(
        exercise(kind, ref="" if kind is ExerciseKind.ROLLBACK else None) for kind in ExerciseKind
    )
    result = evaluate_l4_eligibility(SCOPE, exercises, full_evidence(), NOW)
    assert not result.eligible
    assert "missing-evidence-reference" in result.missing


def test_exercises_from_another_scope_are_ignored():
    other = ExerciseResult(
        kind=ExerciseKind.ROLLBACK, passed=True, service="billing", environment="prod",
        runbook_id="aks.rollout.undo", observed_blast_radius=99, evidence_ref="https://ci/x",
        evidence_grade="cluster-exercise",
    )
    result = evaluate_l4_eligibility(SCOPE, (*full_exercises(), other), full_evidence(), NOW)
    assert result.eligible


def test_an_empty_scope_is_missing_every_mandatory_item():
    result = evaluate_l4_eligibility(SCOPE, (), (), NOW)
    assert not result.eligible
    assert set(MANDATORY_L4_EVIDENCE) - {"blast-radius-within-budget"} <= set(result.missing)
