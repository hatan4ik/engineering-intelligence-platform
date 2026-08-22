from feedback.store import FeedbackEvent, FeedbackOutcome, SqliteFeedbackStore, summarize_feedback
from portal.intelligence_view import (
    ArchitectureHealth,
    IncidentHealth,
    KnowledgeHealth,
    ServiceIntelligenceView,
    to_dict,
)


def test_feedback_store_is_idempotent_and_summarizes_learning_signals(tmp_path):
    store = SqliteFeedbackStore(tmp_path / "feedback.db")
    event = FeedbackEvent("e1", "pr-guardian", "pr:42", FeedbackOutcome.ACCEPTED, service="payments")
    assert store.append(event) is True
    assert store.append(event) is False
    store.append(FeedbackEvent("e2", "pr-guardian", "pr:43", FeedbackOutcome.REJECTED, service="payments"))
    store.append(FeedbackEvent("e3", "incident-intelligence", "inc:7", FeedbackOutcome.CORRECT, service="payments"))

    metrics = summarize_feedback(store.events(service="payments"))
    assert metrics.total == 3
    assert metrics.acceptance_rate == 0.5
    assert metrics.precision == 1.0


def test_service_intelligence_attention_score_surfaces_real_risk():
    view = ServiceIntelligenceView(
        service="payments",
        owner="payments-team",
        tier=1,
        repositories=("acme/payments",),
        dependencies=("identity",),
        impacted_dependents=("checkout",),
        slo_target=0.999,
        slo_current=0.995,
        change_risk_score=80,
        knowledge=KnowledgeHealth(stale=2, conflicts=1, missing_owner=0),
        architecture=ArchitectureHealth(blocking_findings=1, advisory_findings=2),
        incidents=IncidentHealth(active=1, recent_rca_confidence=0.88, impacted_services=("checkout",)),
        feedback=summarize_feedback((
            FeedbackEvent("a", "pr-guardian", "pr:1", FeedbackOutcome.ACCEPTED),
            FeedbackEvent("b", "pr-guardian", "pr:2", FeedbackOutcome.REJECTED),
        )),
        pending_approvals=1,
    )
    payload = to_dict(view)
    assert payload["attention_score"] >= 50
    assert payload["feedback"]["acceptance_rate"] == 0.5
    assert payload["incidents"]["impacted_services"] == ["checkout"]
