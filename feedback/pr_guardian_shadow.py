"""Metrics for reviewable PR Guardian shadow-pilot exports.

The report is deliberately conservative.  Its ``decision`` says only whether a
promotion *review* has enough inputs (``advisory-candidate``) or not
(``shadow-only``); ``blocking_authorized`` is always ``False``.  A human
evidence review and the controls in ``PRODUCTION-EVIDENCE.md`` are still needed
before any blocking rule can be proposed, and the ``calibration`` section is a
recommendation that nothing in this codebase applies.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from feedback.store import FeedbackEvent, FeedbackOutcome
from intelligence.risk_calibration import (
    DEFAULT_HIGH_THRESHOLD,
    RiskCalibration,
    calibrate_high_risk_threshold,
)
from intelligence.service_risk_profile import (
    calibrate_service_profile,
    scored_outcomes_from_feedback,
)
from product.pr_guardian_shadow import validate_outcome

CALIBRATION_NOTE = (
    "Threshold changes are reviewed product decisions; this section is a recommendation only."
)

# A reviewer disposition describes whether PR Guardian was *right*, so a
# confirmed risk is a correct capability outcome and a false positive is an
# incorrect one.
_DISPOSITION_OUTCOMES = {
    "confirmed-risk": FeedbackOutcome.CORRECT,
    "false-positive": FeedbackOutcome.INCORRECT,
}
# ``scored_outcomes_from_feedback`` treats an INCORRECT outcome as a failed
# sample — the class a calibrated threshold is tuned to catch.  The report
# states that plainly so a suggested threshold cannot be read in the wrong
# direction.
_FAILURE_DISPOSITIONS = sorted(
    disposition
    for disposition, outcome in _DISPOSITION_OUTCOMES.items()
    if outcome is FeedbackOutcome.INCORRECT
)


def build_shadow_report(outcomes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    records = [validate_outcome(item) for item in outcomes]
    joined = [record for record in records if record["source_observation"] is not None]
    reviewed = [
        record for record in joined
        if record["reviewer_signal"]["risk"] != "not-reviewed"  # type: ignore[index]
    ]
    confirmed = [
        record for record in reviewed
        if record["reviewer_signal"]["risk"] == "confirmed-risk"  # type: ignore[index]
    ]
    useful = sum(
        1 for record in joined
        if record["reviewer_signal"]["utility"] == "useful"  # type: ignore[index]
    )
    not_useful = sum(
        1 for record in joined
        if record["reviewer_signal"]["utility"] == "not-useful"  # type: ignore[index]
    )
    tp = fp = tn = fn = 0
    for record in reviewed:
        source = record["source_observation"]
        assert isinstance(source, Mapping)
        would_block = bool(source["would_block"])
        confirmed_risk = record["reviewer_signal"]["risk"] == "confirmed-risk"  # type: ignore[index]
        if would_block and confirmed_risk:
            tp += 1
        elif would_block:
            fp += 1
        elif confirmed_risk:
            fn += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    utility = _ratio(useful, useful + not_useful)
    promotion_requirements = {
        "minimum_joined_observations": len(joined) >= 30,
        "minimum_reviewer_classifications": len(reviewed) >= 30,
        "minimum_confirmed_risks": len(confirmed) >= 5,
        "minimum_simulated_block_precision": precision is not None and precision >= 0.50,
        "minimum_simulated_block_recall": recall is not None and recall >= 0.80,
    }
    failures = [name for name, complete in promotion_requirements.items() if not complete]
    return {
        "schema_version": 1,
        "kind": "pr-guardian-shadow-report",
        "scope": "offline pilot export only",
        "sample": {
            "closure_records": len(records),
            "joined_observations": len(joined),
            "reviewer_classifications": len(reviewed),
            "confirmed_risks": len(confirmed),
            "utility_responses": useful + not_useful,
        },
        "simulated_block_decision": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
            "precision": precision,
            "recall": recall,
        },
        "utility": {"useful": useful, "not_useful": not_useful, "useful_rate": utility},
        "calibration": _calibration(reviewed),
        "promotion_readiness": {
            "requirements": promotion_requirements,
            "unmet_requirements": failures,
            # No measured result may authorize merge blocking; only a reviewed
            # evidence record under PRODUCTION-EVIDENCE.md can, and that is a
            # human decision made outside this report.
            "blocking_authorized": False,
            "decision": "shadow-only" if failures else "advisory-candidate",
            "next_review": _next_review(records, failures),
        },
        "limitations": [
            "Closure and reviewer labels do not establish post-merge incident or rollback outcomes.",
            "This report is an input to an approved evidence record; it is not production evidence by itself.",
            "No report output can authorize PR Guardian merge blocking.",
        ],
    }


def _next_review(records: Sequence[Mapping[str, object]], failures: Sequence[str]) -> str:
    if not records:
        return "no closure records yet"
    if failures:
        return f"awaiting {failures[0]}"
    return "human evidence review of the promotion packet"


def _calibration(reviewed: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Recommend high-risk thresholds from reviewer dispositions.

    Nothing reads this section: it is a suggestion for a reviewed product
    decision.  Records without a reviewer disposition or without a joined
    observation carry no score and are excluded.
    """
    events = _feedback_events(reviewed)
    global_calibration = calibrate_high_risk_threshold(scored_outcomes_from_feedback(events))
    per_service: dict[str, object] = {}
    for service in sorted({event.service for event in events if event.service}):
        profile = calibrate_service_profile(service=service, events=events)
        per_service[service] = _calibration_view(profile.calibration) | {"source": profile.source}
    return {
        "applied": False,
        "note": CALIBRATION_NOTE,
        # A closure record identifies its scope only by repository; that is the
        # finest service granularity available to this report.
        "service_key": "subject.repository",
        "disposition_mapping": {
            disposition: outcome.value for disposition, outcome in _DISPOSITION_OUTCOMES.items()
        },
        "failure_samples_from": list(_FAILURE_DISPOSITIONS),
        "default_high_threshold": DEFAULT_HIGH_THRESHOLD,
        "global": _calibration_view(global_calibration),
        "per_service": per_service,
    }


def _feedback_events(reviewed: Sequence[Mapping[str, object]]) -> tuple[FeedbackEvent, ...]:
    events: list[FeedbackEvent] = []
    for record in reviewed:
        source = record["source_observation"]
        if not isinstance(source, Mapping):
            continue
        disposition = record["reviewer_signal"]["risk"]  # type: ignore[index]
        outcome = _DISPOSITION_OUTCOMES.get(str(disposition))
        if outcome is None:
            continue
        subject = record["subject"]
        assert isinstance(subject, Mapping)
        events.append(
            FeedbackEvent(
                event_id=f"{subject['repository']}#{subject['pr_number']}@{subject['head_sha']}",
                capability="predictive-risk",
                subject_id=str(subject["head_sha"]),
                outcome=outcome,
                service=str(subject["repository"]),
                metadata={"risk_score": str(source["score"])},
                occurred_at=str(record["recorded_at"]),
            )
        )
    return tuple(events)


def _calibration_view(calibration: RiskCalibration) -> dict[str, object]:
    return {
        "suggested_high_threshold": calibration.high_threshold,
        "sample_size": calibration.sample_size,
        "failed_samples": calibration.failed_samples,
        "changed_from_default": calibration.changed_from_default,
        "confidence": round(calibration.confidence, 4),
        "evidence": list(calibration.evidence),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
