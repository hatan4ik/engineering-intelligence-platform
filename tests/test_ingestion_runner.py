"""The knowledge plane's first runtime path: ingest a checked-out repository."""
from __future__ import annotations

import json

import pytest

from ingestion.index import InMemoryIndex
from ingestion.runner import ingest_checkout


def _checkout(root):
    root.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "service.py").write_text(
        "def handler():\n    return 1\n\n\nclass Worker:\n    pass\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Title\n\nA paragraph of prose.\n", encoding="utf-8")
    (root / "artifact.bin").write_bytes(b"\x00\x01\x02\x03")
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    return root


def _run(root, index, ledger, *, branch="main", commit_sha="a" * 40, groups=("engineering",)):
    return ingest_checkout(
        root,
        repository="acme/platform",
        branch=branch,
        commit_sha=commit_sha,
        index=index,
        ledger_path=ledger,
        groups=groups,
    )


def test_first_run_indexes_every_eligible_file(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()

    counts = _run(root, index, tmp_path / "ledger.db")

    assert counts["documents"] == 2
    assert counts["chunks"] >= 3
    assert counts["failed"] == 0
    assert counts["skipped"] == 1  # artifact.bin is not an ingestible source file
    assert set(index.documents) == {
        "git:acme/platform:main:README.md",
        "git:acme/platform:main:src/service.py",
    }


def test_git_directory_is_never_walked(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()

    _run(root, index, tmp_path / "ledger.db")

    assert not any(".git" in document_id for document_id in index.documents)


def test_rerunning_over_an_unchanged_checkout_is_idempotent(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()
    ledger = tmp_path / "ledger.db"

    first = _run(root, index, ledger)
    second = _run(root, index, ledger)

    assert second["documents"] == 0
    assert second["chunks"] == 0
    assert second["duplicates"] == first["documents"]
    assert len(index.documents) == 2


def test_a_changed_file_is_reingested(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()
    ledger = tmp_path / "ledger.db"
    _run(root, index, ledger)

    (root / "README.md").write_text("# Title\n\nRewritten prose.\n", encoding="utf-8")
    second = _run(root, index, ledger)

    assert second["documents"] == 1
    assert second["duplicates"] == 1
    chunks = index.documents["git:acme/platform:main:README.md"]
    assert "Rewritten prose." in chunks[0].content


def test_indexed_chunks_carry_the_requested_and_repository_acl_groups(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()

    _run(root, index, tmp_path / "ledger.db", groups=("engineering",))

    chunk = next(iter(index.documents.values()))[0]
    assert chunk.acl.groups == ("repo:acme/platform:read", "engineering")
    assert index.search("paragraph", groups=["engineering"])
    assert index.search("paragraph", groups=["finance"]) == []


def test_empty_group_list_is_refused_rather_than_indexing_world_readable_chunks(tmp_path):
    root = _checkout(tmp_path / "checkout")

    with pytest.raises(ValueError) as error:
        _run(root, InMemoryIndex(), tmp_path / "ledger.db", groups=())

    assert "groups" in str(error.value)


def test_unreadable_file_is_counted_as_failed_without_aborting_the_run(tmp_path, monkeypatch):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()

    import ingestion.runner as runner

    real_read = runner._read_text

    def exploding_read(path, limit):
        if path.name == "README.md":
            raise OSError("permission denied")
        return real_read(path, limit)

    monkeypatch.setattr(runner, "_read_text", exploding_read)
    counts = _run(root, index, tmp_path / "ledger.db")

    assert counts["failed"] == 1
    assert counts["documents"] == 1


def test_oversize_files_are_skipped(tmp_path):
    root = _checkout(tmp_path / "checkout")
    (root / "huge.md").write_text("x" * 10_000, encoding="utf-8")
    index = InMemoryIndex()

    counts = ingest_checkout(
        root,
        repository="acme/platform",
        branch="main",
        commit_sha="b" * 40,
        index=index,
        ledger_path=tmp_path / "ledger.db",
        groups=("engineering",),
        max_file_bytes=1000,
    )

    assert counts["skipped"] == 2  # artifact.bin and huge.md
    assert not any("huge.md" in document_id for document_id in index.documents)


def test_counts_are_json_serialisable(tmp_path):
    root = _checkout(tmp_path / "checkout")
    counts = _run(root, InMemoryIndex(), tmp_path / "ledger.db")

    assert json.loads(json.dumps(counts))["documents"] == 2


def test_a_later_commit_replaces_the_changed_document_instead_of_duplicating_it(tmp_path):
    """Document identity is the branch; the commit sha is provenance only."""

    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()
    ledger = tmp_path / "ledger.db"

    _run(root, index, ledger, commit_sha="a" * 40)
    (root / "README.md").write_text("# Title\n\nSecond commit prose.\n", encoding="utf-8")
    second = _run(root, index, ledger, commit_sha="f" * 40)

    assert second["documents"] == 1
    assert second["duplicates"] == 1
    # Still two documents, not four: the same document_id was replaced.
    assert set(index.documents) == {
        "git:acme/platform:main:README.md",
        "git:acme/platform:main:src/service.py",
    }
    readme = index.documents["git:acme/platform:main:README.md"]
    assert len(readme) == 1
    assert "Second commit prose." in readme[0].content
    assert readme[0].source.commit_sha == "f" * 40
    assert readme[0].source.citation == "git:acme/platform@" + "f" * 40 + ":README.md"
    # The unchanged file keeps the commit its content actually came from.
    service = index.documents["git:acme/platform:main:src/service.py"]
    assert service[0].source.commit_sha == "a" * 40


def test_a_different_branch_is_a_different_document(tmp_path):
    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()
    ledger = tmp_path / "ledger.db"

    _run(root, index, ledger, branch="main")
    _run(root, index, ledger, branch="release-1")

    assert "git:acme/platform:main:README.md" in index.documents
    assert "git:acme/platform:release-1:README.md" in index.documents


@pytest.mark.parametrize("field", ["branch", "commit_sha"])
def test_blank_identity_fields_are_refused(tmp_path, field):
    root = _checkout(tmp_path / "checkout")

    with pytest.raises(ValueError) as error:
        _run(root, InMemoryIndex(), tmp_path / "ledger.db", **{field: "  "})

    assert field in str(error.value)


def test_an_acl_change_propagates_on_re_ingest(tmp_path):
    """PRODUCTION-EVIDENCE.md requires an ACL change to propagate, so the ACL is
    part of the idempotency key — otherwise the ledger would dedupe it away."""

    root = _checkout(tmp_path / "checkout")
    index = InMemoryIndex()
    ledger = tmp_path / "ledger.db"

    _run(root, index, ledger, groups=("engineering",))
    second = _run(root, index, ledger, groups=("platform-security",))

    assert second["documents"] == 2
    assert second["duplicates"] == 0
    chunk = index.documents["git:acme/platform:main:README.md"][0]
    assert chunk.acl.groups == ("repo:acme/platform:read", "platform-security")
    assert index.search("paragraph", groups=["engineering"]) == []
    assert index.search("paragraph", groups=["platform-security"])
