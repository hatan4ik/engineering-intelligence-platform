from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident, utc
from intelligence.slo import SLOContext, remediation_urgency


def test_incident_analysis_separates_facts_and_inference():
    events = [
        EvidenceEvent("deploy-1", EvidenceKind.DEPLOYMENT, "payments", utc("2026-08-21T10:00:00Z"), "release abc123", "ado"),
        EvidenceEvent("oom-1", EvidenceKind.K8S_EVENT, "payments", utc("2026-08-21T10:04:00Z"), "OOMKilled replica-1", "aks", severity=4),
        EvidenceEvent("oom-2", EvidenceKind.LOG, "payments", utc("2026-08-21T10:05:00Z"), "memory allocation failure", "app", severity=4),
    ]
    analysis = analyze_incident(events, service="payments")
    assert [e.id for e in analysis.timeline] == ["deploy-1", "oom-1", "oom-2"]
    assert analysis.hypotheses
    deploy_h = next(h for h in analysis.hypotheses if "deployment" in h.title.lower())
    assert "deploy-1" in deploy_h.evidence_ids
    assert deploy_h.facts
    assert deploy_h.inferences


def test_slo_context_sets_critical_urgency_when_budget_exhausted():
    ctx = SLOContext(target=0.999, current=0.992, error_budget_remaining=0.0)
    assert ctx.breached
    assert remediation_urgency(ctx) == "critical"
