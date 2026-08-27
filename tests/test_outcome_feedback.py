from feedback.outcome_capture import OutcomeFeedbackRecorder, normalize_github_pr_outcome
from feedback.store import FeedbackOutcome, SqliteFeedbackStore


def test_pr_outcome_capture_is_idempotent(tmp_path):
    store = SqliteFeedbackStore(tmp_path / "feedback.db")
    recorder = OutcomeFeedbackRecorder(store)
    first = recorder.record_pr_closed(
        repository="acme/platform", pr_number=42, service="payments", merged=True, risk_score=61
    )
    second = recorder.record_pr_closed(
        repository="acme/platform", pr_number=42, service="payments", merged=True, risk_score=61
    )
    assert first.inserted is True
    assert second.inserted is False
    event = store.events(capability="pr-guardian")[0]
    assert event.outcome == FeedbackOutcome.ACCEPTED
    assert event.metadata["risk_score"] == "61"


def test_deployment_and_incident_results_become_learning_evidence(tmp_path):
    store = SqliteFeedbackStore(tmp_path / "feedback.db")
    recorder = OutcomeFeedbackRecorder(store)
    recorder.record_deployment(
        deployment_id="dep-9",
        service="payments",
        environment="prod",
        succeeded=False,
        risk_score=78,
    )
    recorder.record_incident_rca(
        incident_id="inc-1",
        service="payments",
        hypothesis_id="deployment-regression",
        confirmed=True,
        actor="oncall@example.com",
    )
    risk_event = store.events(capability="predictive-risk")[0]
    rca_event = store.events(capability="incident-intelligence")[0]
    assert risk_event.outcome == FeedbackOutcome.INCORRECT
    assert risk_event.metadata["risk_score"] == "78"
    assert rca_event.outcome == FeedbackOutcome.CORRECT
    assert rca_event.actor == "oncall@example.com"


def test_github_terminal_outcome_normalization():
    payload = {
        "action": "closed",
        "number": 7,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {"merged": True},
    }
    assert normalize_github_pr_outcome(payload) == {
        "repository": "acme/platform",
        "pr_number": 7,
        "merged": True,
        # Reviewer dispositions now travel with the terminal outcome; an
        # unlabelled pull request is explicitly "not-reviewed", never assumed.
        "risk_signal": "not-reviewed",
        "utility_signal": "not-reviewed",
    }
    assert normalize_github_pr_outcome({"action": "synchronize"}) is None
