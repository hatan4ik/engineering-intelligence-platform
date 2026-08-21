from ingestion.chunkers import chunk_change
from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline


def make_change(content: str, commit: str = "abc", groups=("team-a",)) -> FileChange:
    return FileChange(
        source=SourceIdentity("github", "org/repo", "main", commit, "svc/app.py"),
        change_type=ChangeType.UPSERT,
        content=content,
        language="python",
        service="svc",
        owner="platform",
        acl=ACL(groups=groups),
    )


def test_python_ast_chunks_symbols():
    chunks = chunk_change(make_change("def a():\n    return 1\n\nclass B:\n    pass\n"))
    assert [c.symbol for c in chunks] == ["a", "B"]
    assert all(c.service == "svc" for c in chunks)


def test_pipeline_idempotent_and_acl_filtered():
    index = InMemoryIndex()
    pipeline = IngestionPipeline(index)
    event = NormalizedEvent("evt-1", (make_change("def secret():\n    return 'needle'\n"),))

    first = pipeline.process(event)
    second = pipeline.process(event)
    assert first["chunks"] == 1
    assert second["duplicate"] is True
    assert index.search("needle", ["team-a"])
    assert index.search("needle", ["team-b"]) == []


def test_replace_removes_stale_chunks():
    index = InMemoryIndex()
    pipeline = IngestionPipeline(index)
    pipeline.process(NormalizedEvent("evt-1", (make_change("def old():\n    return 'stale'\n", commit="1"),)))
    pipeline.process(NormalizedEvent("evt-2", (make_change("def new():\n    return 'fresh'\n", commit="2"),)))
    assert index.search("stale", ["team-a"]) == []
    assert index.search("fresh", ["team-a"])


def test_delete_reconciles_document():
    index = InMemoryIndex()
    pipeline = IngestionPipeline(index)
    original = make_change("def gone():\n    return 'gone'\n")
    pipeline.process(NormalizedEvent("evt-1", (original,)))
    deleted = FileChange(source=original.source, change_type=ChangeType.DELETE, acl=original.acl)
    result = pipeline.process(NormalizedEvent("evt-2", (deleted,)))
    assert result["deleted"] == 1
    assert index.search("gone", ["team-a"]) == []
