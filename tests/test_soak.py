from datetime import datetime, timedelta, timezone

from validation.soak import SoakSample, evaluate_soak


def sample(hour: int, *, passed: bool = True, ref: str | None = None) -> SoakSample:
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return SoakSample(
        observed_at=(base + timedelta(hours=hour)).isoformat(),
        passed=passed,
        evidence_ref=ref if ref is not None else f"artifact://run-{hour}",
    )


def test_168_hours_requires_continuous_passing_evidence():
    samples = tuple(sample(hour) for hour in range(0, 169, 2))
    report = evaluate_soak(samples, minimum_hours=168, maximum_gap_hours=2)
    assert report.continuous_hours == 168.0
    assert report.qualifies is True
    assert report.failed_samples == 0


def test_failed_sample_breaks_soak_window():
    samples = tuple(sample(hour, passed=(hour != 84)) for hour in range(0, 169, 2))
    report = evaluate_soak(samples, minimum_hours=168, maximum_gap_hours=2)
    assert report.qualifies is False
    assert report.continuous_hours < 168
    assert report.failed_samples == 1


def test_large_sampling_gap_breaks_continuity():
    samples = (sample(0), sample(2), sample(10), sample(12))
    report = evaluate_soak(samples, minimum_hours=10, maximum_gap_hours=2)
    assert report.qualifies is False
    assert report.continuous_hours == 2.0


def test_missing_evidence_reference_counts_as_failure():
    report = evaluate_soak((sample(0), sample(2, ref=""), sample(4)), minimum_hours=4)
    assert report.qualifies is False
    assert report.failed_samples == 1
