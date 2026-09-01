"""Metrics for reviewable PR Guardian shadow-pilot exports.

The report is deliberately conservative.  Its ``decision`` says only whether a
promotion *review* has enough inputs (``advisory-candidate``) or not
(``shadow-only``); ``blocking_authorized`` is always ``False``.  A human
evidence review and the controls in ``PRODUCTION-EVIDENCE.md`` are still needed
before any blocking rule can be proposed, and the ``calibration`` section is a
recommendation that nothing in this codebase applies.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from intelligence.risk_calibration import (
    DEFAULT_HIGH_THRESHOLD,
    RiskCalibration,
    ScoredOutcome,
    calibrate_high_risk_threshold,
)
from product.pr_guardian_shadow import ShadowOutcome, validate_outcome

CALIBRATION_NOTE = "Threshold changes are reviewed product decisions; this section is a recommendation only."

# ``calibrate_high_risk_threshold`` tunes a threshold to catch the *failed*
# class, so a reviewer-confirmed risk is a failed sample and a false positive is
# not.  The report publishes this mapping so a suggested threshold cannot be
# read in the wrong direction.
_DISPOSITION_FAILED = {"confirmed-risk": True, "false-positive": False}
_FAILURE_DISPOSITION = next(
    disposition for disposition, failed in _DISPOSITION_FAILED.items() if failed
)


def build_shadow_report(outcomes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    records: list[ShadowOutcome] = [validate_outcome(item) for item in outcomes]
    joined: list[ShadowOutcome] = [
        record for record in records if record["source_observation"] is not None
    ]
    reviewed: list[ShadowOutcome] = [
        record
        for record in joined
        if record["reviewer_signal"]["risk"] != "not-reviewed"
    ]
    confirmed = [
        record
        for record in reviewed
        if record["reviewer_signal"]["risk"] == "confirmed-risk"
    ]
    useful = sum(
        1 for record in joined if record["reviewer_signal"]["utility"] == "useful"
    )
    not_useful = sum(
        1 for record in joined if record["reviewer_signal"]["utility"] == "not-useful"
    )
    tp = fp = tn = fn = 0
    for record in reviewed:
        source = record["source_observation"]
        if source is None:
            continue
        would_block = source["would_block"]
        confirmed_risk = record["reviewer_signal"]["risk"] == "confirmed-risk"
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
        "minimum_simulated_block_precision": precision is not None
        and precision >= 0.50,
        "minimum_simulated_block_recall": recall is not None and recall >= 0.80,
    }
    failures = [
        name for name, complete in promotion_requirements.items() if not complete
    ]
    return {
        "schema_version": 1,
        "kind": "pr-guardian-shadow-report",
        "scope": "offline pilot export only",
        "input_provenance": {
            "canonical_outcome_export_sha256": canonical_shadow_outcomes_sha256(
                records
            ),
            "closure_records": len(records),
            "canonicalization": "validated closure records sorted by repository, PR, head SHA, and recorded_at",
        },
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


def canonical_json_sha256(payload: object) -> str:
    """Return the stable digest used to bind reviewable JSON evidence.

    The function deliberately rejects non-JSON values and NaN rather than
    quietly producing a platform-specific representation. It is a content
    fingerprint, not an authenticity or retention assertion.
    """

    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def canonical_shadow_outcomes_sha256(records: Sequence[ShadowOutcome]) -> str:
    """Fingerprint normalized outcomes independently of input-file order."""

    canonical_records = sorted(
        records,
        key=lambda record: (
            record["subject"]["repository"],
            record["subject"]["pr_number"],
            record["subject"]["head_sha"],
            record["recorded_at"],
        ),
    )
    return canonical_json_sha256(canonical_records)


def _next_review(
    records: Sequence[Mapping[str, object]], failures: Sequence[str]
) -> str:
    if not records:
        return "no closure records yet"
    if failures:
        return f"awaiting {failures[0]}"
    return "human evidence review of the promotion packet"


def _calibration(reviewed: Sequence[ShadowOutcome]) -> dict[str, object]:
    """Recommend high-risk thresholds from reviewer dispositions.

    Nothing reads this section: it is a suggestion for a reviewed product
    decision.  Records without a reviewer disposition or without a joined
    observation carry no score and are excluded.
    """
    outcomes = _scored_outcomes(reviewed)
    global_calibration = calibrate_high_risk_threshold(outcomes)
    per_service: dict[str, object] = {}
    for service in sorted({outcome.service for outcome in outcomes if outcome.service}):
        per_service[service] = _calibration_view(
            calibrate_high_risk_threshold(
                [outcome for outcome in outcomes if outcome.service == service]
            )
        )
    return {
        "applied": False,
        "note": CALIBRATION_NOTE,
        # A closure record identifies its scope only by repository; that is the
        # finest service granularity available to this report.
        "service_key": "subject.repository",
        "disposition_mapping": {
            disposition: "failed" if failed else "not-failed"
            for disposition, failed in _DISPOSITION_FAILED.items()
        },
        "failure_samples_from": _FAILURE_DISPOSITION,
        "default_high_threshold": DEFAULT_HIGH_THRESHOLD,
        "global": _calibration_view(global_calibration),
        "per_service": per_service,
    }


def _scored_outcomes(reviewed: Sequence[ShadowOutcome]) -> list[ScoredOutcome]:
    outcomes: list[ScoredOutcome] = []
    for record in reviewed:
        source = record["source_observation"]
        if source is None:
            continue
        disposition = record["reviewer_signal"]["risk"]
        if disposition not in _DISPOSITION_FAILED:
            continue
        subject = record["subject"]
        outcomes.append(
            ScoredOutcome(
                score=source["score"],
                failed=_DISPOSITION_FAILED[disposition],
                service=subject["repository"],
            )
        )
    return outcomes


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
