from feedback.store import FeedbackEvent, FeedbackOutcome
from intelligence.service_risk_profile import calibrate_service_profile, scored_outcomes_from_feedback


def event(i: int, *, service: str, score: int, failed: bool) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=f"e-{service}-{i}",
        capability="predictive-risk",
        subject_id=f"d-{i}",
        outcome=FeedbackOutcome.INCORRECT if failed else FeedbackOutcome.CORRECT,
        service=service,
        metadata={"risk_score": str(score)},
    )


def test_feedback_converts_to_scored_outcomes():
    events = (
        event(1, service="payments", score=70, failed=True),
        event(2, service="payments", score=20, failed=False),
    )
    outcomes = scored_outcomes_from_feedback(events)
    assert [(o.score, o.failed, o.service) for o in outcomes] == [
        (70, True, "payments"),
        (20, False, "payments"),
    ]


def test_service_with_enough_history_uses_service_profile():
    events = tuple(
        event(i, service="payments", score=(65 if i < 8 else 25), failed=(i < 8))
        for i in range(24)
    )
    profile = calibrate_service_profile(
        service="payments",
        events=events,
        min_service_samples=20,
        min_service_failures=4,
    )
    assert profile.source == "service-history"
    assert profile.calibration.sample_size == 24
    assert 40 <= profile.calibration.high_threshold <= 75


def test_sparse_service_does_not_overfit():
    sparse = tuple(event(i, service="checkout", score=90, failed=True) for i in range(3))
    profile = calibrate_service_profile(service="checkout", events=sparse)
    assert profile.source == "safe-default"
    assert profile.calibration.high_threshold == 50
    assert profile.calibration.changed_from_default is False
