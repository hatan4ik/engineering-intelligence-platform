import pytest

from feedback.pr_guardian_shadow import build_shadow_report
from intelligence.risk import RiskAssessment, RiskFactor
from integrations.github.pr_guardian import PullRequestEvent
from product.pr_guardian_shadow import (
    closure_outcome,
    observation_comment,
    observation_from_assessment,
    observation_from_comment,
    validate_observation,
)


def observation(*, sha="deadbeef", would_block=True):
    return observation_from_assessment(
        event=PullRequestEvent("acme/platform", 42, sha, "synchronize"),
        assessment=RiskAssessment(
            score=95,
            band="critical",
            blast_radius=("payments",),
            factors=(RiskFactor("security-boundary-change", 20, "identity/security controls changed"),),
        ),
        workflow_id="pr:acme/platform:42",
        changed_services=("payments",),
        would_require_extended_tests=True,
        would_require_additional_approval=True,
        would_block=would_block,
        audit_chain_verified=True,
        observed_at="2026-08-26T12:00:00+00:00",
    )


def closed_event(*, sha="deadbeef", labels=None):
    return {
        "action": "closed",
        "number": 42,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {
            "head": {"sha": sha},
            "merged": True,
            "labels": [{"name": label} for label in (labels or [])],
        },
    }


def test_shadow_observation_round_trips_in_a_sticky_comment():
    record = observation()
    body = observation_comment(record)
    assert "Advisory only" in body
    assert "would block pending remediation" in body
    assert observation_from_comment(body) == record


def test_shadow_observation_rejects_unexpected_transfer_fields():
    record = observation()
    record["unexpected"] = "not accepted"
    with pytest.raises(ValueError, match="unexpected or missing"):
        validate_observation(record)


def test_closure_requires_one_unambiguous_reviewer_label_and_matching_pr():
    outcome = closure_outcome(
        payload=closed_event(labels=["eip-pr-guardian/confirmed-risk", "eip-pr-guardian/useful"]),
        observation=observation(),
        recorded_at="2026-08-26T12:30:00+00:00",
    )
    assert outcome["reviewer_signal"] == {"risk": "confirmed-risk", "utility": "useful"}
    assert outcome["source_observation"]["would_block"] is True

    with pytest.raises(ValueError, match="conflicting risk"):
        closure_outcome(
            payload=closed_event(labels=["eip-pr-guardian/confirmed-risk", "eip-pr-guardian/false-positive"]),
            observation=observation(),
        )
    with pytest.raises(ValueError, match="does not match"):
        closure_outcome(payload=closed_event(sha="facefeed"), observation=observation())


def test_shadow_report_measures_simulation_but_never_authorizes_blocking():
    confirmed = closure_outcome(
        payload=closed_event(labels=["eip-pr-guardian/confirmed-risk"]), observation=observation()
    )
    false_positive = closure_outcome(
        payload=closed_event(labels=["eip-pr-guardian/false-positive"]), observation=observation()
    )
    report = build_shadow_report([confirmed, false_positive])
    assert report["sample"]["reviewer_classifications"] == 2
    assert report["simulated_block_decision"]["true_positive"] == 1
    assert report["simulated_block_decision"]["false_positive"] == 1
    assert report["promotion_readiness"]["blocking_authorized"] is False
    assert report["promotion_readiness"]["decision"] == "shadow-only"
