"""A comment-permission failure must not discard a captured shadow outcome."""

from __future__ import annotations

import json

from integrations.github.pr_guardian import GitHubAPIError
from scripts import capture_pr_guardian_shadow_outcome as capture


class _CommentRefusingClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def latest_comment_with_marker(self, **_: object) -> None:
        return None

    def publish_sticky_comment(self, **_: object) -> None:
        raise GitHubAPIError("write permission denied", 403)


def test_comment_permission_failure_is_fail_soft_after_outcome_is_written(monkeypatch, tmp_path, capsys):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "closed",
                "number": 42,
                "repository": {"full_name": "acme/payments"},
                "pull_request": {
                    "number": 42,
                    "merged": True,
                    "head": {"sha": "deadbeef"},
                    "labels": [],
                },
            }
        ),
        encoding="utf-8",
    )
    outcome_path = tmp_path / "outcome.json"
    monkeypatch.setattr(capture, "GitHubRestPRClient", _CommentRefusingClient)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/payments")
    monkeypatch.setenv("EIP_PR_GUARDIAN_OUTCOME_PATH", str(outcome_path))

    assert capture.main() == 0
    assert json.loads(outcome_path.read_text(encoding="utf-8"))["closure"]["merged"] is True
    captured = capsys.readouterr()
    assert "not-published" in captured.out
    assert "retained artifact remains authoritative" in captured.err
