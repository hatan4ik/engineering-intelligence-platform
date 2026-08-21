from resilience.policy import AutonomyCertification, PlatformHealth, degraded_mode


def test_policy_or_audit_outage_forces_read_only():
    assert degraded_mode(PlatformHealth(True, True, False, True)) == "read-only"
    assert degraded_mode(PlatformHealth(True, True, True, False)) == "read-only"


def test_observability_outage_disables_automated_mutation():
    assert degraded_mode(PlatformHealth(True, False, True, True)) == "recommend-only"


def certified(**overrides):
    values = dict(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        max_blast_radius=3,
        rollback_tested=True,
        kill_switch_tested=True,
        verification_independent=True,
        security_reviewed=True,
        error_budget_enforced=True,
        policy_fail_closed_tested=True,
        audit_fail_closed_tested=True,
        successful_exercises=7,
        minimum_exercises=3,
    )
    values.update(overrides)
    return AutonomyCertification(**values)


def test_l4_requires_all_certification_controls_and_exercises():
    assert certified().l4_eligible
    unsafe = certified(rollback_tested=False)
    assert not unsafe.l4_eligible
    assert "rollback-tested" in unsafe.missing_controls
    insufficient = certified(successful_exercises=2)
    assert not insufficient.l4_eligible
    assert "minimum-exercises" in insufficient.missing_controls
