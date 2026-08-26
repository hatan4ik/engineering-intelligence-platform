from datetime import datetime, timedelta, timezone

import pytest

from company_brain import (
    BrainEntity,
    BrainEvidence,
    BrainProvenance,
    CompanyBrainRetentionError,
    CompanyBrainStoreError,
    CompanyBrainVersionConflict,
    EntityKind,
    RelationshipKind,
    RetentionPolicy,
    SqliteCompanyBrainStore,
)
from company_brain.model import BrainRelationship


def provenance(*, record: str = "source-1", revision: str = "v1") -> BrainProvenance:
    return BrainProvenance(
        source_system="github",
        source_record_id=record,
        source_revision=revision,
        observed_at=datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc),
        event_id=f"event:{record}:{revision}",
    )


def service(entity_id: str = "service:payments") -> BrainEntity:
    return BrainEntity(entity_id=entity_id, kind=EntityKind.SERVICE, label=entity_id.removeprefix("service:"))


def test_store_is_tenant_scoped_and_round_trips_provenance(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    stored = store.put_entity("tenant-a", service(), provenance=provenance())
    other = store.put_entity("tenant-b", service(), provenance=provenance(record="source-2"))

    assert stored.version == 1
    assert stored.provenance.source_record_id == "source-1"
    assert store.get_entity("tenant-a", "service:payments") == stored
    assert store.get_entity("tenant-b", "service:payments") == other
    assert store.get_entity("tenant-c", "service:payments") is None
    assert [event.tenant_id for event in store.audit_events("tenant-a")] == ["tenant-a"]


def test_store_uses_compare_and_swap_without_resurrecting_tombstones(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    first = store.put_entity("tenant-a", service(), provenance=provenance())
    second = store.put_entity(
        "tenant-a",
        BrainEntity(entity_id="service:payments", kind=EntityKind.SERVICE, label="payments-v2"),
        provenance=provenance(revision="v2"),
        expected_version=first.version,
    )

    assert second.version == 2
    with pytest.raises(CompanyBrainVersionConflict, match="expected version 1, current version is 2"):
        store.put_entity("tenant-a", service(), provenance=provenance(revision="v3"), expected_version=1)

    deleted = store.delete_entity(
        "tenant-a",
        "service:payments",
        expected_version=second.version,
        reason="source deletion reconciled",
        deleted_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    assert deleted.version == 3
    assert store.get_entity("tenant-a", "service:payments") is None
    assert store.get_entity("tenant-a", "service:payments", include_deleted=True) == deleted
    assert store.audit_events("tenant-a")[-1].operation == "tombstoned"

    with pytest.raises(CompanyBrainStoreError, match="cannot be silently recreated"):
        store.put_entity("tenant-a", service(), provenance=provenance(revision="v3"), expected_version=3)


def test_retention_cannot_be_weakened_and_legal_hold_blocks_tombstone(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    policy = RetentionPolicy(
        retain_until=datetime(2027, 8, 26, tzinfo=timezone.utc),
        legal_hold=True,
    )
    stored = store.put_entity("tenant-a", service(), provenance=provenance(), retention=policy)

    with pytest.raises(CompanyBrainRetentionError, match="legal hold"):
        store.delete_entity("tenant-a", "service:payments", expected_version=stored.version, reason="privacy request")
    with pytest.raises(CompanyBrainRetentionError, match="cannot be removed"):
        store.put_entity(
            "tenant-a",
            service(),
            provenance=provenance(revision="v2"),
            retention=RetentionPolicy(retain_until=policy.retain_until),
            expected_version=stored.version,
        )

    no_hold = store.put_entity(
        "tenant-a",
        service("service:orders"),
        provenance=provenance(record="orders"),
        retention=RetentionPolicy(retain_until=datetime(2027, 8, 26, tzinfo=timezone.utc)),
    )
    with pytest.raises(CompanyBrainRetentionError, match="cannot be shortened"):
        store.put_entity(
            "tenant-a",
            service("service:orders"),
            provenance=provenance(record="orders", revision="v2"),
            retention=RetentionPolicy(retain_until=datetime(2027, 8, 25, tzinfo=timezone.utc)),
            expected_version=no_hold.version,
        )


def test_relationships_require_active_same_tenant_endpoints_and_governed_evidence(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    store.put_entity("tenant-a", service("service:orders"), provenance=provenance(record="orders"))
    store.put_entity("tenant-b", service("service:payments"), provenance=provenance(record="payments"))

    with pytest.raises(CompanyBrainStoreError, match="same tenant"):
        store.put_relationship(
            "tenant-a",
            BrainRelationship("service:orders", "service:payments", RelationshipKind.DEPENDS_ON),
            provenance=provenance(record="relationship-1"),
        )

    store.put_entity("tenant-a", service("service:payments"), provenance=provenance(record="payments"))
    evidence = store.put_evidence(
        "tenant-a",
        BrainEvidence(
            evidence_id="evidence:adr-1",
            source_kind="adr",
            citation="knowledge://adr-1",
            revision="1",
            acl_groups=("engineering",),
        ),
        provenance=provenance(record="adr-1"),
    )
    relationship = store.put_relationship(
        "tenant-a",
        BrainRelationship(
            "service:orders",
            "service:payments",
            RelationshipKind.DEPENDS_ON,
            evidence_ids=(evidence.evidence.evidence_id,),
        ),
        provenance=provenance(record="relationship-2"),
    )

    assert relationship.version == 1
    snapshot = store.snapshot("tenant-a")
    assert [item.kind for item in snapshot.outgoing("service:orders")] == [RelationshipKind.DEPENDS_ON]
    assert "service:orders" in snapshot.entities
    assert "service:payments" in snapshot.entities
    assert snapshot.evidence["evidence:adr-1"].acl_groups == ("engineering",)


def test_retention_date_can_extend_but_not_move_backwards(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    first = store.put_entity(
        "tenant-a",
        service(),
        provenance=provenance(),
        retention=RetentionPolicy(retain_until=datetime(2026, 9, 1, tzinfo=timezone.utc)),
    )
    extended = store.put_entity(
        "tenant-a",
        service(),
        provenance=provenance(revision="v2"),
        retention=RetentionPolicy(retain_until=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=1)),
        expected_version=first.version,
    )

    assert extended.version == 2
    assert extended.retention.retain_until == datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_evidence_and_relationship_tombstones_are_consistent_in_a_snapshot(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    store.put_entity("tenant-a", service("service:orders"), provenance=provenance(record="orders"))
    store.put_entity("tenant-a", service("service:payments"), provenance=provenance(record="payments"))
    evidence = store.put_evidence(
        "tenant-a",
        BrainEvidence(
            evidence_id="evidence:runbook-1",
            source_kind="runbook",
            citation="knowledge://runbook-1",
            revision="1",
            acl_groups=("engineering",),
        ),
        provenance=provenance(record="runbook-1"),
    )
    relationship = store.put_relationship(
        "tenant-a",
        BrainRelationship(
            "service:orders",
            "service:payments",
            RelationshipKind.DEPENDS_ON,
            evidence_ids=(evidence.evidence.evidence_id,),
        ),
        provenance=provenance(record="relationship-1"),
    )

    with pytest.raises(CompanyBrainStoreError, match="delete_evidence"):
        store.delete_entity(
            "tenant-a",
            "evidence:runbook-1",
            expected_version=1,
            reason="wrong deletion API",
        )

    deleted_relationship = store.delete_relationship(
        "tenant-a",
        source_id="service:orders",
        target_id="service:payments",
        kind=RelationshipKind.DEPENDS_ON,
        expected_version=relationship.version,
        reason="dependency removed",
    )
    assert deleted_relationship.deleted_at is not None
    assert store.list_relationships("tenant-a") == ()

    deleted_evidence = store.delete_evidence(
        "tenant-a",
        "evidence:runbook-1",
        expected_version=evidence.version,
        reason="source document removed",
    )
    assert deleted_evidence.deleted_at is not None
    assert store.get_evidence("tenant-a", "evidence:runbook-1") is None
    assert store.get_evidence("tenant-a", "evidence:runbook-1", include_deleted=True) == deleted_evidence
    assert "evidence:runbook-1" not in store.snapshot("tenant-a").entities
