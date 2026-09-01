"""A shadow-pilot plan stays non-enforcing before it reaches GitHub."""

from __future__ import annotations

import json

import pytest

from product.pr_guardian.contracts import ProductMode, RepositoryConfig
from product.pr_guardian.pilot import (
    EVALUATION_PERMISSIONS,
    OUTCOME_PERMISSIONS,
    PUBLISHER_PERMISSIONS,
    REPORT_PERMISSIONS,
    ShadowPilotContractError,
    parse_shadow_pilot_manifest,
    validate_shadow_installation,
)
from scripts.validate_pr_guardian_shadow_pilot import main


def manifest_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "pilot_id": "pr-guardian-payments",
        "repository": "acme/payments",
        "service_ids": ["payments"],
        "owner_ids": ["team-payments"],
        "evidence_sources": ["github-pull-request"],
        "policy_version": "pr-policy-2026-09",
        "data_classification": "internal",
        "mode": "shadow",
        "decision_impact": "advisory",
        "configuration_path": ".eip/pr-guardian.json",
        "minimum_shadow_observations": 30,
        "reviewer_labels": {
            "confirmed_risk": "eip-pr-guardian/confirmed-risk",
            "false_positive": "eip-pr-guardian/false-positive",
            "useful": "eip-pr-guardian/useful",
            "not_useful": "eip-pr-guardian/not-useful",
        },
        "workflow_controls": {
            "evaluation_permissions": list(EVALUATION_PERMISSIONS),
            "publisher_permissions": list(PUBLISHER_PERMISSIONS),
            "outcome_permissions": list(OUTCOME_PERMISSIONS),
            "report_permissions": list(REPORT_PERMISSIONS),
            "evaluation_has_write_token": False,
            "publisher_checks_out_pr_head": False,
            "outcome_checks_out_pr_head": False,
            "check_is_required": False,
        },
        "kill_switch_variable": "EIP_PR_GUARDIAN_KILL_SWITCH",
        "kill_switch_engaged_value": "true",
        "evidence_retention": {
            "system": "enterprise-evidence-registry",
            "locator": "evidence://eip/pr-guardian/payments/2026-q3",
            "retention_days": 365,
            "access_control_ref": "policy://data-governance/eip-internal",
            "immutability_control_ref": "control://records/worm-retention-v1",
        },
        "operating_model": {
            "pilot_owner": "platform-owner",
            "security_reviewer": "security-owner",
            "developer_experience_owner": "developer-experience",
            "reviewer_disposition_sla_hours": 72,
            "hypercare_days": 14,
        },
    }


def repository_config(mode: ProductMode = ProductMode.SHADOW) -> RepositoryConfig:
    return RepositoryConfig(
        repository="acme/payments",
        service_ids=("payments",),
        owner_ids=("team-payments",),
        evidence_sources=("github-pull-request",),
        policy_version="pr-policy-2026-09",
        mode=mode,
    )


def test_shadow_pilot_manifest_is_exact_and_never_grants_product_authority():
    manifest = parse_shadow_pilot_manifest(manifest_payload())

    assert manifest.mode == "shadow"
    assert manifest.decision_impact == "advisory"
    assert manifest.advisory_or_enforcement_authorized is False
    assert parse_shadow_pilot_manifest(manifest.to_payload()) == manifest


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("mode",), "advisory", "mode must be shadow"),
        (
            ("workflow_controls", "check_is_required"),
            True,
            "check_is_required must be false",
        ),
        (
            ("evidence_retention", "system"),
            "GitHub Actions",
            "external evidence system",
        ),
        (("owner_ids",), ["team-todo"], "real accountable identity"),
    ],
)
def test_shadow_pilot_manifest_rejects_unsafe_or_placeholder_controls(
    path, value, message
):
    payload = manifest_payload()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ShadowPilotContractError, match=message):
        parse_shadow_pilot_manifest(payload)


def test_shadow_installation_must_match_repository_config_and_stay_shadow_mode():
    manifest = parse_shadow_pilot_manifest(manifest_payload())
    validate_shadow_installation(manifest, repository_config())

    with pytest.raises(ShadowPilotContractError, match="mode=shadow"):
        validate_shadow_installation(manifest, repository_config(ProductMode.ADVISORY))


def test_cli_validates_manifest_and_optional_repository_configuration(tmp_path, capsys):
    manifest_path = tmp_path / "pilot.json"
    manifest_path.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    config_dir = tmp_path / ".eip"
    config_dir.mkdir()
    (config_dir / "pr-guardian.json").write_text(
        json.dumps(
            {
                "mode": "shadow",
                "service_ids": ["payments"],
                "service_owners": ["team-payments"],
                "evidence_sources": ["github-pull-request"],
                "policy_version": "pr-policy-2026-09",
            }
        ),
        encoding="utf-8",
    )

    assert main(["--manifest", str(manifest_path), "--config-root", str(tmp_path)]) == 0
    assert "advisory_or_enforcement_authorized=False" in capsys.readouterr().out


def test_cli_reports_a_malformed_repository_configuration_without_a_traceback(
    tmp_path, capsys
):
    manifest_path = tmp_path / "pilot.json"
    manifest_path.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    config_dir = tmp_path / ".eip"
    config_dir.mkdir()
    (config_dir / "pr-guardian.json").write_text("{not-json", encoding="utf-8")

    assert main(["--manifest", str(manifest_path), "--config-root", str(tmp_path)]) == 2
    assert "shadow-pilot manifest is invalid" in capsys.readouterr().err
