from resilience.exercises import ExerciseKind, ExerciseResult, certification_from_exercises


def result(kind, *, passed=True, blast=2):
    return ExerciseResult(
        kind=kind,
        passed=passed,
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        observed_blast_radius=blast,
        evidence_ref=f"exercise://{kind.value}",
    )


def full_suite():
    return tuple(
        result(kind)
        for kind in (
            ExerciseKind.SUCCESSFUL_REMEDIATION,
            ExerciseKind.ROLLBACK,
            ExerciseKind.KILL_SWITCH,
            ExerciseKind.POLICY_OUTAGE,
            ExerciseKind.AUDIT_OUTAGE,
            ExerciseKind.ERROR_BUDGET_EXHAUSTED,
        )
    )


def test_full_exercise_suite_can_certify_bounded_l4():
    cert = certification_from_exercises(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3,
        security_reviewed=True,
        verification_independent=True,
        exercises=full_suite(),
    )
    assert cert.l4_eligible
    assert cert.successful_exercises == 6


def test_missing_fail_closed_exercise_blocks_l4():
    exercises = tuple(e for e in full_suite() if e.kind is not ExerciseKind.AUDIT_OUTAGE)
    cert = certification_from_exercises(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3,
        security_reviewed=True,
        verification_independent=True,
        exercises=exercises,
    )
    assert not cert.l4_eligible
    assert "audit-fail-closed-tested" in cert.missing_controls


def test_observed_blast_radius_above_certification_budget_invalidates_scope():
    exercises = full_suite() + (result(ExerciseKind.ROLLBACK, blast=7),)
    cert = certification_from_exercises(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        certified_max_blast_radius=3,
        security_reviewed=True,
        verification_independent=True,
        exercises=exercises,
    )
    assert not cert.l4_eligible
    assert "bounded-blast-radius" in cert.missing_controls
