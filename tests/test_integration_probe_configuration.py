"""The integration probe refuses to run against an incomplete configuration."""
from __future__ import annotations

import json
import re
from pathlib import Path

from validation.integration_probe import (
    REQUIRED_ENVIRONMENT,
    WORKFLOW_REQUIRED_ENVIRONMENT,
    check_configuration,
    main,
    missing_configuration,
)

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "INTEGRATION-PROOF-RUNBOOK.md"
WORKFLOW = ROOT / ".github" / "workflows" / "integration-proof.yml"

COMPLETE_ENVIRONMENT = {
    "EIP_BASE_URL": "https://eip.private",
    "EIP_INTEGRATION_ALLOWED_BEARER_FILE": "/run/secrets/allowed",
    "EIP_INTEGRATION_DENIED_BEARER_FILE": "/run/secrets/denied",
    "EIP_INTEGRATION_ALLOWED_QUERY": "What is the approved rollback?",
    "EIP_INTEGRATION_DENIED_QUERY": "What is the approved rollback?",
    "EIP_INTEGRATION_ALLOWED_SOURCE": "docs/allowed.md",
    "AZURE_SEARCH_HOST": "search.privatelink",
    "AZURE_OPENAI_HOST": "openai.privatelink",
    "AZURE_KEYVAULT_HOST": "vault.privatelink",
    "EIP_COSMOS_HOST": "cosmos.privatelink",
    "AZURE_POSTGRESQL_HOST": "pg.privatelink",
    "EIP_TEMPORAL_HOST": "temporal.privatelink",
    "EIP_INTEGRATION_SCOPE": "acme/platform integration westeurope sha=abc image=sha256:def",
    "EIP_INTEGRATION_EVIDENCE": "/var/evidence/integration-evidence.json",
}

COMPLETE_WORKFLOW_ENVIRONMENT = dict(
    COMPLETE_ENVIRONMENT,
    AZURE_CLIENT_ID="00000000-0000-0000-0000-000000000000",
    AZURE_TENANT_ID="00000000-0000-0000-0000-000000000000",
    AZURE_SUBSCRIPTION_ID="00000000-0000-0000-0000-000000000000",
    AKS_RESOURCE_GROUP="rg-eip-integration",
    AKS_CLUSTER_NAME="aks-eip-integration",
)


def test_the_required_list_has_the_fourteen_documented_variables():
    assert len(REQUIRED_ENVIRONMENT) == 14
    assert len(set(REQUIRED_ENVIRONMENT)) == 14
    assert set(COMPLETE_ENVIRONMENT) == set(REQUIRED_ENVIRONMENT)


def test_workflow_preflight_requires_azure_and_aks_settings_before_login():
    assert len(WORKFLOW_REQUIRED_ENVIRONMENT) == 19
    assert set(COMPLETE_WORKFLOW_ENVIRONMENT) == set(WORKFLOW_REQUIRED_ENVIRONMENT)
    assert missing_configuration(COMPLETE_ENVIRONMENT, required=WORKFLOW_REQUIRED_ENVIRONMENT) == (
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AKS_RESOURCE_GROUP",
        "AKS_CLUSTER_NAME",
    )


def test_scope_and_evidence_path_are_required_so_a_pass_is_never_unscoped():
    """docs/PRODUCTION-EVIDENCE.md: evidence names its scope. The runbook requires
    the evidence path to be outside the source checkout, so neither may default."""

    assert "EIP_INTEGRATION_SCOPE" in REQUIRED_ENVIRONMENT
    assert "EIP_INTEGRATION_EVIDENCE" in REQUIRED_ENVIRONMENT
    assert missing_configuration(
        {name: value for name, value in COMPLETE_ENVIRONMENT.items() if name != "EIP_INTEGRATION_SCOPE"}
    ) == ("EIP_INTEGRATION_SCOPE",)


def test_every_required_variable_is_documented_in_the_runbook():
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", RUNBOOK.read_text(encoding="utf-8")))
    assert set(REQUIRED_ENVIRONMENT) <= documented


def test_missing_configuration_reports_every_unset_variable():
    assert missing_configuration({}) == REQUIRED_ENVIRONMENT
    assert missing_configuration(COMPLETE_ENVIRONMENT) == ()


def test_blank_values_count_as_missing():
    environment = dict(COMPLETE_ENVIRONMENT, EIP_BASE_URL="   ")

    assert missing_configuration(environment) == ("EIP_BASE_URL",)


def test_main_emits_one_configuration_result_and_exits_2(tmp_path, monkeypatch, capsys):
    evidence = tmp_path / "integration-evidence.json"
    for name in REQUIRED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    # Only the output path is set, so the refusal record is readable; everything
    # else — including the scope — is missing and must be named.
    monkeypatch.setenv("EIP_INTEGRATION_EVIDENCE", str(evidence))
    monkeypatch.setattr(
        "validation.integration_probe.collect",
        lambda: (_ for _ in ()).throw(AssertionError("probes must not run on incomplete config")),
    )

    code = main()

    assert code == 2
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    expected_missing = [name for name in REQUIRED_ENVIRONMENT if name != "EIP_INTEGRATION_EVIDENCE"]
    assert payload["passed"] is False
    assert payload["scope"] == "configuration-refused"
    assert payload["results"] == [
        {"probe": "configuration", "passed": False, "missing": expected_missing}
    ]
    assert "EIP_INTEGRATION_SCOPE" in expected_missing
    assert "sha256" in payload
    assert "configuration" in capsys.readouterr().out


def test_configuration_only_mode_refuses_before_any_probe(tmp_path, monkeypatch, capsys):
    evidence = tmp_path / "integration-evidence.json"
    for name in REQUIRED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EIP_INTEGRATION_EVIDENCE", str(evidence))
    monkeypatch.setattr(
        "validation.integration_probe.collect",
        lambda: (_ for _ in ()).throw(AssertionError("configuration-only mode must not probe")),
    )

    code = main(["--check-configuration"])

    assert code == 2
    assert json.loads(evidence.read_text(encoding="utf-8"))["scope"] == "configuration-refused"
    assert "missing required environment" in capsys.readouterr().err


def test_configuration_only_mode_accepts_complete_invocation_without_probing(monkeypatch, capsys):
    for name, value in COMPLETE_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "validation.integration_probe.collect",
        lambda: (_ for _ in ()).throw(AssertionError("configuration-only mode must not probe")),
    )

    assert check_configuration() == 0
    assert "no probe was run" in capsys.readouterr().out


def test_workflow_configuration_only_mode_refuses_before_azure_login(tmp_path, monkeypatch):
    evidence = tmp_path / "integration-evidence.json"
    for name, value in COMPLETE_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("EIP_INTEGRATION_EVIDENCE", str(evidence))

    assert main(["--check-workflow-configuration"]) == 2
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["results"][0]["missing"] == [
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AKS_RESOURCE_GROUP",
        "AKS_CLUSTER_NAME",
    ]


def test_unknown_probe_argument_is_rejected_without_running(tmp_path, monkeypatch, capsys):
    evidence = tmp_path / "integration-evidence.json"
    monkeypatch.setenv("EIP_INTEGRATION_EVIDENCE", str(evidence))
    monkeypatch.setattr(
        "validation.integration_probe.collect",
        lambda: (_ for _ in ()).throw(AssertionError("unknown arguments must not probe")),
    )

    assert main(["--unsafe"]) == 2
    assert not evidence.exists()
    assert "usage:" in capsys.readouterr().err


def test_the_workflow_passes_every_required_variable():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for name in WORKFLOW_REQUIRED_ENVIRONMENT:
        assert f"{name}:" in workflow, name


def test_the_workflow_is_explicitly_opt_in_and_private_runner_only():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" not in workflow
    assert "cron:" not in workflow
    assert "run_private_integration:" in workflow
    assert "default: false" in workflow
    assert "runs-on: [self-hosted, eip-private-integration]" in workflow
    assert "id-token: write" in workflow
    assert "environment: integration" in workflow


def test_the_workflow_writes_evidence_outside_the_source_checkout():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "EIP_INTEGRATION_EVIDENCE: ${{ runner.temp }}/integration-evidence.json" in workflow
    assert "EIP_INTEGRATION_SCOPE: ${{ vars.EIP_INTEGRATION_SCOPE }}" in workflow
    assert "--check-workflow-configuration" in workflow
    # Nothing may read or upload the old in-checkout default path.
    assert "path: integration-evidence.json" not in workflow
