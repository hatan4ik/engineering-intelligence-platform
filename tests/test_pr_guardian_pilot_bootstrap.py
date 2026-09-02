import json

from product.pr_guardian.pilot import PilotDataClassification
from product.pr_guardian.pilot_bootstrap import build_shadow_pilot_bundle
from scripts.prepare_pr_guardian_shadow_pilot import main


def _bundle():
    return build_shadow_pilot_bundle(
        repository="acme/platform",
        service_ids=("payments",),
        owner_ids=("team-payments",),
        policy_version="pr-policy-v1",
        data_classification=PilotDataClassification.INTERNAL,
        evidence_system="azure-immutable-audit",
        evidence_locator="eip-pilots/acme-platform",
        evidence_access_control_ref="rbac-policy-17",
        evidence_immutability_control_ref="worm-policy-90d",
        pilot_owner="team-payments",
        security_reviewer="security-sre",
        developer_experience_owner="developer-experience",
    )


def test_bootstrap_builds_cross_validated_shadow_contracts():
    bundle = _bundle()
    payload = bundle.to_payload()
    assert bundle.manifest.pilot_id == "pr-guardian-acme-platform"
    assert bundle.manifest.mode == "shadow"
    assert bundle.runtime_configuration["mode"] == "shadow"
    assert payload["advisory_or_enforcement_authorized"] is False
    assert payload["operational_evidence_collected"] is False


def test_cli_writes_reviewable_files_but_refuses_overwrite(tmp_path):
    argv = [
        "--repository",
        "acme/platform",
        "--service-id",
        "payments",
        "--owner-id",
        "team-payments",
        "--data-classification",
        "internal",
        "--evidence-system",
        "azure-immutable-audit",
        "--evidence-locator",
        "eip-pilots/acme-platform",
        "--evidence-access-control-ref",
        "rbac-policy-17",
        "--evidence-immutability-control-ref",
        "worm-policy-90d",
        "--pilot-owner",
        "team-payments",
        "--security-reviewer",
        "security-sre",
        "--developer-experience-owner",
        "developer-experience",
        "--write-root",
        str(tmp_path),
    ]
    assert main(argv) == 0
    eip = tmp_path / ".eip"
    manifest = json.loads((eip / "pr-guardian-shadow-pilot.json").read_text())
    config = json.loads((eip / "pr-guardian.json").read_text())
    assert manifest["mode"] == "shadow"
    assert config["mode"] == "shadow"
    assert main(argv) == 2
