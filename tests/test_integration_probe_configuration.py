"""The integration probe refuses to run against an incomplete configuration."""
from __future__ import annotations

import json
import re
from pathlib import Path

from validation.integration_probe import (
    REQUIRED_ENVIRONMENT,
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
}


def test_the_required_list_has_the_twelve_documented_variables():
    assert len(REQUIRED_ENVIRONMENT) == 12
    assert len(set(REQUIRED_ENVIRONMENT)) == 12


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
    monkeypatch.setenv("EIP_INTEGRATION_EVIDENCE", str(evidence))
    monkeypatch.setenv("EIP_INTEGRATION_SCOPE", "integration/pilot")
    monkeypatch.setattr(
        "validation.integration_probe.collect",
        lambda: (_ for _ in ()).throw(AssertionError("probes must not run on incomplete config")),
    )

    code = main()

    assert code == 2
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["scope"] == "integration/pilot"
    assert payload["results"] == [
        {"probe": "configuration", "passed": False, "missing": list(REQUIRED_ENVIRONMENT)}
    ]
    assert "sha256" in payload
    assert "configuration" in capsys.readouterr().out


def test_the_workflow_passes_every_required_variable():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for name in REQUIRED_ENVIRONMENT:
        assert f"{name}:" in workflow, name


def test_the_workflow_is_scheduled_and_environment_gated():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" in workflow
    assert "cron:" in workflow
    assert "environment: integration" in workflow
