from __future__ import annotations

from dataclasses import dataclass

from feedback.store import FeedbackEvent, FeedbackOutcome
from intelligence.risk_calibration import (
    DEFAULT_HIGH_THRESHOLD,
    RiskCalibration,
    ScoredOutcome,
    calibrate_high_risk_threshold,
)


@dataclass(frozen=True)
class ServiceRiskProfile:
    service: str
    calibration: RiskCalibration
    source: str


def scored_outcomes_from_feedback(events: tuple[FeedbackEvent, ...]) -> list[ScoredOutcome]:
    outcomes: list[ScoredOutcome] = []
    for event in events:
        if event.capability != "predictive-risk":
            continue
        metadata = dict(event.metadata or {})
        raw_score = metadata.get("risk_score")
        if raw_score is None:
            continue
        try:
            score = int(raw_score)
        except ValueError:
            continue
        if score < 0 or score > 100:
            continue
        if event.outcome == FeedbackOutcome.INCORRECT:
            failed = True
        elif event.outcome == FeedbackOutcome.CORRECT:
            failed = False
        else:
            continue
        outcomes.append(ScoredOutcome(score=score, failed=failed, service=event.service))
    return outcomes


def calibrate_service_profile(
    *,
    service: str,
    events: tuple[FeedbackEvent, ...],
    global_default: int = DEFAULT_HIGH_THRESHOLD,
    min_service_samples: int = 20,
    min_service_failures: int = 4,
) -> ServiceRiskProfile:
    all_outcomes = scored_outcomes_from_feedback(events)
    service_outcomes = [item for item in all_outcomes if item.service == service]

    service_calibration = calibrate_high_risk_threshold(
        service_outcomes,
        default_threshold=global_default,
        min_samples=min_service_samples,
        min_failures=min_service_failures,
    )
    if service_calibration.changed_from_default or (
        service_calibration.sample_size >= min_service_samples
        and service_calibration.failed_samples >= min_service_failures
    ):
        return ServiceRiskProfile(service, service_calibration, "service-history")

    global_calibration = calibrate_high_risk_threshold(
        all_outcomes,
        default_threshold=global_default,
    )
    if global_calibration.changed_from_default:
        evidence = global_calibration.evidence + (
            f"service {service} lacks sufficient independent evidence; using global calibration",
        )
        fallback = RiskCalibration(
            high_threshold=global_calibration.high_threshold,
            sample_size=service_calibration.sample_size,
            failed_samples=service_calibration.failed_samples,
            metrics=service_calibration.metrics,
            confidence=min(global_calibration.confidence, 0.70),
            evidence=evidence,
            changed_from_default=global_calibration.high_threshold != global_default,
        )
        return ServiceRiskProfile(service, fallback, "global-history")

    return ServiceRiskProfile(service, service_calibration, "safe-default")
