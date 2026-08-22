from intelligence.risk_calibration import (
    DEFAULT_HIGH_THRESHOLD,
    MIN_HIGH_THRESHOLD,
    ScoredOutcome,
    calibrate_high_risk_threshold,
    classify_with_calibration,
)


def test_insufficient_samples_never_change_release_threshold():
    outcomes = [ScoredOutcome(80, True), ScoredOutcome(10, False)]
    result = calibrate_high_risk_threshold(outcomes)
    assert result.high_threshold == DEFAULT_HIGH_THRESHOLD
    assert result.changed_from_default is False
    assert result.confidence < 0.5


def test_calibration_prefers_failure_recall_and_respects_safety_floor():
    outcomes = []
    # Failures cluster above 45, successes mainly below 40. This should allow a
    # bounded threshold adjustment but can never lower below the safety floor.
    for score in (45, 50, 55, 60, 65, 70, 75, 80):
        outcomes.append(ScoredOutcome(score, True))
    for score in (5, 10, 15, 20, 25, 30, 35, 38, 39, 42, 44, 46, 48, 52,
                  8, 12, 18, 22, 28, 32, 34, 36, 37, 40, 41, 43, 47, 49):
        outcomes.append(ScoredOutcome(score, False))

    result = calibrate_high_risk_threshold(outcomes, min_samples=30, min_failures=5)
    assert result.high_threshold >= MIN_HIGH_THRESHOLD
    assert result.metrics is not None
    assert (result.metrics.recall or 0) >= 0.80
    assert (result.metrics.precision or 0) >= 0.50
    assert result.confidence >= 0.5


def test_no_safe_candidate_keeps_default_instead_of_optimizing_for_fewer_gates():
    outcomes = []
    # Failures are deliberately indistinguishable from successes across scores.
    for i in range(20):
        outcomes.append(ScoredOutcome(10 + (i % 5) * 15, i % 2 == 0))
        outcomes.append(ScoredOutcome(12 + (i % 5) * 15, i % 2 == 1))
    result = calibrate_high_risk_threshold(
        outcomes,
        min_samples=30,
        min_failures=5,
        min_precision=0.9,
        min_recall=0.9,
    )
    assert result.high_threshold == DEFAULT_HIGH_THRESHOLD
    assert result.changed_from_default is False
    assert "default threshold retained" in result.evidence[-1]


def test_classification_uses_calibrated_high_threshold_but_keeps_critical_floor():
    outcomes = [ScoredOutcome(80, True)] * 10 + [ScoredOutcome(20, False)] * 25
    calibration = calibrate_high_risk_threshold(outcomes, min_samples=30, min_failures=5)
    assert classify_with_calibration(100, calibration) == "critical"
    assert classify_with_calibration(calibration.high_threshold, calibration) == "high"
