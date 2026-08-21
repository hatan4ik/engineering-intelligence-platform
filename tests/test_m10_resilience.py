from resilience.policy import AutonomyCertification, PlatformHealth, degraded_mode


def test_policy_or_audit_outage_forces_read_only():
    assert degraded_mode(PlatformHealth(True, True, False, True)) == "read-only"
    assert degraded_mode(PlatformHealth(True, True, True, False)) == "read-only"


def test_observability_outage_disables_automated_mutation():
    assert degraded_mode(PlatformHealth(True, False, True, True)) == "recommend-only"


def test_l4_requires_all_certification_controls():
    cert = AutonomyCertification(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        max_blast_radius=3,
        rollback_tested=True,
        kill_switch_tested=True,
        verification_independent=True,
        security_reviewed=True,
    )
    assert cert.l4_eligible
    unsafe = AutonomyCertification(
        service="payments",
        environment="prod",
        runbook_id="aks.rollout.undo",
        max_blast_radius=3,
        rollback_tested=False,
        kill_switch_tested=True,
        verification_independent=True,
        security_reviewed=True,
    )
    assert not unsafe.l4_eligible
