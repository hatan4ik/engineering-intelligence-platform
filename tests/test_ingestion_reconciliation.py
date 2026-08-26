from __future__ import annotations

from ingestion.catalog import SourceScope, SqliteSourceCatalog
from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline
from ingestion.reconciliation import SourceReconciler
from ingestion.worker import sqlite_worker


def change(path: str, *, commit: str, content: str, groups: tuple[str, ...] = ("payments",)) -> FileChange:
    return FileChange(
        source=SourceIdentity("github", "acme/payments", "main", commit, path),
        change_type=ChangeType.UPSERT,
        content=content,
        language="python",
        acl=ACL(groups=groups),
        service="payments",
    )


def test_reconciliation_updates_acl_content_and_deletes_absent_sources(tmp_path):
    index = InMemoryIndex()
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(index, catalog=catalog)
    pipeline.process(
        NormalizedEvent(
            "evt-1",
            (
                change("payments.py", commit="one", content="def old(): return 'stale'"),
                change("legacy.py", commit="one", content="def legacy(): return 'remove-me'"),
            ),
        )
    )
    reconciler = SourceReconciler(pipeline, catalog)
    scope = SourceScope("github", "acme/payments", "main")
    manifest = (
        change("payments.py", commit="two", content="def current(): return 'fresh'", groups=("platform",)),
        change("new.py", commit="two", content="def added(): return 'new'", groups=("platform",)),
    )

    result = reconciler.reconcile(scope, manifest)

    assert (result.upserted, result.deleted, result.unchanged) == (2, 1, 0)
    assert index.search("stale", ["payments"]) == []
    assert index.search("fresh", ["payments"]) == []
    assert index.search("fresh", ["platform"])
    assert index.search("remove-me", ["payments"]) == []
    assert catalog.get(manifest[0].source.document_id).state == "active"
    assert catalog.get("github:acme/payments:main:legacy.py").state == "deleted"

    repeat = reconciler.reconcile(scope, manifest)
    assert (repeat.upserted, repeat.deleted, repeat.unchanged) == (0, 0, 2)


def test_reconciliation_repairs_a_missing_index_document_from_catalog(tmp_path):
    index = InMemoryIndex()
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(index, catalog=catalog)
    current = change("payments.py", commit="one", content="def payment(): return 'healthy'")
    pipeline.process(NormalizedEvent("evt-1", (current,)))
    index.delete_document(current.source.document_id)  # Simulated index drift, not source deletion.

    result = SourceReconciler(pipeline, catalog).reconcile(
        SourceScope("github", "acme/payments", "main"), (current,)
    )

    assert (result.upserted, result.deleted, result.unchanged) == (1, 0, 0)
    assert index.search("healthy", ["payments"])


def test_sqlite_worker_uses_a_durable_source_catalog_by_default(tmp_path):
    worker = sqlite_worker(IngestionPipeline(InMemoryIndex()), str(tmp_path / "ledger.db"))
    event = NormalizedEvent("evt-1", (change("payments.py", commit="one", content="def payment(): pass"),))

    worker.handle(event)

    assert worker.pipeline.catalog is not None
    assert worker.pipeline.catalog.get(event.changes[0].source.document_id).last_event_id == "evt-1"


def test_catalog_does_not_advance_when_index_write_fails(tmp_path):
    class BrokenIndex(InMemoryIndex):
        def replace_document(self, document_id, chunks):
            raise RuntimeError("index unavailable")

    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(BrokenIndex(), catalog=catalog)
    item = change("payments.py", commit="one", content="def payment(): pass")

    try:
        pipeline.process(NormalizedEvent("evt-1", (item,)))
        assert False, "the index failure must propagate"
    except RuntimeError as exc:
        assert "index unavailable" in str(exc)
    assert catalog.get(item.source.document_id) is None


def test_reconciliation_rejects_cross_scope_manifests(tmp_path):
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(InMemoryIndex(), catalog=catalog)
    reconciler = SourceReconciler(pipeline, catalog)
    foreign = FileChange(
        source=SourceIdentity("github", "acme/other", "main", "one", "other.py"),
        change_type=ChangeType.UPSERT,
        content="def other(): pass",
    )

    try:
        reconciler.reconcile(SourceScope("github", "acme/payments", "main"), (foreign,))
        assert False, "a manifest must not escape its authorized source scope"
    except ValueError as exc:
        assert "cross source scope" in str(exc)
