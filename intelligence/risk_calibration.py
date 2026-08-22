from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ScoredOutcome:
    score: int
    failed: bool
    service: str | None = None


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def precision(self) -> float | None:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else None

    @property
    def false_negative_rate(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return self.false_negative / denominator if denominator else None


@dataclass(frozen=True)
class RiskCalibration:
    high_threshold: int
    sample_size: int
    failed_samples: int
    metrics: ThresholdMetrics | None
    confidence: float
    evidence: tuple[str, ...]
    changed_from_default: bool


DEFAULT_HIGH_THRESHOLD = 50
MIN_HIGH_THRESHOLD = 40
MAX_HIGH_THRESHOLD = 75


def evaluate_threshold(outcomes: Iterable[ScoredOutcome], threshold: int) -> ThresholdMetrics:
    tp = fp = tn = fn = 0
    for outcome in outcomes:
        predicted_high = outcome.score >= threshold
        if predicted_high and outcome.failed:
            tp += 1
        elif predicted_high and not outcome.failed:
            fp += 1
        elif not predicted_high and not outcome.failed:
            tn += 1
        else:
            fn += 1
    return ThresholdMetrics(threshold, tp, fp, tn, fn)


def calibrate_high_risk_threshold(
    outcomes: list[ScoredOutcome],
    *,
    default_threshold: int = DEFAULT_HIGH_THRESHOLD,
    min_samples: int = 30,
    min_failures: int = 5,
    min_precision: float = 0.50,
    min_recall: float = 0.80,
) -> RiskCalibration:
    if not outcomes:
        return RiskCalibration(
            default_threshold, 0, 0, None, 0.0,
            ("no observed outcomes; default threshold retained",), False,
        )
    for outcome in outcomes:
        if outcome.score < 0 or outcome.score > 100:
            raise ValueError("risk scores must be between 0 and 100")

    sample_size = len(outcomes)
    failures = sum(1 for o in outcomes if o.failed)
    if sample_size < min_samples or failures < min_failures:
        evidence = (
            f"insufficient calibration evidence: {sample_size} samples / {failures} failures",
            f"requires at least {min_samples} samples / {min_failures} failures",
            "default threshold retained",
        )
        return RiskCalibration(
            default_threshold,
            sample_size,
            failures,
            evaluate_threshold(outcomes, default_threshold),
            min(0.49, sample_size / max(1, min_samples) * 0.49),
            evidence,
            False,
        )

    candidates: list[tuple[int, ThresholdMetrics]] = []
    for threshold in range(MIN_HIGH_THRESHOLD, MAX_HIGH_THRESHOLD + 1, 5):
        metrics = evaluate_threshold(outcomes, threshold)
        precision = metrics.precision or 0.0
        recall = metrics.recall or 0.0
        if precision >= min_precision and recall >= min_recall:
            candidates.append((threshold, metrics))

    if not candidates:
        metrics = evaluate_threshold(outcomes, default_threshold)
        return RiskCalibration(
            default_threshold,
            sample_size,
            failures,
            metrics,
            min(0.85, 0.5 + sample_size / 500.0),
            (
                "no candidate threshold satisfied precision/recall safety constraints",
                "default threshold retained",
            ),
            False,
        )

    # Prefer lowest false negatives, then highest precision, then the threshold
    # closest to the default. Never optimize merely for fewer review gates.
    def rank(item: tuple[int, ThresholdMetrics]) -> tuple[float, float, int]:
        threshold, metrics = item
        fnr = metrics.false_negative_rate if metrics.false_negative_rate is not None else 1.0
        precision = metrics.precision or 0.0
        return (fnr, -precision, abs(threshold - default_threshold))

    selected_threshold, selected = min(candidates, key=rank)
    confidence = min(0.95, 0.55 + min(sample_size, 200) / 500.0 + min(failures, 20) / 100.0)
    evidence = (
        f"calibrated from {sample_size} observed changes including {failures} failures",
        f"selected threshold {selected_threshold}: precision={(selected.precision or 0):.2f}, recall={(selected.recall or 0):.2f}",
        f"threshold constrained to safety range {MIN_HIGH_THRESHOLD}-{MAX_HIGH_THRESHOLD}",
    )
    return RiskCalibration(
        selected_threshold,
        sample_size,
        failures,
        selected,
        round(confidence, 3),
        evidence,
        selected_threshold != default_threshold,
    )


def classify_with_calibration(score: int, calibration: RiskCalibration) -> str:
    if score < 0 or score > 100:
        raise ValueError("risk score must be between 0 and 100")
    high = calibration.high_threshold
    critical = max(75, high + 25)
    moderate = min(25, max(15, high // 2))
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= moderate:
        return "moderate"
    return "low"
