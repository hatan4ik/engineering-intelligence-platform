"""The trusted publisher must reach its fail-soft missing-artifact path."""
from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "pr-guardian-shadow-publish.yml"
)


def test_missing_evaluation_artifact_does_not_stop_the_trusted_publisher():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    download_start = workflow.index("- name: Download the untrusted evaluation observation")
    next_step = workflow.index("      - name:", download_start + 1)
    download_step = workflow[download_start:next_step]
    assert "id: download_observation" in download_step
    assert "continue-on-error: true" in download_step
    assert "actions/download-artifact" in download_step
    assert "EIP_PR_GUARDIAN_RESULT_PATH: shadow-input/pr-guardian-shadow-result.json" in workflow
    assert "python scripts/publish_pr_guardian_shadow.py" in workflow
