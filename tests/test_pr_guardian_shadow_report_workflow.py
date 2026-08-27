"""The shadow-report download step, exercised with a fake ``gh`` on PATH.

No network and no GitHub: the tests stub ``gh`` with a shell script so the real
failure modes (no runs, an expired artifact, a token without ``actions: read``)
are distinguishable behaviors rather than assumptions.
"""

import os
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_SCRIPT = REPOSITORY_ROOT / "scripts" / "download_pr_guardian_shadow_outcomes.sh"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "pr-guardian-shadow-report.yml"

NO_ARTIFACT_STDERR = "no artifact matches any of the names or patterns provided"
FORBIDDEN_STDERR = "HTTP 403: Resource not accessible by integration"


def _fake_gh(tmp_path, *, run_ids, download):
    """Install a fake ``gh`` whose ``run download`` behavior is ``download``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "run" ] && [ "$2" = "list" ]; then\n'
        f"  printf '%s' '{run_ids}'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "run" ] && [ "$2" = "download" ]; then\n'
        "  dir=''\n"
        "  while [ $# -gt 0 ]; do\n"
        '    if [ "$1" = "--dir" ]; then dir="$2"; fi\n'
        "    shift\n"
        "  done\n"
        f"{download}"
        "fi\n"
        'echo "unexpected gh invocation: $*" >&2\n'
        "exit 64\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return bin_dir


def _run(tmp_path, bin_dir):
    output = tmp_path / "github-output"
    summary = tmp_path / "github-step-summary"
    output.touch()
    summary.touch()
    result = subprocess.run(
        ["bash", str(DOWNLOAD_SCRIPT), str(tmp_path / "shadow-outcomes")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "HOME": str(tmp_path),
        },
    )
    return result, output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")


def test_no_runs_reports_zero_without_fabricating_a_report(tmp_path):
    bin_dir = _fake_gh(tmp_path, run_ids="", download="  exit 0\n")
    result, output, summary = _run(tmp_path, bin_dir)
    assert result.returncode == 0, result.stderr
    assert "count=0" in output
    assert "No retained" in summary
    assert "not a result" in summary


def test_an_expired_artifact_is_skipped_rather_than_failing_the_report(tmp_path):
    bin_dir = _fake_gh(
        tmp_path,
        run_ids="101 102",
        download=f'  echo "{NO_ARTIFACT_STDERR}" >&2\n  exit 1\n',
    )
    result, output, summary = _run(tmp_path, bin_dir)
    assert result.returncode == 0, result.stderr
    assert "count=0" in output
    assert "No retained" in summary


def test_a_hard_download_failure_fails_the_step(tmp_path):
    bin_dir = _fake_gh(
        tmp_path,
        run_ids="101",
        download=f'  echo "{FORBIDDEN_STDERR}" >&2\n  exit 1\n',
    )
    result, output, summary = _run(tmp_path, bin_dir)
    assert result.returncode != 0
    assert "403" in result.stderr
    # A hard failure must not be laundered into an empty-but-green pilot report.
    assert "count=" not in output
    assert summary == ""


def test_a_listing_failure_fails_the_step(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\necho "{FORBIDDEN_STDERR}" >&2\nexit 1\n', encoding="utf-8")
    gh.chmod(0o755)
    result, output, summary = _run(tmp_path, bin_dir)
    assert result.returncode != 0
    assert "count=" not in output
    assert summary == ""


def test_downloaded_artifacts_are_counted(tmp_path):
    bin_dir = _fake_gh(
        tmp_path,
        run_ids="101 102",
        download='  mkdir -p "$dir"\n  echo "{}" > "$dir/pr-guardian-shadow-outcome.json"\n  exit 0\n',
    )
    result, output, summary = _run(tmp_path, bin_dir)
    assert result.returncode == 0, result.stderr
    assert "count=2" in output
    assert summary == ""


def test_workflow_wires_the_script_and_uses_the_real_actions_variables():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    # GITHUB_STEP_OUTPUT does not exist; under `set -u` it would abort the step
    # and skip every step gated on the count.
    assert "GITHUB_STEP_OUTPUT" not in workflow
    assert "$GITHUB_OUTPUT" in DOWNLOAD_SCRIPT.read_text(encoding="utf-8")
    assert "bash scripts/download_pr_guardian_shadow_outcomes.sh" in workflow
    assert "steps.download.outputs.count != '0'" in workflow


def test_run_listing_filters_by_event_rather_than_branch():
    script = DOWNLOAD_SCRIPT.read_text(encoding="utf-8")
    assert "--event pull_request_target" in script
    assert "--branch" not in script
