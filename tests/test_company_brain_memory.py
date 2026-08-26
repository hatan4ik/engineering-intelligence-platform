from datetime import datetime, timezone

import pytest

from company_brain import (
    BrainPrincipal,
    CompanyBrainMemoryError,
    CompanyBrainMemoryProjector,
    ProjectionState,
    RelationshipKind,
    SqliteBrainProjectionJournal,
    SqliteCompanyBrainStore,
)
from company_brain.projector import repository_id, service_id
from ingestion.catalog import SourceScope, SqliteSourceCatalog
from ingestion.documents import KnowledgeChange, KnowledgeDocument, KnowledgeIdentity, KnowledgeSourceType
from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.knowledge_pipeline import InMemoryKnowledgeIndex, KnowledgePipeline
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline
from ingestion.reconciliation import SourceReconciler


TENANT = "tenant-acme"


def change(
    path: str,
    *,
    commit: str,
    groups: tuple[str, ...] = ("payments",),
    content: str = "def payment(): return 'healthy'",
) -> FileChange:
    return FileChange(
        source=SourceIdentity("github", "acme/payments", "main", commit, path),
        change_type=ChangeType.UPSERT,
        content=content,
        language="python",
        service="payments",
        owner="team-payments",
        acl=ACL(groups=groups),
    )


def memory(tmp_path) -> tuple[SqliteCompanyBrainStore, SqliteBrainProjectionJournal, CompanyBrainMemoryProjector]:
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    journal = SqliteBrainProjectionJournal(tmp_path / "projection-journal.db")
    return store, journal, CompanyBrainMemoryProjector(store, journal, TENANT)


def test_file_ingestion_writes_after_index_success_and_replays_idempotently(tmp_path):
    store, journal, projector = memory(tmp_path)
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(InMemoryIndex(), catalog=catalog, brain_memory_projector=projector)
    item = change("payments.py", commit="one")

    result = pipeline.process(NormalizedEvent("evt-1", (item,)))

    assert result["upserted"] == 1
    projection = journal.get(TENANT, f"file:{item.source.document_id}")
    assert projection is not None and projection.state is ProjectionState.ACTIVE
    snapshot = store.snapshot(TENANT)
    context = snapshot.context_for_change(
        repository_id=repository_id(provider="github", repository="acme/payments"),
        changed_services=(service_id("payments"),),
        principal=BrainPrincipal(groups=("payments",)),
    )
    assert len(context.evidence) == 1
    before_events = len(store.audit_events(TENANT))

    replay = projector.project_file_change(item, event_id="evt-1")

    assert replay.duplicate is True
    assert len(store.audit_events(TENANT)) == before_events


def test_failed_index_write_does_not_create_a_brain_projection_or_advance_catalog(tmp_path):
    class BrokenIndex(InMemoryIndex):
        def replace_document(self, document_id, chunks):
            raise RuntimeError("index unavailable")

    store, journal, projector = memory(tmp_path)
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(BrokenIndex(), catalog=catalog, brain_memory_projector=projector)
    item = change("payments.py", commit="one")

    with pytest.raises(RuntimeError, match="index unavailable"):
        pipeline.process(NormalizedEvent("evt-1", (item,)))

    assert catalog.get(item.source.document_id) is None
    assert journal.get(TENANT, f"file:{item.source.document_id}") is None
    assert store.get_entity(TENANT, service_id("payments")) is None


def test_reconciliation_replaces_acl_membership_and_propagates_source_deletion(tmp_path):
    store, journal, projector = memory(tmp_path)
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(InMemoryIndex(), catalog=catalog, brain_memory_projector=projector)
    original = change("payments.py", commit="one", groups=("payments",))
    pipeline.process(NormalizedEvent("evt-1", (original,)))
    reconciler = SourceReconciler(pipeline, catalog)
    scope = SourceScope("github", "acme/payments", "main")
    updated = change("payments.py", commit="two", groups=("platform",), content="def payment(): return 'current'")

    result = reconciler.reconcile(scope, (updated,))

    assert (result.upserted, result.deleted) == (1, 0)
    old_evidence = "evidence:github:acme/payments:main:one:payments.py"
    new_evidence = "evidence:github:acme/payments:main:two:payments.py"
    assert store.get_evidence(TENANT, old_evidence) is None
    assert store.get_evidence(TENANT, old_evidence, include_deleted=True).deleted_at is not None
    snapshot = store.snapshot(TENANT)
    platform = snapshot.context_for_change(
        repository_id=repository_id(provider="github", repository="acme/payments"),
        changed_services=(service_id("payments"),),
        principal=BrainPrincipal(groups=("platform",)),
    )
    denied = snapshot.context_for_change(
        repository_id=repository_id(provider="github", repository="acme/payments"),
        changed_services=(service_id("payments",)),
        principal=BrainPrincipal(groups=("payments",)),
    )
    assert [item.evidence_id for item in platform.evidence] == [new_evidence]
    assert denied.evidence == ()

    deletion = reconciler.reconcile(scope, ())

    assert deletion.deleted == 1
    projection = journal.get(TENANT, f"file:{updated.source.document_id}")
    assert projection.state is ProjectionState.DELETED
    assert store.get_evidence(TENANT, new_evidence) is None
    assert "change:github:acme/payments:main:two:payments.py" not in store.snapshot(TENANT).entities


def test_deleting_one_source_keeps_shared_edges_backed_by_another_source(tmp_path):
    store, _, projector = memory(tmp_path)
    catalog = SqliteSourceCatalog(tmp_path / "sources.db")
    pipeline = IngestionPipeline(InMemoryIndex(), catalog=catalog, brain_memory_projector=projector)
    first = change("first.py", commit="one")
    second = change("second.py", commit="one")
    pipeline.process(NormalizedEvent("evt-1", (first, second)))
    reconciler = SourceReconciler(pipeline, catalog)

    reconciler.reconcile(SourceScope("github", "acme/payments", "main"), (second,))

    relationship = store.get_relationship(
        TENANT,
        source_id=service_id("payments"),
        target_id=repository_id(provider="github", repository="acme/payments"),
        kind=RelationshipKind.BELONGS_TO,
    )
    assert relationship is not None
    assert relationship.relationship.evidence_ids == ("evidence:github:acme/payments:main:one:second.py",)
    assert store.get_evidence(TENANT, "evidence:github:acme/payments:main:one:first.py") is None


def test_knowledge_pipeline_replays_missing_projection_and_propagates_deletion(tmp_path):
    store, journal, projector = memory(tmp_path)
    document = KnowledgeDocument(
        identity=KnowledgeIdentity("confluence", KnowledgeSourceType.ADR, "adr-42"),
        title="Payments API boundary",
        body="All access uses the Payments API.",
        revision="2",
        updated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        service="payments",
        acl=ACL(groups=("platform",)),
    )
    pipeline = KnowledgePipeline(InMemoryKnowledgeIndex(), brain_memory_projector=projector)

    indexed = pipeline.process(KnowledgeChange(ChangeType.UPSERT, document), event_id="knowledge-1")
    replay = pipeline.process(KnowledgeChange(ChangeType.UPSERT, document), event_id="knowledge-1")

    assert indexed["status"] == "indexed"
    assert replay["status"] == "duplicate"
    assert "adr:confluence:adr-42" in store.snapshot(TENANT).entities
    deleted = pipeline.process(KnowledgeChange(ChangeType.DELETE, document), event_id="knowledge-2")
    projection = journal.get(TENANT, f"knowledge:{document.identity.document_id}")
    assert deleted["status"] == "deleted"
    assert projection.state is ProjectionState.DELETED
    assert "adr:confluence:adr-42" not in store.snapshot(TENANT).entities


def test_source_event_id_cannot_be_reused_for_different_content(tmp_path):
    _, _, projector = memory(tmp_path)
    projector.project_file_change(change("payments.py", commit="one"), event_id="evt-1")

    with pytest.raises(CompanyBrainMemoryError, match="cannot project different state or content"):
        projector.project_file_change(
            change("payments.py", commit="two", content="def payment(): return 'changed'"),
            event_id="evt-1",
        )
