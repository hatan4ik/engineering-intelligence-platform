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


def test_the_azure_path_reports_when_it_is_not_configured():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert SKIP_NOTICE in workflow
    assert "steps.azure_config.outputs.configured" in workflow
    assert "--index azure" in workflow


def test_the_workflow_never_grants_write_permissions():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    permissions = workflow.split("permissions:", 1)[1].split("jobs:", 1)[0]

    assert "contents: read" in permissions
    assert ": write" not in permissions
