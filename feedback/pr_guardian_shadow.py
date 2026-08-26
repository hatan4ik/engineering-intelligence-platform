"""Metrics for reviewable PR Guardian shadow-pilot exports.

The report is deliberately conservative: it can show whether a promotion review
has enough inputs, but always leaves the capability in shadow mode.  A human
evidence review and the controls in ``PRODUCTION-EVIDENCE.md`` are still needed
before any blocking rule can be proposed.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from product.pr_guardian_shadow import validate_outcome


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
        "promotion_readiness": {
            "requirements": promotion_requirements,
            "unmet_requirements": failures,
            "blocking_authorized": False,
            "decision": "shadow-only",
        },
        "limitations": [
            "Closure and reviewer labels do not establish post-merge incident or rollback outcomes.",
            "This report is an input to an approved evidence record; it is not production evidence by itself.",
            "No report output can authorize PR Guardian merge blocking.",
        ],
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
