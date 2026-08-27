"""Qualified, read-only world-model queries over durable Company Brain facts.

Facts and graph edges are not equally trustworthy merely because they exist in
storage. This module qualifies them with the source provenance and ACL-bearing
evidence retained by the durable store. Stale, unauthorized, insufficient, or
conflicting relationships are reported as limitations rather than silently
driving a product decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from math import prod
from typing import Iterable, Protocol

from .model import BrainEntity, BrainPrincipal, BrainRelationship, CompanyBrainError, EntityKind, RelationshipKind
from .store import StoredEntity, StoredEvidence, StoredRelationship


class WorldModelError(CompanyBrainError):
    """Raised when a qualified Company Brain world-model query is invalid."""


class FactFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class WorldModelConflictKind(StrEnum):
    DEPENDENCY_CYCLE = "dependency_cycle"
    AMBIGUOUS_OWNERSHIP = "ambiguous_ownership"


@dataclass(frozen=True)
class SourceTrustRule:
    """Trust and freshness policy for one evidence source type."""

    source_kind: str
    confidence: float
    max_age: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, str) or not self.source_kind or "\n" in self.source_kind:
            raise WorldModelError("source_kind is invalid")
        if not 0.0 < self.confidence <= 1.0:
            raise WorldModelError("source confidence must be in (0, 1]")
        if self.max_age <= timedelta(0):
            raise WorldModelError("source max_age must be positive")


_DEFAULT_SOURCE_TRUST: tuple[SourceTrustRule, ...] = (
    SourceTrustRule("adr", 0.98, timedelta(days=365)),
    SourceTrustRule("conversation", 0.45, timedelta(days=30)),
    SourceTrustRule("deployment", 0.80, timedelta(days=30)),
    SourceTrustRule("documentation", 0.70, timedelta(days=180)),
    SourceTrustRule("incident", 0.75, timedelta(days=90)),
    SourceTrustRule("repository-change", 0.85, timedelta(days=45)),
    SourceTrustRule("runbook", 0.82, timedelta(days=90)),
    SourceTrustRule("work_item", 0.65, timedelta(days=120)),
)


@dataclass(frozen=True)
class WorldModelPolicy:
    """Deterministic policy controlling when an assertion is decision-usable."""

    minimum_confidence: float = 0.70
    default_rule: SourceTrustRule = SourceTrustRule("unknown", 0.40, timedelta(days=30))
    source_rules: tuple[SourceTrustRule, ...] = _DEFAULT_SOURCE_TRUST

    def __post_init__(self) -> None:
        if not 0.0 < self.minimum_confidence <= 1.0:
            raise WorldModelError("minimum_confidence must be in (0, 1]")
        kinds = tuple(rule.source_kind for rule in self.source_rules)
        if kinds != tuple(sorted(set(kinds))):
            raise WorldModelError("source_rules must be sorted by unique source_kind")

    def rule_for(self, source_kind: str) -> SourceTrustRule:
        return next((rule for rule in self.source_rules if rule.source_kind == source_kind), self.default_rule)


@dataclass(frozen=True)
class EvidenceQualification:
    evidence_id: str
    source_kind: str
    citation: str
    observed_at: datetime
    age: timedelta
    confidence: float
    freshness: FactFreshness


@dataclass(frozen=True)
class EntityQualification:
    entity: BrainEntity
    confidence: float
    freshness: FactFreshness
    evidence: tuple[EvidenceQualification, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationshipQualification:
    relationship: BrainRelationship
    confidence: float
    freshness: FactFreshness
    evidence: tuple[EvidenceQualification, ...]
    withheld_evidence_count: int
    usable: bool
    limitations: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorldModelConflict:
    conflict_id: str
    kind: WorldModelConflictKind
    entity_ids: tuple[str, ...]
    relationship_keys: tuple[tuple[str, RelationshipKind, str], ...]
    message: str


@dataclass(frozen=True)
class QualifiedWorldModelContext:
    tenant_id: str
    repository_id: str
    changed_services: tuple[str, ...]
    blast_radius: tuple[str, ...]
    owner_ids: tuple[str, ...]
    confidence: float
    entities: tuple[EntityQualification, ...]
    relationships: tuple[RelationshipQualification, ...]
    evidence: tuple[EvidenceQualification, ...]
    conflicts: tuple[WorldModelConflict, ...]
    limitations: tuple[str, ...]


class WorldModelStore(Protocol):
    def list_entities(self, tenant_id: str, *, include_deleted: bool = False) -> tuple[StoredEntity, ...]: ...
    def list_evidence(self, tenant_id: str, *, include_deleted: bool = False) -> tuple[StoredEvidence, ...]: ...
    def list_relationships(
        self, tenant_id: str, *, include_deleted: bool = False
    ) -> tuple[StoredRelationship, ...]: ...


@dataclass
class CompanyBrainWorldModel:
    """Resolve qualified company context without granting action authority."""

    store: WorldModelStore
    tenant_id: str
    policy: WorldModelPolicy = WorldModelPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id or "\n" in self.tenant_id:
            raise WorldModelError("tenant_id is invalid")

    def context_for_change(
        self,
        *,
        repository_id: str,
        changed_services: tuple[str, ...],
        principal: BrainPrincipal,
        now: datetime | None = None,
    ) -> QualifiedWorldModelContext:
        when = _utc(now or datetime.now(timezone.utc), "now")
        entities = {item.entity.entity_id: item.entity for item in self.store.list_entities(self.tenant_id)}
        repository = entities.get(repository_id)
        if repository is None or repository.kind is not EntityKind.REPOSITORY:
            raise WorldModelError("repository_id does not identify an active repository in this tenant")

        evidence = {item.evidence.evidence_id: item for item in self.store.list_evidence(self.tenant_id)}
        relationship_assessments = tuple(
            self._qualify_relationship(item.relationship, evidence, principal, when)
            for item in self.store.list_relationships(self.tenant_id)
        )
        relationship_assessments, conflicts = _detect_conflicts(relationship_assessments, entities)
        relationship_by_key = {_relationship_key(item.relationship): item for item in relationship_assessments}

        repository_services = {
            item.relationship.source_id
            for item in relationship_assessments
            if item.usable
            and item.relationship.kind is RelationshipKind.BELONGS_TO
            and item.relationship.target_id == repository_id
            and item.relationship.source_id in entities
            and entities[item.relationship.source_id].kind is EntityKind.SERVICE
        }
        requested = tuple(sorted(set(changed_services)))
        scoped_changed = tuple(service for service in requested if service in repository_services)
        blast_radius = _blast_radius(scoped_changed, relationship_assessments, entities)
        owner_ids = tuple(
            sorted(
                {
                    item.relationship.source_id
                    for item in relationship_assessments
                    if item.usable
                    and item.relationship.kind is RelationshipKind.OWNS
                    and item.relationship.target_id in blast_radius
                    and item.relationship.source_id in entities
                    and entities[item.relationship.source_id].kind in {EntityKind.OWNER, EntityKind.TEAM}
                }
            )
        )
        context_entity_ids = tuple(sorted({repository_id, *scoped_changed, *blast_radius, *owner_ids}))
        relevant_relationships = tuple(
            item
            for item in relationship_assessments
            if item.relationship.source_id in context_entity_ids or item.relationship.target_id in context_entity_ids
        )
        entity_qualifications = tuple(
            self._qualify_entity(entities[entity_id], relationship_by_key)
            for entity_id in context_entity_ids
        )
        context_evidence = _deduplicate_evidence(
            qualification for item in relevant_relationships for qualification in item.evidence
        )
        relevant_conflicts = tuple(
            conflict
            for conflict in conflicts
            if set(conflict.entity_ids).intersection(context_entity_ids)
        )
        limitations = _context_limitations(
            requested=requested,
            scoped_changed=scoped_changed,
            relevant_relationships=relevant_relationships,
            conflicts=relevant_conflicts,
        )
        usable_confidences = [
            item.confidence
            for item in relevant_relationships
            if item.usable and item.relationship.kind is not RelationshipKind.HAS_EVIDENCE
        ]
        return QualifiedWorldModelContext(
            tenant_id=self.tenant_id,
            repository_id=repository_id,
            changed_services=scoped_changed,
            blast_radius=blast_radius,
            owner_ids=owner_ids,
            confidence=min(usable_confidences) if usable_confidences else 0.0,
            entities=entity_qualifications,
            relationships=relevant_relationships,
            evidence=context_evidence,
            conflicts=relevant_conflicts,
            limitations=limitations,
        )

    def _qualify_entity(
        self,
        entity: BrainEntity,
        relationships: dict[tuple[str, RelationshipKind, str], RelationshipQualification],
    ) -> EntityQualification:
        supports = tuple(
            item
            for item in relationships.values()
            if item.relationship.kind is RelationshipKind.HAS_EVIDENCE and item.relationship.source_id == entity.entity_id
        )
        qualifications = _deduplicate_evidence(
            evidence for support in supports for evidence in support.evidence
        )
        fresh_confidences = [item.confidence for item in qualifications if item.freshness is FactFreshness.FRESH]
        if fresh_confidences:
            return EntityQualification(
                entity=entity,
                confidence=_combine_confidence(fresh_confidences),
                freshness=FactFreshness.FRESH,
                evidence=qualifications,
            )
        if qualifications:
            return EntityQualification(
                entity=entity,
                confidence=0.0,
                freshness=FactFreshness.STALE,
                evidence=qualifications,
                limitations=("Authorized entity evidence is stale and is not decision-usable.",),
            )
        return EntityQualification(
            entity=entity,
            confidence=0.0,
            freshness=FactFreshness.UNKNOWN,
            evidence=(),
            limitations=("No authorized evidence directly supports this entity fact.",),
        )

    def _qualify_relationship(
        self,
        relationship: BrainRelationship,
        evidence: dict[str, StoredEvidence],
        principal: BrainPrincipal,
        now: datetime,
    ) -> RelationshipQualification:
        known = tuple(evidence[item] for item in relationship.evidence_ids if item in evidence)
        authorized = tuple(item for item in known if item.evidence.visible_to(principal))
        qualifications = tuple(self._qualify_evidence(item, now) for item in authorized)
        withheld = len(known) - len(authorized)
        fresh_confidences = [item.confidence for item in qualifications if item.freshness is FactFreshness.FRESH]
        limitations: list[str] = []
        if not qualifications:
            limitations.append("No authorized supporting evidence is available for this relationship.")
            return RelationshipQualification(
                relationship=relationship,
                confidence=0.0,
                freshness=FactFreshness.UNKNOWN,
                evidence=(),
                withheld_evidence_count=withheld,
                usable=False,
                limitations=tuple(limitations),
            )
        if not fresh_confidences:
            limitations.append("Authorized supporting evidence is stale and is excluded from decision paths.")
            return RelationshipQualification(
                relationship=relationship,
                confidence=0.0,
                freshness=FactFreshness.STALE,
                evidence=qualifications,
                withheld_evidence_count=withheld,
                usable=False,
                limitations=tuple(limitations),
            )
        confidence = _combine_confidence(fresh_confidences)
        if withheld:
            limitations.append("Some supporting evidence is not authorized for this principal.")
        if any(item.freshness is FactFreshness.STALE for item in qualifications):
            limitations.append("Stale supporting evidence was excluded from the confidence calculation.")
        if confidence < self.policy.minimum_confidence:
            limitations.append("Fresh evidence confidence is below the decision threshold.")
        return RelationshipQualification(
            relationship=relationship,
            confidence=confidence,
            freshness=FactFreshness.FRESH,
            evidence=qualifications,
            withheld_evidence_count=withheld,
            usable=confidence >= self.policy.minimum_confidence,
            limitations=tuple(limitations),
        )

    def _qualify_evidence(self, evidence: StoredEvidence, now: datetime) -> EvidenceQualification:
        observed_at = _utc(evidence.provenance.observed_at, "evidence observed_at")
        age = max(timedelta(0), now - observed_at)
        rule = self.policy.rule_for(evidence.evidence.source_kind)
        freshness = FactFreshness.FRESH if age <= rule.max_age else FactFreshness.STALE
        return EvidenceQualification(
            evidence_id=evidence.evidence.evidence_id,
            source_kind=evidence.evidence.source_kind,
            citation=evidence.evidence.citation,
            observed_at=observed_at,
            age=age,
            confidence=rule.confidence,
            freshness=freshness,
        )


def _detect_conflicts(
    assessments: tuple[RelationshipQualification, ...], entities: dict[str, BrainEntity]
) -> tuple[tuple[RelationshipQualification, ...], tuple[WorldModelConflict, ...]]:
    by_key = {_relationship_key(item.relationship): item for item in assessments}
    conflicts: list[WorldModelConflict] = []
    cycle_keys: set[tuple[str, RelationshipKind, str]] = set()
    for key, assessment in by_key.items():
        source_id, kind, target_id = key
        if kind is not RelationshipKind.DEPENDS_ON or not assessment.usable:
            continue
        reverse = (target_id, RelationshipKind.DEPENDS_ON, source_id)
        if reverse not in by_key or not by_key[reverse].usable or key > reverse:
            continue
        cycle_keys.update((key, reverse))
        pair = tuple(sorted((source_id, target_id)))
        conflicts.append(
            WorldModelConflict(
                conflict_id=f"dependency-cycle:{pair[0]}:{pair[1]}",
                kind=WorldModelConflictKind.DEPENDENCY_CYCLE,
                entity_ids=pair,
                relationship_keys=tuple(sorted((key, reverse))),
                message="A direct dependency cycle has conflicting decision semantics and is excluded.",
            )
        )

    owners_by_service: dict[str, set[str]] = {}
    owner_relationships: dict[str, list[tuple[str, RelationshipKind, str]]] = {}
    for key, assessment in by_key.items():
        source_id, kind, target_id = key
        if (
            kind is RelationshipKind.OWNS
            and assessment.usable
            and entities.get(source_id) is not None
            and entities[source_id].kind in {EntityKind.OWNER, EntityKind.TEAM}
        ):
            owners_by_service.setdefault(target_id, set()).add(source_id)
            owner_relationships.setdefault(target_id, []).append(key)
    for service_id, owners in sorted(owners_by_service.items()):
        if len(owners) <= 1:
            continue
        conflicts.append(
            WorldModelConflict(
                conflict_id=f"ambiguous-ownership:{service_id}",
                kind=WorldModelConflictKind.AMBIGUOUS_OWNERSHIP,
                entity_ids=tuple(sorted((service_id, *owners))),
                relationship_keys=tuple(sorted(owner_relationships[service_id])),
                message="Multiple fresh owners are asserted; no single owner is inferred.",
            )
        )

    conflict_ids_by_key: dict[tuple[str, RelationshipKind, str], list[str]] = {}
    for conflict in conflicts:
        for key in conflict.relationship_keys:
            conflict_ids_by_key.setdefault(key, []).append(conflict.conflict_id)
    qualified = tuple(
        replace(
            assessment,
            usable=False if _relationship_key(assessment.relationship) in cycle_keys else assessment.usable,
            conflicts=tuple(sorted(conflict_ids_by_key.get(_relationship_key(assessment.relationship), ()))),
        )
        for assessment in assessments
    )
    return qualified, tuple(sorted(conflicts, key=lambda item: item.conflict_id))


def _blast_radius(
    changed_services: tuple[str, ...],
    assessments: tuple[RelationshipQualification, ...],
    entities: dict[str, BrainEntity],
) -> tuple[str, ...]:
    incoming: dict[str, set[str]] = {}
    for assessment in assessments:
        relationship = assessment.relationship
        if (
            assessment.usable
            and relationship.kind is RelationshipKind.DEPENDS_ON
            and entities.get(relationship.source_id) is not None
            and entities.get(relationship.target_id) is not None
            and entities[relationship.source_id].kind is EntityKind.SERVICE
            and entities[relationship.target_id].kind is EntityKind.SERVICE
        ):
            incoming.setdefault(relationship.target_id, set()).add(relationship.source_id)
    seen = set(changed_services)
    pending = list(changed_services)
    while pending:
        current = pending.pop()
        for dependent in sorted(incoming.get(current, ())):
            if dependent not in seen:
                seen.add(dependent)
                pending.append(dependent)
    return tuple(sorted(seen))


def _context_limitations(
    *,
    requested: tuple[str, ...],
    scoped_changed: tuple[str, ...],
    relevant_relationships: tuple[RelationshipQualification, ...],
    conflicts: tuple[WorldModelConflict, ...],
) -> tuple[str, ...]:
    limitations: list[str] = []
    unmapped = tuple(sorted(set(requested).difference(scoped_changed)))
    if unmapped:
        limitations.append("Some changed services lack authorized, fresh repository membership evidence.")
    if any(item.freshness is FactFreshness.STALE for item in relevant_relationships):
        limitations.append("Stale Company Brain relationships were excluded from decision paths.")
    if any(item.withheld_evidence_count for item in relevant_relationships):
        limitations.append("Some relevant Company Brain evidence is not authorized for this principal.")
    if any(not item.usable for item in relevant_relationships):
        limitations.append("Some relevant Company Brain relationships are below the decision threshold or conflicted.")
    if conflicts:
        limitations.append("Company Brain conflicts require human review before relying on affected relationships.")
    if not any(item.usable for item in relevant_relationships):
        limitations.append("No qualified Company Brain relationship is available for the requested context.")
    return tuple(dict.fromkeys(limitations))


def _deduplicate_evidence(values: Iterable[EvidenceQualification]) -> tuple[EvidenceQualification, ...]:
    result: dict[str, EvidenceQualification] = {}
    for value in values:
        result[value.evidence_id] = value
    return tuple(result[key] for key in sorted(result))


def _relationship_key(relationship: BrainRelationship) -> tuple[str, RelationshipKind, str]:
    return relationship.source_id, relationship.kind, relationship.target_id


def _combine_confidence(values: list[float]) -> float:
    return 1.0 - prod(1.0 - value for value in values)


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorldModelError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)
