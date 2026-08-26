"""The knowledge-ingest workflow gives ingestion its first CI trigger."""
from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "knowledge-ingest.yml"
SKIP_NOTICE = "Azure index not configured for this repository — skipped"


def test_the_workflow_exists():
    assert WORKFLOW.is_file()


def test_it_is_triggered_by_dispatch_with_an_in_memory_default_and_by_push():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "index:" in workflow
    assert "default: in-memory" in workflow
    assert "push:" in workflow
    assert "branches: [main]" in workflow


def test_the_in_memory_smoke_runs_the_real_cli():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/ingest_repository.py" in workflow
    assert "--index in-memory" in workflow


def test_both_jobs_pass_branch_identity_and_commit_provenance_separately():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("--branch main") == 2
    assert workflow.count('--commit-sha "${{ github.sha }}"') == 2
    # The single --ref flag keyed document identity by commit sha, which made
    # every commit a new document instead of replacing the branch's document.
    assert "--ref " not in workflow


def test_the_azure_path_reports_when_it_is_not_configured():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert SKIP_NOTICE in workflow
    assert "steps.azure_config.outputs.configured" in workflow
    assert "--index azure" in workflow


def test_the_azure_job_can_actually_acquire_a_federated_token():
    """A workload-identity run needs id-token: write and an azure/login step."""

    workflow = WORKFLOW.read_text(encoding="utf-8")
    header = workflow.split("jobs:", 1)[0]
    azure_job = workflow.split("  azure:", 1)[1]

    assert "id-token: write" in header
    assert "uses: azure/login@v2" in azure_job
    assert "client-id: ${{ secrets.AZURE_CLIENT_ID }}" in azure_job
    assert "tenant-id: ${{ secrets.AZURE_TENANT_ID }}" in azure_job
    assert "subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}" in azure_job


def test_the_configuration_gate_requires_the_full_identity_set_or_an_api_key():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = workflow.split("id: azure_config", 1)[1].split("- name:", 1)[0]

    for name in ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX", "AZURE_SEARCH_API_KEY"):
        assert f'"${name}"' in gate or f"${name}" in gate
    # A client id on its own passed the old gate and then failed at token
    # acquisition; the federated path needs the whole triple.
    assert "AZURE_TENANT_ID" in gate
    assert "AZURE_SUBSCRIPTION_ID" in gate


def test_the_smoke_job_keeps_read_only_permissions():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    smoke_job = workflow.split("  in-memory:", 1)[1].split("  azure:", 1)[0]

    assert "contents: read" in smoke_job
    assert "id-token" not in smoke_job
