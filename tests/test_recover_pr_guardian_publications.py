from __future__ import annotations

from pathlib import Path

from company_brain.artifact_outbox import SqliteArtifactOutbox
from scripts import recover_pr_guardian_publications as recovery


def test_recovery_requires_a_github_token(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("EIP_GITHUB_TOKEN", raising=False)

    assert recovery.main(["--state-dir", str(tmp_path)]) == 2
    assert "requires EIP_GITHUB_TOKEN" in capsys.readouterr().err


def test_recovery_requires_an_existing_outbox(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("EIP_GITHUB_TOKEN", "test-token")

    assert recovery.main(["--state-dir", str(tmp_path)]) == 2
    assert "outbox was not found" in capsys.readouterr().err


def test_recovery_drains_a_bounded_number_of_due_deliveries(monkeypatch, tmp_path, capsys) -> None:
    outbox_path = tmp_path / "pr-guardian-publication-outbox.db"
    outbox_path.touch()
    monkeypatch.setenv("EIP_GITHUB_TOKEN", "test-token")

    class FakeClient:
        def __init__(self, token: str) -> None:
            assert token == "test-token"

    class FakePublisher:
        def __init__(self, client: FakeClient, outbox: SqliteArtifactOutbox) -> None:
            assert isinstance(client, FakeClient)
            assert outbox_path == Path(outbox.path)

        def deliver_pending(self, *, maximum_deliveries: int) -> int:
            assert maximum_deliveries == 7
            return 2

    monkeypatch.setattr(recovery, "GitHubRestPRClient", FakeClient)
    monkeypatch.setattr(recovery, "PRGuardianPublisher", FakePublisher)

    assert recovery.main(["--state-dir", str(tmp_path), "--maximum-deliveries", "7"]) == 0
    assert "deliveries_attempted=2" in capsys.readouterr().out
