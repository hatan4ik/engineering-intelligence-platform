"""Repository hygiene contracts that are cheap to regress and costly to rediscover."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ACTION_REFERENCE = re.compile(r"^\s*(?:-\s*)?uses:\s+[^@\s]+@([^\s#]+)", re.MULTILINE)


def test_external_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    failures: list[str] = []
    for workflow in sorted(workflow_dir.glob("*.y*ml")):
        for reference in ACTION_REFERENCE.findall(workflow.read_text()):
            if not FULL_SHA.fullmatch(reference):
                failures.append(f"{workflow.relative_to(ROOT)}: {reference}")

    assert not failures, "GitHub Actions must use immutable full commit SHAs:\n" + "\n".join(failures)


def test_eip_chart_app_version_matches_python_package_version() -> None:
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        project_version = tomllib.load(pyproject_file)["project"]["version"]

    chart_values: dict[str, str] = {}
    for line in (ROOT / "helm" / "eip" / "Chart.yaml").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"version", "appVersion"}:
            chart_values[key] = value.strip().strip('"')

    assert chart_values["version"], "The Helm chart needs its own package version."
    assert chart_values["appVersion"] == project_version


def test_completed_one_shot_document_migrations_are_not_kept_at_repository_root() -> None:
    retired_helpers = (
        "rewrite_links.py",
        "fix_design_target_state.py",
        "fix_temporal_alignment.py",
    )
    present = [name for name in retired_helpers if (ROOT / name).exists()]
    assert not present, "Retire completed one-shot helpers instead of preserving stale mutation paths: " + ", ".join(present)
