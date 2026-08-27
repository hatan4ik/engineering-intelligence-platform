"""A file the runner could not read is named in the run output, not silently counted."""
from __future__ import annotations

import ingestion.runner as runner
from ingestion.index import InMemoryIndex


def test_failed_paths_lists_every_unreadable_file(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# readme\n\nhello world\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# guide\n\nmore words\n", encoding="utf-8")
    (root / "docs" / "ok.md").write_text("# ok\n\nfine\n", encoding="utf-8")

    real_read = runner._read_text

    def exploding_read(path, limit):
        if path.name in {"README.md", "guide.md"}:
            raise OSError("permission denied")
        return real_read(path, limit)

    monkeypatch.setattr(runner, "_read_text", exploding_read)
    counts = runner.ingest_checkout(
        root,
        repository="acme/platform",
        branch="main",
        commit_sha="abc123",
        index=InMemoryIndex(),
        ledger_path=tmp_path / "ledger.db",
        groups=["engineering"],
    )

    assert counts["failed"] == 2
    assert counts["failed_paths"] == ["README.md", "docs/guide.md"]
    assert counts["documents"] == 1


def test_a_clean_run_reports_an_empty_failed_paths_list(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "README.md").write_text("# readme\n\nhello\n", encoding="utf-8")
    counts = runner.ingest_checkout(
        root,
        repository="acme/platform",
        branch="main",
        commit_sha="abc123",
        index=InMemoryIndex(),
        ledger_path=tmp_path / "ledger.db",
        groups=["engineering"],
    )
    assert counts["failed"] == 0
    assert counts["failed_paths"] == []
