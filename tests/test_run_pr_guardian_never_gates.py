"""The read-only evaluate job is never the merge gate: ``main()`` always returns 0."""
from __future__ import annotations

import json

from scripts import run_pr_guardian


def _event(tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({
            "action": "opened",
            "number": 7,
            "repository": {"full_name": "acme/platform"},
            "pull_request": {"head": {"sha": "deadbeef"}},
        }),
        encoding="utf-8",
    )
    return event_path


def test_an_unexpected_failure_is_reported_and_still_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(_event(tmp_path)))
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("EIP_PR_GUARDIAN_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))

    def explode(*args, **kwargs):
        raise RuntimeError("service graph exploded")

    monkeypatch.setattr(run_pr_guardian, "build_service_graph_from_checkout", explode)

    assert run_pr_guardian.main() == 0
    err = capsys.readouterr().err
    assert "evaluation failed" in err
    assert "service graph exploded" in err
    assert "not a gate" in err


def test_missing_environment_is_reported_and_still_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert run_pr_guardian.main() == 0
    assert "GITHUB_EVENT_PATH and GITHUB_TOKEN are required" in capsys.readouterr().err
