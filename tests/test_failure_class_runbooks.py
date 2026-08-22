from datetime import datetime, timedelta, timezone

from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from remediation.planner import plan_from_incident


def event(i, kind, minutes, summary, severity=4):
    base = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    return EvidenceEvent(i, kind, "payments", base + timedelta(minutes=minutes), summary, "test", severity)


def test_readiness_regression_prefers_specific_rollback_runbook():
    analysis = analyze_incident([
        event("d1", EvidenceKind.DEPLOYMENT, 0, "release v2", 1),
        event("a1", EvidenceKind.ALERT, 2, "readiness probe failed"),
    ], service="payments")
    plan = plan_from_incident(analysis)
    assert plan is not None
    assert plan.runbook_id == "aks.rollback.readiness"


def test_crashloop_prefers_bounded_restart_over_generic_deployment_rollback():
    analysis = analyze_incident([
        event("d1", EvidenceKind.DEPLOYMENT, 0, "release v2", 1),
        event("k1", EvidenceKind.K8S_EVENT, 1, "CrashLoopBackOff for container api"),
    ], service="payments")
    plan = plan_from_incident(analysis)
    assert plan is not None
    assert plan.runbook_id == "aks.restart.crashloop"


def test_oom_does_not_silently_change_memory_policy():
    analysis = analyze_incident([
        event("k1", EvidenceKind.K8S_EVENT, 0, "OOMKilled container api"),
        event("m1", EvidenceKind.ALERT, 1, "memory pressure sustained"),
    ], service="payments")
    plan = plan_from_incident(analysis)
    assert plan is not None
    assert plan.runbook_id == "aks.restart.oom"
