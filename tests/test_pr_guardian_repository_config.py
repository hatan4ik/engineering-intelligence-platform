"""The repository — not the platform — chooses the PR Guardian mode.

Every invalid configuration must name the offending field so a service owner
can fix their own file without reading platform source.
"""

import json
from datetime import date

import pytest

from product.pr_guardian.config import (
    CONFIG_RELATIVE_PATH,
    default_shadow_config,
    load_repository_config,
    parse_repository_config,
)
from product.pr_guardian.contracts import (
    EnforcementRule,
    ProductContractError,
    ProductMode,
)


NOW = date(2026, 8, 26)


def enforce_payload(**overrides):
    payload = {
        "mode": "enforce",
        "service_ids": ["payments"],
        "service_owners": ["octocat"],
        "policy_version": "pr-policy-2026-08",
        "enforcement": {
            "rule": "iac-change-without-test-evidence-at-high-risk",
            "threshold": 70,
            "approved_by": "octocat",
            "approved_on": "2026-08-01",
            "expires_on": "2026-12-31",
            "waivers": [
                {
                    "path_glob": "infra/legacy/*.tf",
                    "reason": "Frozen legacy stack; owner accepts the risk.",
                    "owner": "octocat",
                    "expires_on": "2026-10-01",
                }
            ],
        },
    }
    payload.update(overrides)
    return payload


def write_config(tmp_path, payload):
    path = tmp_path / CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_missing_configuration_file_means_shadow_and_never_enforcement(tmp_path):
    config = load_repository_config(tmp_path, repository="acme/platform", now=NOW)

    assert config.mode is ProductMode.SHADOW
    assert config.enforcement is None
    assert config == default_shadow_config("acme/platform")


def test_advisory_configuration_declares_owners_and_carries_no_enforcement(tmp_path):
    write_config(tmp_path, {
        "mode": "advisory",
        "service_ids": ["payments"],
        "service_owners": ["octocat", "team-payments"],
        "policy_version": "pr-policy-2026-08",
    })

    config = load_repository_config(tmp_path, repository="acme/platform", now=NOW)

    assert config.mode is ProductMode.ADVISORY
    assert config.owner_ids == ("octocat", "team-payments")
    assert config.enforcement is None


def test_enforce_configuration_records_the_owner_approval_and_waivers(tmp_path):
    write_config(tmp_path, enforce_payload())

    config = load_repository_config(tmp_path, repository="acme/platform", now=NOW)

    assert config.mode is ProductMode.ENFORCE
    assert config.enforcement is not None
    assert config.enforcement.rule is EnforcementRule.IAC_CHANGE_WITHOUT_TEST_EVIDENCE
    assert config.enforcement.threshold == 70
    assert config.enforcement.approved_by == "octocat"
    assert config.enforcement.waivers[0].path_glob == "infra/legacy/*.tf"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"mode": "blocking"}, "mode"),
        ({"service_owners": []}, "service_owners"),
        ({"service_owners": ["octocat", "octocat"]}, "service_owners"),
        ({"service_ids": []}, "service_ids"),
        ({"policy_version": ""}, "policy_version"),
        ({"repository": "someone/else"}, "repository"),
        ({"surprise": True}, "surprise"),
    ],
)
def test_each_invalid_top_level_field_is_named(tmp_path, payload, field):
    with pytest.raises(ProductContractError, match=field):
        parse_repository_config(enforce_payload(**payload), repository="acme/platform", now=NOW)


def test_enforce_without_an_enforcement_block_is_invalid():
    payload = enforce_payload()
    payload.pop("enforcement")
    with pytest.raises(ProductContractError, match="enforcement"):
        parse_repository_config(payload, repository="acme/platform", now=NOW)


def test_enforcement_block_outside_enforce_mode_is_invalid():
    with pytest.raises(ProductContractError, match="enforcement"):
        parse_repository_config(enforce_payload(mode="advisory"), repository="acme/platform", now=NOW)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"rule": "block-everything"}, r"enforcement\.rule"),
        ({"threshold": "70"}, r"enforcement\.threshold"),
        ({"approved_by": "stranger"}, r"approved_by"),
        ({"approved_on": "01-08-2026"}, r"enforcement\.approved_on"),
        ({"expires_on": "2026-13-01"}, r"enforcement\.expires_on"),
        ({"expires_on": "2026-08-25"}, r"enforcement\.expires_on"),
    ],
)
def test_each_invalid_enforcement_field_is_named(override, field):
    payload = enforce_payload()
    payload["enforcement"] = {**payload["enforcement"], **override}
    with pytest.raises(ProductContractError, match=field):
        parse_repository_config(payload, repository="acme/platform", now=NOW)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"path_glob": ""}, r"waivers\[0\]\.path_glob"),
        ({"reason": ""}, r"waivers\[0\]\.reason"),
        ({"owner": "stranger"}, r"waivers\[0\]\.owner"),
        ({"expires_on": "soon"}, r"waivers\[0\]\.expires_on"),
    ],
)
def test_each_invalid_waiver_field_is_named_with_its_index(override, field):
    payload = enforce_payload()
    waiver = {**payload["enforcement"]["waivers"][0], **override}
    payload["enforcement"] = {**payload["enforcement"], "waivers": [waiver]}
    with pytest.raises(ProductContractError, match=field):
        parse_repository_config(payload, repository="acme/platform", now=NOW)


def test_unparseable_configuration_file_is_refused_not_silently_ignored(tmp_path):
    path = tmp_path / CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ProductContractError, match="valid JSON"):
        load_repository_config(tmp_path, repository="acme/platform", now=NOW)


def test_owner_order_is_normalized_but_duplicates_are_refused(tmp_path):
    write_config(tmp_path, {
        "mode": "advisory",
        "service_ids": ["payments"],
        "service_owners": ["zoe", "octocat"],
        "policy_version": "pr-policy-2026-08",
    })

    config = load_repository_config(tmp_path, repository="acme/platform", now=NOW)

    assert config.owner_ids == ("octocat", "zoe")
