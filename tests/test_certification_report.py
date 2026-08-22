from resilience.certification import build_certification_report
from resilience.exercises import ExerciseKind, ExerciseResult


def exercise(kind, *, passed=True, radius=2, ref=None):
    return ExerciseResult(
        kind=kind,
        passed=passed,
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        observed_blast_radius=radius,
        evidence_ref=ref or f"evidence://{kind.value}",
    )


def test_l3_requires_complete_failure_and_safety_exercise_evidence():
    exercises = tuple(exercise(k) for k in (
        ExerciseKind.SUCCESSFUL_REMEDIATION,
        ExerciseKind.VERIFICATION_FAILURE,
        ExerciseKind.ROLLBACK,
        ExerciseKind.KILL_SWITCH,
        ExerciseKind.POLICY_OUTAGE,
        ExerciseKind.AUDIT_OUTAGE,
    ))
    report = build_certification_report(
        service="payments", environment="prod", runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3, security_reviewed=True,
        verification_independent=True, exercises=exercises,
        generated_at="2026-08-22T00:00:00+00:00",
    )
    assert report.l3_eligible
    assert not report.l4_eligible
    assert "exercise:error_budget_exhausted" in report.missing_l4_controls
    assert report.evidence_digest.startswith("sha256:")


def test_l4_requires_error_budget_exercise_and_no_failed_exercises():
    exercises = tuple(exercise(k) for k in ExerciseKind)
    report = build_certification_report(
        service="payments", environment="prod", runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3, security_reviewed=True,
        verification_independent=True, exercises=exercises,
    )
    assert report.l3_eligible
    assert report.l4_eligible
    assert report.missing_l4_controls == ()


def test_failed_or_overblast_exercise_blocks_certification():
    exercises = tuple(exercise(k) for k in ExerciseKind) + (
        exercise(ExerciseKind.ROLLBACK, passed=False, radius=9, ref="chaos://failed-rollback"),
    )
    report = build_certification_report(
        service="payments", environment="prod", runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3, security_reviewed=True,
        verification_independent=True, exercises=exercises,
    )
    assert not report.l3_eligible
    assert not report.l4_eligible
    assert "failed-exercise-present" in report.missing_l3_controls
