from validation.production_readiness import REQUIRED_KEYS, ReadinessArea, ReadinessEvidence, evaluate_production_readiness
from validation.soak import SoakReport
from resilience.certification import CertificationReport


def test_auditable_soak_report_contributes_evidence_and_controls_readiness():
    evidence = tuple(
        ReadinessEvidence(key, ReadinessArea.RELIABILITY, True, f"evidence://{key}")
        for key in REQUIRED_KEYS
    )
    cert = CertificationReport(
        service="payments",
        environment="prod",
        runbook_id="restart-deployment",
        generated_at="2026-08-23T00:00:00+00:00",
        evidence_digest="sha256:l3",
        passed_kinds=(),
        failed_kinds=(),
        l3_eligible=True,
        l4_eligible=False,
        missing_l3_controls=(),
        missing_l4_controls=("exercise:error-budget-exhausted",),
    )
    soak = SoakReport(
        continuous_hours=168.0,
        sample_count=85,
        passed_samples=85,
        failed_samples=0,
        evidence_refs=("artifact://first", "artifact://last"),
        qualifies=True,
    )
    report = evaluate_production_readiness(
        evidence,
        l3_report=cert,
        soak_report=soak,
        observed_metrics={"control_plane_success_rate": 0.999, "audit_write_success_rate": 1.0},
    )
    assert report.ready is True
    assert "artifact://first" in report.evidence_refs
    assert "artifact://last" in report.evidence_refs
