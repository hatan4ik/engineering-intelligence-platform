from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from company_brain import (
    BrainEntity,
    DecisionContextRelationship,
    EntityKind,
    FactFreshness,
    ProductContractError,
    RelationshipKind,
    decision_context_from_world_model,
)
from company_brain.model import BrainRelationship
from company_brain.world_model import (
    EntityQualification,
    EvidenceQualification,
    QualifiedWorldModelContext,
    RelationshipQualification,
)


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _evidence(evidence_id: str, *, freshness: FactFreshness = FactFreshness.FRESH) -> EvidenceQualification:
    return EvidenceQualification(
        evidence_id=evidence_id,
        source_kind="repository-change",
        citation=f"knowledge://{evidence_id}",
        revision="revision-001",
        observed_at=NOW,
        age=timedelta(),
        confidence=0.85,
        freshness=freshness,
    )


def test_decision_context_keeps_only_qualified_relationship_claims():
    usable_evidence = _evidence("evidence:dependency")
    context = QualifiedWorldModelContext(
        tenant_id="tenant-acme",
        repository_id="repository:github:acme/platform",
        changed_services=("service:payments",),
        blast_radius=("service:checkout", "service:payments"),
        owner_ids=(),
        confidence=0.85,
        entities=(
            EntityQualification(
                BrainEntity("repository:github:acme/platform", EntityKind.REPOSITORY, "acme/platform"),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
            ),
            EntityQualification(
                BrainEntity("service:checkout", EntityKind.SERVICE, "checkout"),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
            ),
            EntityQualification(
                BrainEntity("service:payments", EntityKind.SERVICE, "payments"),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
            ),
            EntityQualification(
                BrainEntity("service:restricted", EntityKind.SERVICE, "restricted"),
                0.0,
                FactFreshness.UNKNOWN,
                (),
            ),
            EntityQualification(
                BrainEntity("service:conflicted", EntityKind.SERVICE, "conflicted"),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
            ),
        ),
        relationships=(
            RelationshipQualification(
                BrainRelationship(
                    "service:checkout",
                    "service:payments",
                    RelationshipKind.DEPENDS_ON,
                    ("evidence:dependency",),
                ),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
                0,
                True,
            ),
            RelationshipQualification(
                BrainRelationship(
                    "service:restricted",
                    "service:payments",
                    RelationshipKind.DEPENDS_ON,
                    ("evidence:private",),
                ),
                0.0,
                FactFreshness.UNKNOWN,
                (),
                1,
                False,
                ("No authorized supporting evidence is available for this relationship.",),
            ),
            RelationshipQualification(
                BrainRelationship(
                    "service:conflicted",
                    "service:payments",
                    RelationshipKind.DEPENDS_ON,
                    ("evidence:dependency",),
                ),
                0.85,
                FactFreshness.FRESH,
                (usable_evidence,),
                0,
                True,
                conflicts=("dependency-cycle:service:conflicted:service:payments",),
            ),
        ),
        evidence=(usable_evidence,),
        conflicts=(),
        limitations=("Some relevant evidence is not authorized for this principal.",),
    )

    decision_context = decision_context_from_world_model(
        context,
        context_version="world-model:v1:test",
        qualified=False,
        limitations=context.limitations,
    )

    assert [relationship.statement for relationship in decision_context.relationships] == [
        "checkout depends on payments"
    ]
    assert [reference.evidence_id for reference in decision_context.relationships[0].evidence] == [
        "evidence:dependency"
    ]
    assert decision_context.evidence.references[0].locator == "knowledge://evidence:dependency"
    assert "restricted" not in str(decision_context)
    assert "conflicted" not in str(decision_context)


def test_decision_context_rejects_a_stale_relationship_claim():
    with pytest.raises(ProductContractError, match="freshness must be fresh"):
        DecisionContextRelationship(
            source_id="service:checkout",
            source_label="checkout",
            relationship=RelationshipKind.DEPENDS_ON,
            target_id="service:payments",
            target_label="payments",
            confidence=0.85,
            freshness=FactFreshness.STALE,
            evidence=(),
        )


def test_decision_context_rejects_a_string_backed_relationship_kind() -> None:
    with pytest.raises(ProductContractError, match="relationship kind"):
        DecisionContextRelationship(
            source_id="service:checkout",
            source_label="checkout",
            relationship=cast(RelationshipKind, "depends_on"),
            target_id="service:payments",
            target_label="payments",
            confidence=0.85,
            freshness=FactFreshness.FRESH,
            evidence=(),
        )
