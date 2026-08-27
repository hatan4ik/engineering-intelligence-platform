from datetime import datetime, timedelta, timezone

from company_brain import (
    BrainEntity,
    BrainEvidence,
    BrainPrincipal,
    BrainProvenance,
    CompanyBrainWorldModel,
    EntityKind,
    FactFreshness,
    RelationshipKind,
    SqliteCompanyBrainStore,
    WorldModelConflictKind,
)
from company_brain.model import BrainRelationship


TENANT = "tenant-acme"
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def provenance(record_id: str, observed_at: datetime = NOW) -> BrainProvenance:
    return BrainProvenance(
        source_system="github",
        source_record_id=record_id,
        source_revision="1",
        observed_at=observed_at,
        event_id=f"event:{record_id}",
    )


def entity(store: SqliteCompanyBrainStore, entity_id: str, kind: EntityKind, label: str) -> None:
    store.put_entity(TENANT, BrainEntity(entity_id=entity_id, kind=kind, label=label), provenance=provenance(entity_id))


def evidence(
    store: SqliteCompanyBrainStore,
    evidence_id: str,
    *,
    source_kind: str = "repository-change",
    groups: tuple[str, ...] = ("engineering",),
    observed_at: datetime = NOW,
) -> None:
    store.put_evidence(
        TENANT,
        BrainEvidence(
            evidence_id=evidence_id,
            source_kind=source_kind,
            citation=f"knowledge://{evidence_id}",
            revision="1",
            acl_groups=groups,
        ),
        provenance=provenance(evidence_id, observed_at),
    )


def relate(
    store: SqliteCompanyBrainStore,
    source_id: str,
    target_id: str,
    kind: RelationshipKind,
    evidence_id: str,
) -> None:
    store.put_relationship(
        TENANT,
        BrainRelationship(source_id, target_id, kind, evidence_ids=(evidence_id,)),
        provenance=provenance(f"{source_id}:{kind.value}:{target_id}"),
    )


def seed_repository(store: SqliteCompanyBrainStore) -> None:
    entity(store, "repository:github:acme/platform", EntityKind.REPOSITORY, "acme/platform")
    entity(store, "service:payments", EntityKind.SERVICE, "payments")
    entity(store, "service:checkout", EntityKind.SERVICE, "checkout")
    evidence(store, "evidence:membership")
    relate(
        store,
        "service:payments",
        "repository:github:acme/platform",
        RelationshipKind.BELONGS_TO,
        "evidence:membership",
    )
    relate(
        store,
        "service:checkout",
        "repository:github:acme/platform",
        RelationshipKind.BELONGS_TO,
        "evidence:membership",
    )


def test_fresh_authorized_relationships_drive_qualified_blast_radius(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)
    entity(store, "owner:payments", EntityKind.OWNER, "team-payments")
    evidence(store, "evidence:dependency")
    evidence(store, "evidence:owner", source_kind="adr")
    relate(store, "service:checkout", "service:payments", RelationshipKind.DEPENDS_ON, "evidence:dependency")
    relate(store, "owner:payments", "service:payments", RelationshipKind.OWNS, "evidence:owner")
    relate(store, "service:payments", "evidence:owner", RelationshipKind.HAS_EVIDENCE, "evidence:owner")

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("engineering",)),
        now=NOW,
    )

    assert context.changed_services == ("service:payments",)
    assert context.blast_radius == ("service:checkout", "service:payments")
    assert context.owner_ids == ("owner:payments",)
    assert context.confidence == 0.85
    assert not context.conflicts
    payments = next(item for item in context.entities if item.entity.entity_id == "service:payments")
    assert payments.freshness is FactFreshness.FRESH
    assert payments.confidence == 0.98


def test_stale_relationships_are_visible_as_limitations_but_excluded_from_blast_radius(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)
    evidence(store, "evidence:stale-dependency", observed_at=NOW - timedelta(days=46))
    relate(
        store,
        "service:checkout",
        "service:payments",
        RelationshipKind.DEPENDS_ON,
        "evidence:stale-dependency",
    )

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("engineering",)),
        now=NOW,
    )

    assert context.blast_radius == ("service:payments",)
    dependency = next(item for item in context.relationships if item.relationship.kind is RelationshipKind.DEPENDS_ON)
    assert dependency.freshness is FactFreshness.STALE
    assert dependency.usable is False
    assert "Stale Company Brain relationships were excluded from decision paths." in context.limitations


def test_unauthorized_evidence_fails_closed_before_repository_scope_is_granted(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("finance",)),
        now=NOW,
    )

    assert context.changed_services == ()
    assert context.blast_radius == ()
    assert context.evidence == ()
    assert "Some changed services lack authorized, fresh repository membership evidence." in context.limitations


def test_direct_dependency_cycle_is_conflicted_and_removed_from_decision_paths(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)
    evidence(store, "evidence:payments-to-checkout")
    evidence(store, "evidence:checkout-to-payments")
    relate(
        store,
        "service:payments",
        "service:checkout",
        RelationshipKind.DEPENDS_ON,
        "evidence:payments-to-checkout",
    )
    relate(
        store,
        "service:checkout",
        "service:payments",
        RelationshipKind.DEPENDS_ON,
        "evidence:checkout-to-payments",
    )

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("engineering",)),
        now=NOW,
    )

    assert context.blast_radius == ("service:payments",)
    assert {conflict.kind for conflict in context.conflicts} == {WorldModelConflictKind.DEPENDENCY_CYCLE}
    dependencies = [item for item in context.relationships if item.relationship.kind is RelationshipKind.DEPENDS_ON]
    assert all(item.usable is False and item.conflicts for item in dependencies)


def test_multiple_fresh_owners_are_returned_without_inferring_a_single_owner(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)
    entity(store, "owner:payments-a", EntityKind.OWNER, "payments-a")
    entity(store, "owner:payments-b", EntityKind.OWNER, "payments-b")
    evidence(store, "evidence:owner-a", source_kind="adr")
    evidence(store, "evidence:owner-b", source_kind="adr")
    relate(store, "owner:payments-a", "service:payments", RelationshipKind.OWNS, "evidence:owner-a")
    relate(store, "owner:payments-b", "service:payments", RelationshipKind.OWNS, "evidence:owner-b")

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("engineering",)),
        now=NOW,
    )

    assert context.owner_ids == ("owner:payments-a", "owner:payments-b")
    assert {conflict.kind for conflict in context.conflicts} == {WorldModelConflictKind.AMBIGUOUS_OWNERSHIP}
    assert "Company Brain conflicts require human review before relying on affected relationships." in context.limitations


def test_world_model_is_tenant_isolated(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    seed_repository(store)
    store.put_entity(
        "tenant-other",
        BrainEntity("repository:github:acme/platform", EntityKind.REPOSITORY, "other/platform"),
        provenance=provenance("other-repository"),
    )

    context = CompanyBrainWorldModel(store, TENANT).context_for_change(
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        principal=BrainPrincipal(groups=("engineering",)),
        now=NOW,
    )

    assert context.tenant_id == TENANT
    assert context.repository_id == "repository:github:acme/platform"
