from resilience.certification import CertificationReport
from validation.production_readiness import (
    REQUIRED_KEYS,
    ProductionReadinessReport,
    ReadinessArea,
    ReadinessEvidence,
    evaluate_production_readiness,
)


def l3_report(eligible: bool) -> CertificationReport:
    return CertificationReport(
        service="payments",
        environment="prod",
        runbook_id="restart-deployment",
        generated_at="2026-08-23T00:00:00+00:00",
        evidence_digest="sha256:test",
        passed_kinds=(),
        failed_kinds=(),
        l3_eligible=eligible,
        l4_eligible=False,
        missing_l3_controls=() if eligible else ("exercise:rollback",),
        missing_l4_controls=("exercise:error-budget-exhausted",),
    )


def complete_evidence():
    area = ReadinessArea.RELIABILITY
    return tuple(
        ReadinessEvidence(key, area, True, f"evidence://{key}")
        for key in REQUIRED_KEYS
    )


def test_reference_implementation_cannot_claim_production_ready_without_real_evidence():
    report = evaluate_production_readiness((), l3_report=None, soak_hours=0.0)
    assert report.ready is False
    assert "real-source-integration" in report.missing
    assert "l3-certification-evidence" in report.missing
    assert "soak-hours<168" in report.missing


def test_complete_evidence_still_requires_operational_slo_metrics():
    report = evaluate_production_readiness(
        complete_evidence(),
        l3_report=l3_report(True),
        soak_hours=168,
        observed_metrics={"control_plane_success_rate": 0.95, "audit_write_success_rate": 1.0},
    )
    assert report.ready is False
    assert "control-plane-success-rate>=0.99" in report.missing


def test_production_ready_only_when_all_evidence_is_present():
    report: ProductionReadinessReport = evaluate_production_readiness(
        complete_evidence(),
        l3_report=l3_report(True),
        soak_hours=240,
        observed_metrics={"control_plane_success_rate": 0.995, "audit_write_success_rate": 1.0},
    )
    assert report.ready is True
    assert report.score == 1.0
    assert "sha256:test" in report.evidence_refs
