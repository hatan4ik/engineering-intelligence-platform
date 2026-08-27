"""Selective enforcement is one deterministic rule with an owner escape hatch.

The matrix below is the whole authority surface: mode, the rule condition, a
waiver, the approval expiry, and the environment kill switch.
"""

from datetime import date

import pytest

from intelligence.risk import RiskAssessment, RiskFactor
from product.pr_guardian.config import parse_repository_config
from product.pr_guardian.contracts import ProductContractError, ProductMode
from product.pr_guardian.enforcement import (
    KILL_SWITCH_ENV,
    REASON_APPROVAL_EXPIRED,
    REASON_CONDITION_MET,
    REASON_CONDITION_NOT_MET,
    REASON_KILL_SWITCH,
    REASON_MODE_NOT_ENFORCING,
    REASON_THRESHOLD_NOT_MET,
    REASON_WAIVED,
    enforcement_decision,
    publishable_conclusion,
)


NOW = date(2026, 8, 26)
IAC_FILES = ("infra/payments/main.tf",)
IAC_AND_LEGACY = ("infra/legacy/old.tf",)


def assessment(*, score=80, factors=("infrastructure-change", "weak-test-evidence")):
    return RiskAssessment(
        score=score,
        band="critical" if score >= 75 else "high",
        blast_radius=("payments",),
        factors=tuple(RiskFactor(name, 10, f"{name} detected") for name in factors),
    )


def config(mode="enforce", *, waivers=(), expires_on="2026-12-31", threshold=70):
    payload = {
        "mode": mode,
        "service_ids": ["payments"],
        "service_owners": ["octocat"],
        "policy_version": "pr-policy-2026-08",
    }
    if mode == "enforce":
        payload["enforcement"] = {
            "rule": "iac-change-without-test-evidence-at-high-risk",
            "threshold": threshold,
            "approved_by": "octocat",
            "approved_on": "2026-08-01",
            "expires_on": expires_on,
            "waivers": list(waivers),
        }
    # require_unexpired=False mirrors how the runtime loads a config: an
    # approval that lapsed yesterday still loads, and the decision functions
    # are what refuse to act on it.
    return parse_repository_config(
        payload, repository="acme/platform", now=NOW, require_unexpired=False
    )


def waiver(*, path_glob="infra/legacy/*.tf", expires_on="2026-10-01"):
    return {
        "path_glob": path_glob,
        "reason": "Frozen legacy stack; owner accepts the risk.",
        "owner": "octocat",
        "expires_on": expires_on,
    }


@pytest.mark.parametrize("mode", ["shadow", "advisory"])
def test_non_enforcing_modes_never_block(mode):
    decision = enforcement_decision(config(mode), assessment(), IAC_FILES, NOW, environ={})

    assert decision.would_block is False
    assert decision.reason == REASON_MODE_NOT_ENFORCING
    assert decision.rule is None


def test_enforce_blocks_only_its_deterministic_condition():
    decision = enforcement_decision(config(), assessment(), IAC_FILES, NOW, environ={})

    assert decision.would_block is True
    assert decision.reason == REASON_CONDITION_MET
    assert decision.rule == "iac-change-without-test-evidence-at-high-risk"
    assert decision.waived_by is None


@pytest.mark.parametrize(
    ("score", "factors", "files"),
    [
        (60, ("infrastructure-change", "weak-test-evidence"), IAC_FILES),
        (80, ("infrastructure-change",), IAC_FILES),
        (80, ("weak-test-evidence",), IAC_FILES),
        (80, ("infrastructure-change", "weak-test-evidence"), ("product/service.py",)),
    ],
)
def test_enforce_does_not_block_when_any_part_of_the_condition_is_absent(score, factors, files):
    decision = enforcement_decision(
        config(), assessment(score=score, factors=factors), files, NOW, environ={}
    )

    assert decision.would_block is False
    assert decision.reason == REASON_CONDITION_NOT_MET


def test_an_unexpired_waiver_covering_every_triggering_file_bypasses_the_rule():
    decision = enforcement_decision(
        config(waivers=[waiver()]), assessment(), IAC_AND_LEGACY, NOW, environ={}
    )

    assert decision.would_block is False
    assert decision.reason == REASON_WAIVED
    assert decision.waived_by == "octocat"


def test_an_expired_waiver_does_not_bypass_the_rule():
    decision = enforcement_decision(
        config(waivers=[waiver(expires_on="2026-08-25")]), assessment(), IAC_AND_LEGACY, NOW, environ={}
    )

    assert decision.would_block is True
    assert decision.waived_by is None


def test_a_waiver_that_covers_only_some_triggering_files_does_not_bypass_the_rule():
    decision = enforcement_decision(
        config(waivers=[waiver()]),
        assessment(),
        IAC_AND_LEGACY + IAC_FILES,
        NOW,
        environ={},
    )

    assert decision.would_block is True
    assert decision.waived_by is None


def test_kill_switch_forces_a_non_blocking_decision():
    decision = enforcement_decision(
        config(), assessment(), IAC_FILES, NOW, environ={KILL_SWITCH_ENV: "TRUE"}
    )

    assert decision.would_block is False
    assert decision.reason == REASON_KILL_SWITCH


def test_kill_switch_only_responds_to_an_explicit_true():
    decision = enforcement_decision(
        config(), assessment(), IAC_FILES, NOW, environ={KILL_SWITCH_ENV: "no"}
    )

    assert decision.would_block is True


def test_an_expired_owner_approval_stops_blocking_even_though_the_file_still_says_enforce():
    expired = config(expires_on="2026-08-27")
    decision = enforcement_decision(expired, assessment(), IAC_FILES, date(2026, 8, 28), environ={})

    assert decision.would_block is False
    assert decision.reason == REASON_APPROVAL_EXPIRED


def test_enforcement_decision_serializes_to_the_observation_shape():
    payload = enforcement_decision(config(), assessment(), IAC_FILES, NOW, environ={}).as_dict()

    assert set(payload) == {"would_block", "reason", "rule", "waived_by"}


def test_authoring_enforce_requires_an_owner_approval_that_has_not_expired():
    payload = {
        "mode": "enforce",
        "service_ids": ["payments"],
        "service_owners": ["octocat"],
        "policy_version": "pr-policy-2026-08",
        "enforcement": {
            "rule": "iac-change-without-test-evidence-at-high-risk",
            "threshold": 70,
            "approved_by": "octocat",
            "approved_on": "2024-01-01",
            "expires_on": "2025-01-01",
        },
    }
    with pytest.raises(ProductContractError, match=r"enforcement\.expires_on"):
        parse_repository_config(payload, repository="acme/platform", now=NOW)


def test_an_expired_approval_still_loads_so_the_lapse_is_a_runtime_decision():
    lapsed = config(expires_on="2026-08-25")

    decision = enforcement_decision(lapsed, assessment(), IAC_FILES, NOW, environ={})

    assert decision.would_block is False
    assert decision.reason == REASON_APPROVAL_EXPIRED


# --- publisher-side re-check -------------------------------------------------


def observation(*, mode="enforce", would_block=True, rule="iac-change-without-test-evidence-at-high-risk", score=80):
    return {
        "mode": mode,
        "assessment": {"score": score, "band": "critical"},
        "enforcement": {
            "would_block": would_block,
            "reason": REASON_CONDITION_MET if would_block else REASON_CONDITION_NOT_MET,
            "rule": rule,
            "waived_by": None,
        },
    }


def test_publisher_publishes_failure_only_when_observation_and_config_agree():
    decision = publishable_conclusion(observation(), config(), environ={}, now=NOW)

    assert decision.conclusion == "failure"


@pytest.mark.parametrize(
    ("record", "repository_config"),
    [
        (observation(mode="advisory"), config()),
        (observation(would_block=False), config()),
        (observation(), config("advisory")),
        (observation(), config("shadow")),
        (observation(rule="security-boundary-change-without-test-evidence-at-high-risk"), config()),
    ],
)
def test_publisher_refuses_failure_when_the_config_re_read_disagrees(record, repository_config):
    decision = publishable_conclusion(record, repository_config, environ={}, now=NOW)

    assert decision.conclusion == "neutral"
    assert decision.reason


def test_publisher_honours_the_kill_switch_in_the_trusted_workflow():
    decision = publishable_conclusion(
        observation(), config(), environ={KILL_SWITCH_ENV: "true"}, now=NOW
    )

    assert decision.conclusion == "neutral"
    assert decision.reason == REASON_KILL_SWITCH


def test_publisher_refuses_failure_after_the_owner_approval_expired():
    # This is the production path: the runtime loader accepts a lapsed approval
    # so the publisher can lapse to neutral instead of crashing on the day it
    # expires.
    lapsed = config(expires_on="2026-08-25")

    decision = publishable_conclusion(observation(), lapsed, environ={}, now=NOW)

    assert decision.conclusion == "neutral"
    assert decision.reason == REASON_APPROVAL_EXPIRED


def test_publisher_refuses_a_forged_block_whose_score_is_below_the_threshold():
    forged = observation()
    forged["assessment"] = {"score": 10, "band": "low"}

    decision = publishable_conclusion(forged, config(threshold=70), environ={}, now=NOW)

    assert decision.conclusion == "neutral"
    assert decision.reason == REASON_THRESHOLD_NOT_MET


def test_publisher_refuses_a_block_whose_score_is_missing_or_malformed():
    forged = observation()
    forged["assessment"] = {"score": "80", "band": "critical"}

    decision = publishable_conclusion(forged, config(threshold=70), environ={}, now=NOW)

    assert decision.conclusion == "neutral"
    assert decision.reason == REASON_THRESHOLD_NOT_MET


def test_shadow_mode_is_the_default_authority_state():
    assert ProductMode.SHADOW.value == "shadow"
