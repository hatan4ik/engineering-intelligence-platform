import json

from product.pr_guardian.pilot import (
    EVALUATION_PERMISSIONS,
    OUTCOME_PERMISSIONS,
    PUBLISHER_PERMISSIONS,
    REPORT_PERMISSIONS,
)
from product.pr_guardian.pilot_readiness import (
    PilotReadinessState,
    ReadinessCheckState,
    assess_shadow_pilot_checkout,
)


def _write_valid_checkout(root):
    eip = root / ".eip"
    eip.mkdir()
    config = {
        "repository": "acme/platform",
        "mode": "shadow",
        "service_ids": ["payments"],
        "service_owners": ["team-payments"],
        "evidence_sources": ["github-pull-request"],
        "policy_version": "pr-policy-v1",
    }
    manifest = {
        "schema_version": 1,
        "pilot_id": "pr-guardian-acme-platform",
        "repository": "acme/platform",
        "service_ids": ["payments"],
        "owner_ids": ["team-payments"],
        "evidence_sources": ["github-pull-request"],
        "policy_version": "pr-policy-v1",
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
            "system": "azure-immutable-audit",
            "locator": "eip-pilots/acme-platform",
            "retention_days": 90,
            "access_control_ref": "rbac-policy-17",
            "immutability_control_ref": "worm-policy-90d",
        },
        "operating_model": {
            "pilot_owner": "team-payments",
            "security_reviewer": "security-sre",
            "developer_experience_owner": "developer-experience",
            "reviewer_disposition_sla_hours": 72,
            "hypercare_days": 14,
        },
    }
    (eip / "pr-guardian.json").write_text(json.dumps(config), encoding="utf-8")
    (eip / "pr-guardian-shadow-pilot.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_missing_manifest_is_not_ready_and_never_authorizes(tmp_path):
    report = assess_shadow_pilot_checkout(tmp_path)
    assert report.state is PilotReadinessState.NOT_READY
    assert report.contract_ready is False
    assert report.advisory_or_enforcement_authorized is False
    assert report.operational_evidence_collected is False
    assert report.checks[0].state is ReadinessCheckState.FAIL


def test_matching_checkout_is_only_contract_ready(tmp_path):
    _write_valid_checkout(tmp_path)
    report = assess_shadow_pilot_checkout(tmp_path)

    assert report.state is PilotReadinessState.CONTRACT_READY
    assert report.contract_ready is True
    assert report.repository == "acme/platform"
    assert report.pilot_id == "pr-guardian-acme-platform"
    assert report.advisory_or_enforcement_authorized is False
    assert report.operational_evidence_collected is False
    external = [
        check for check in report.checks if check.state is ReadinessCheckState.EXTERNAL_REQUIRED
    ]
    assert len(external) == 3
    assert len(report.operator_actions) == 5


def test_mismatched_runtime_configuration_is_not_ready(tmp_path):
    _write_valid_checkout(tmp_path)
    path = tmp_path / ".eip" / "pr-guardian.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["service_ids"] = ["checkout"]
    path.write_text(json.dumps(config), encoding="utf-8")

    report = assess_shadow_pilot_checkout(tmp_path)
    assert report.state is PilotReadinessState.NOT_READY
    assert report.checks[-1].state is ReadinessCheckState.FAIL
    assert "does not match" in report.checks[-1].detail
