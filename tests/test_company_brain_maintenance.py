from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from company_brain import (
    BrainEntity,
    BrainProvenance,
    CompanyBrainMaintenanceError,
    CompanyBrainStoreError,
    EntityKind,
    MemoryMaintenanceAction,
    MemoryMaintenanceFindingKind,
    SqliteCompanyBrainStore,
    plan_company_brain_maintenance,
)
from company_brain.model import BrainRelationship, RelationshipKind
from scripts.plan_company_brain_maintenance import main


TENANT = "tenant-acme"
AS_OF = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def provenance(record: str, revision: str) -> BrainProvenance:
    return BrainProvenance(
        source_system="confluence",
        source_record_id=record,
        source_revision=revision,
        observed_at=AS_OF,
        event_id=f"event:{record}:{revision}",
    )


def put_knowledge(
    store: SqliteCompanyBrainStore,
    *,
    tenant: str = TENANT,
    source_id: str,
    kind: EntityKind,
    title: str,
    revision: str,
    source_updated_at: datetime | str | None,
    owner: str | None = None,
):
    attributes = [
        ("provider", "confluence"),
        ("revision", revision),
        ("source_type", kind.value),
    ]
    if source_updated_at is not None:
        timestamp = (
            source_updated_at.isoformat()
            if isinstance(source_updated_at, datetime)
            else source_updated_at
        )
        attributes.append(("source_updated_at", timestamp))
    stored = store.put_entity(
        tenant,
        BrainEntity(source_id, kind, title, attributes=tuple(sorted(attributes))),
        provenance=provenance(source_id, revision),
    )
    if owner is None:
        return stored
    owner_id = f"owner:{owner}"
    if store.get_entity(tenant, owner_id) is None:
        store.put_entity(
            tenant,
            BrainEntity(owner_id, EntityKind.OWNER, owner),
            provenance=provenance(owner_id, "v1"),
        )
    store.put_relationship(
        tenant,
        BrainRelationship(owner_id, source_id, RelationshipKind.OWNS),
        provenance=provenance(f"{owner_id}:{source_id}", "v1"),
    )
    return stored


def database_files(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in path.parent.glob(f"{path.name}*")}


def test_read_only_memory_maintenance_uses_source_freshness_and_owner_edges_without_writing(
    tmp_path,
):
    database = tmp_path / "brain.db"
    store = SqliteCompanyBrainStore(database)
    put_knowledge(
        store,
        source_id="runbook:payments",
        kind=EntityKind.RUNBOOK,
        title="Restart payments",
        revision="7",
        source_updated_at=AS_OF - timedelta(days=365),
    )
    put_knowledge(
        store,
        source_id="adr:payments:v1",
        kind=EntityKind.ADR,
        title="Payments queue",
        revision="1",
        source_updated_at=AS_OF - timedelta(days=4),
        owner="team-payments",
    )
    put_knowledge(
        store,
        source_id="adr:payments:v2",
        kind=EntityKind.ADR,
        title="Payments queue",
        revision="2",
        source_updated_at=AS_OF - timedelta(days=2),
        owner="team-payments",
    )
    put_knowledge(
        store,
        source_id="document:missing-freshness",
        kind=EntityKind.DOCUMENT,
        title="Escalation policy",
        revision="3",
        source_updated_at=None,
        owner="team-platform",
    )
    put_knowledge(
        store,
        source_id="incident:historical",
        kind=EntityKind.INCIDENT,
        title="Historical incident",
        revision="1",
        source_updated_at=AS_OF - timedelta(days=365),
    )
    deleted = put_knowledge(
        store,
        source_id="document:deleted",
        kind=EntityKind.DOCUMENT,
        title="Deleted document",
        revision="1",
        source_updated_at=AS_OF - timedelta(days=365),
    )
    store.delete_entity(
        TENANT,
        "document:deleted",
        expected_version=deleted.version,
        reason="source deletion reconciled",
        deleted_at=AS_OF,
    )
    put_knowledge(
        store,
        tenant="tenant-other",
        source_id="runbook:other",
        kind=EntityKind.RUNBOOK,
        title="Other tenant runbook",
        revision="1",
        source_updated_at=AS_OF - timedelta(days=365),
    )

    before = database_files(database)
    reader = SqliteCompanyBrainStore.open_read_only(database)
    plan = plan_company_brain_maintenance(reader, tenant_id=TENANT, as_of=AS_OF)
    repeat = plan_company_brain_maintenance(reader, tenant_id=TENANT, as_of=AS_OF)
    with pytest.raises(sqlite3.OperationalError, match="read-only reference database"):
        reader.put_entity(
            TENANT,
            BrainEntity(
                "document:must-not-write", EntityKind.DOCUMENT, "Must not write"
            ),
            provenance=provenance("document:must-not-write", "1"),
        )

    assert database_files(database) == before
    assert plan == repeat
    assert plan.assessed_source_count == 4
    assert {(item.source_id, item.action) for item in plan.proposals} == {
        ("runbook:payments", MemoryMaintenanceAction.REQUEST_OWNER_REVIEW),
        ("runbook:payments", MemoryMaintenanceAction.ASSIGN_ACCOUNTABLE_OWNER),
        (
            "adr:payments:v1",
            MemoryMaintenanceAction.RESOLVE_CONFLICTING_ACTIVE_REVISIONS,
        ),
        (
            "adr:payments:v2",
            MemoryMaintenanceAction.RESOLVE_CONFLICTING_ACTIVE_REVISIONS,
        ),
        (
            "document:missing-freshness",
            MemoryMaintenanceAction.REPAIR_SOURCE_FRESHNESS_METADATA,
        ),
    }
    assert all(item.requires_human_review for item in plan.proposals)
    assert all(item.source_id != "runbook:other" for item in plan.proposals)
    missing_freshness = next(
        item
        for item in plan.proposals
        if item.finding_kind is MemoryMaintenanceFindingKind.MISSING_SOURCE_FRESHNESS
    )
    assert missing_freshness.source_revision == "3"
    assert missing_freshness.source_version == 1
    assert plan.to_payload()["mode"] == "review-only"


def test_decay_only_compares_documents_with_the_same_source_type(tmp_path):
    database = tmp_path / "brain.db"
    store = SqliteCompanyBrainStore(database)
    put_knowledge(
        store,
        source_id="adr:shared-title",
        kind=EntityKind.ADR,
        title="Shared title",
        revision="1",
        source_updated_at=AS_OF,
        owner="team-platform",
    )
    put_knowledge(
        store,
        source_id="runbook:shared-title",
        kind=EntityKind.RUNBOOK,
        title="Shared title",
        revision="2",
        source_updated_at=AS_OF,
        owner="team-platform",
    )

    plan = plan_company_brain_maintenance(
        SqliteCompanyBrainStore.open_read_only(database),
        tenant_id=TENANT,
        as_of=AS_OF,
    )

    assert plan.proposals == ()


def test_missing_source_freshness_never_uses_projection_write_time_as_a_staleness_proxy(
    tmp_path,
):
    database = tmp_path / "brain.db"
    store = SqliteCompanyBrainStore(database)
    put_knowledge(
        store,
        source_id="document:unknown-age",
        kind=EntityKind.DOCUMENT,
        title="Unknown age",
        revision="1",
        source_updated_at="not-a-timestamp",
        owner="team-platform",
    )

    plan = plan_company_brain_maintenance(
        SqliteCompanyBrainStore.open_read_only(database),
        tenant_id=TENANT,
        as_of=AS_OF,
    )

    assert [(item.finding_kind, item.action) for item in plan.proposals] == [
        (
            MemoryMaintenanceFindingKind.MISSING_SOURCE_FRESHNESS,
            MemoryMaintenanceAction.REPAIR_SOURCE_FRESHNESS_METADATA,
        )
    ]


def test_maintenance_rejects_a_reader_that_leaks_another_tenant(tmp_path):
    database = tmp_path / "brain.db"
    store = SqliteCompanyBrainStore(database)
    foreign = put_knowledge(
        store,
        tenant="tenant-other",
        source_id="runbook:foreign",
        kind=EntityKind.RUNBOOK,
        title="Foreign runbook",
        revision="1",
        source_updated_at=AS_OF,
    )

    class LeakyReader:
        def list_entities(self, tenant_id: str, *, include_deleted: bool = False):
            assert tenant_id == TENANT
            assert include_deleted is False
            return (foreign,)

        def list_relationships(self, tenant_id: str, *, include_deleted: bool = False):
            assert tenant_id == TENANT
            assert include_deleted is False
            return ()

    with pytest.raises(
        CompanyBrainMaintenanceError, match="outside the requested tenant"
    ):
        plan_company_brain_maintenance(LeakyReader(), tenant_id=TENANT, as_of=AS_OF)


def test_cli_emits_json_from_a_read_only_database_and_refuses_database_overwrite(
    tmp_path, capsys
):
    database = tmp_path / "brain.db"
    store = SqliteCompanyBrainStore(database)
    put_knowledge(
        store,
        source_id="runbook:payments",
        kind=EntityKind.RUNBOOK,
        title="Restart payments",
        revision="7",
        source_updated_at=AS_OF - timedelta(days=365),
    )
    before = database_files(database)

    exit_code = main(
        [
            "--database",
            str(database),
            "--tenant",
            TENANT,
            "--as-of",
            AS_OF.isoformat(),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "review-only"
    assert payload["tenant_id"] == TENANT
    assert database_files(database) == before

    assert (
        main(
            [
                "--database",
                str(database),
                "--tenant",
                TENANT,
                "--as-of",
                AS_OF.isoformat(),
                "--output",
                str(database),
            ]
        )
        == 2
    )
    assert "must not overwrite" in capsys.readouterr().err


def test_read_only_store_refuses_to_create_a_missing_database(tmp_path):
    database = tmp_path / "missing.db"

    with pytest.raises(CompanyBrainStoreError, match="does not exist"):
        SqliteCompanyBrainStore.open_read_only(database)

    assert database.exists() is False
