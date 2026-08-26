"""The governed Company Brain world model.

This reference model intentionally retains evidence pointers and access metadata,
not source content. Reasoning products must request an authorized context from
this model; they must not infer that an entity or relationship grants action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable, Mapping


class CompanyBrainError(ValueError):
    """Raised when an organizational fact cannot be represented safely."""


class EntityKind(StrEnum):
    REPOSITORY = "repository"
    SERVICE = "service"
    TEAM = "team"
    OWNER = "owner"
    ADR = "adr"
    CHANGE = "change"
    DEPLOYMENT = "deployment"
    INCIDENT = "incident"
    RUNBOOK = "runbook"
    WORK_ITEM = "work_item"
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    FINDING = "finding"
    OUTCOME = "outcome"
    EVIDENCE = "evidence"


class RelationshipKind(StrEnum):
    OWNS = "owns"
    DEPENDS_ON = "depends_on"
    CHANGED_BY = "changed_by"
    CAUSED = "caused"
    RESOLVED_BY = "resolved_by"
    GOVERNED_BY = "governed_by"
    BELONGS_TO = "belongs_to"
    HAS_EVIDENCE = "has_evidence"
    ASSESSED_BY = "assessed_by"
    HAS_OUTCOME = "has_outcome"


def _required(value: str, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise CompanyBrainError(f"{label} is invalid")
    return value


def _normalized_strings(values: tuple[str, ...], label: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise CompanyBrainError(f"{label} must not be empty")
    if values != tuple(sorted(set(values))):
        raise CompanyBrainError(f"{label} must be sorted and unique")
    return tuple(_required(value, label, maximum=200) for value in values)


def _normalized_attributes(values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if values != tuple(sorted(values)) or len({key for key, _ in values}) != len(values):
        raise CompanyBrainError("attributes must be sorted by unique key")
    for key, value in values:
        _required(key, "attribute key", maximum=100)
        _required(value, "attribute value", maximum=500)
    return values


@dataclass(frozen=True)
class BrainPrincipal:
    """The identity dimensions relevant to evidence authorization."""

    groups: tuple[str, ...] = ()
    users: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalized_strings(self.groups, "principal groups")
        _normalized_strings(self.users, "principal users")
        if not self.groups and not self.users:
            raise CompanyBrainError("principal requires a group or user identity")


@dataclass(frozen=True)
class BrainEntity:
    entity_id: str
    kind: EntityKind
    label: str
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _required(self.entity_id, "entity_id")
        _required(self.label, "entity label", maximum=300)
        if self.kind not in set(EntityKind):
            raise CompanyBrainError("entity kind is invalid")
        _normalized_attributes(self.attributes)

    @property
    def metadata(self) -> Mapping[str, str]:
        return dict(self.attributes)


@dataclass(frozen=True)
class BrainEvidence:
    """A minimal evidence pointer with the ACL needed for a fail-closed read."""

    evidence_id: str
    source_kind: str
    citation: str
    revision: str
    acl_groups: tuple[str, ...] = ()
    acl_users: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required(self.evidence_id, "evidence_id")
        _required(self.source_kind, "source_kind", maximum=100)
        _required(self.citation, "citation")
        _required(self.revision, "revision", maximum=200)
        _normalized_strings(self.acl_groups, "evidence acl_groups")
        _normalized_strings(self.acl_users, "evidence acl_users")

    def visible_to(self, principal: BrainPrincipal) -> bool:
        """Fail closed: an evidence item without a matching ACL is not visible."""
        return bool(
            set(self.acl_groups).intersection(principal.groups)
            or set(self.acl_users).intersection(principal.users)
        )


@dataclass(frozen=True)
class BrainRelationship:
    source_id: str
    target_id: str
    kind: RelationshipKind
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required(self.source_id, "relationship source_id")
        _required(self.target_id, "relationship target_id")
        if self.source_id == self.target_id:
            raise CompanyBrainError("relationship endpoints must differ")
        if self.kind not in set(RelationshipKind):
            raise CompanyBrainError("relationship kind is invalid")
        _normalized_strings(self.evidence_ids, "relationship evidence_ids")


@dataclass(frozen=True)
class CompanyBrainContext:
    """Authorized company context suitable for a product workflow."""

    repository_id: str
    changed_services: tuple[str, ...]
    blast_radius: tuple[str, ...]
    owner_ids: tuple[str, ...]
    evidence: tuple[BrainEvidence, ...]
    limitations: tuple[str, ...]


@dataclass
class CompanyBrain:
    """In-memory reference store for governed facts, edges, and evidence.

    A production adapter may persist these records, but must preserve all
    validation and fail-closed evidence visibility semantics in this model.
    """

    entities: dict[str, BrainEntity] = field(default_factory=dict)
    evidence: dict[str, BrainEvidence] = field(default_factory=dict)
    _relationships: dict[tuple[str, str, RelationshipKind], BrainRelationship] = field(
        default_factory=dict
    )

    def upsert_entity(self, entity: BrainEntity) -> None:
        self.entities[entity.entity_id] = entity

    def record_evidence(self, evidence: BrainEvidence) -> None:
        self.evidence[evidence.evidence_id] = evidence
        self.upsert_entity(
            BrainEntity(
                entity_id=evidence.evidence_id,
                kind=EntityKind.EVIDENCE,
                label=evidence.citation,
                attributes=(("revision", evidence.revision), ("source_kind", evidence.source_kind)),
            )
        )

    def remove_entity(self, entity_id: str) -> None:
        """Remove a source-derived fact and every edge that names it.

        This is intentionally an in-memory projection operation. Durable
        lifecycle and audit semantics belong to ``CompanyBrainStore``.
        """
        self.entities.pop(entity_id, None)
        self._relationships = {
            key: relationship
            for key, relationship in self._relationships.items()
            if relationship.source_id != entity_id and relationship.target_id != entity_id
        }

    def remove_evidence(self, evidence_id: str) -> None:
        """Remove a pointer and its structural evidence entity from this projection."""
        self.evidence.pop(evidence_id, None)
        self.remove_entity(evidence_id)

    def relate(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: RelationshipKind,
        evidence_ids: tuple[str, ...] = (),
    ) -> BrainRelationship:
        if source_id not in self.entities or target_id not in self.entities:
            raise CompanyBrainError("relationship endpoints must exist before they are linked")
        missing_evidence = set(evidence_ids).difference(self.evidence)
        if missing_evidence:
            raise CompanyBrainError(f"relationship references unknown evidence: {sorted(missing_evidence)}")
        key = (source_id, target_id, kind)
        previous = self._relationships.get(key)
        merged_evidence = tuple(sorted(set(evidence_ids).union(previous.evidence_ids if previous else ())))
        relationship = BrainRelationship(source_id, target_id, kind, merged_evidence)
        self._relationships[key] = relationship
        return relationship

    @property
    def relationships(self) -> tuple[BrainRelationship, ...]:
        return tuple(
            sorted(
                self._relationships.values(),
                key=lambda item: (item.source_id, item.kind.value, item.target_id),
            )
        )

    def outgoing(
        self, entity_id: str, *, kind: RelationshipKind | None = None
    ) -> tuple[BrainRelationship, ...]:
        return tuple(
            item
            for item in self.relationships
            if item.source_id == entity_id and (kind is None or item.kind is kind)
        )

    def incoming(
        self, entity_id: str, *, kind: RelationshipKind | None = None
    ) -> tuple[BrainRelationship, ...]:
        return tuple(
            item
            for item in self.relationships
            if item.target_id == entity_id and (kind is None or item.kind is kind)
        )

    def services_for_repository(self, repository_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.source_id
                for item in self.incoming(repository_id, kind=RelationshipKind.BELONGS_TO)
                if self.entities[item.source_id].kind is EntityKind.SERVICE
            )
        )

    def owner_ids_for_service(self, service_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.source_id
                for item in self.incoming(service_id, kind=RelationshipKind.OWNS)
                if self.entities[item.source_id].kind in {EntityKind.OWNER, EntityKind.TEAM}
            )
        )

    def blast_radius(self, changed_services: Iterable[str]) -> tuple[str, ...]:
        """Return changed services plus services that transitively depend on them."""
        seen = {service for service in changed_services if service in self.entities}
        pending = list(seen)
        while pending:
            current = pending.pop()
            for relationship in self.incoming(current, kind=RelationshipKind.DEPENDS_ON):
                dependent = relationship.source_id
                if dependent not in seen and self.entities[dependent].kind is EntityKind.SERVICE:
                    seen.add(dependent)
                    pending.append(dependent)
        return tuple(sorted(seen))

    def authorized_evidence(
        self, entity_ids: Iterable[str], principal: BrainPrincipal
    ) -> tuple[BrainEvidence, ...]:
        evidence_ids: set[str] = set()
        for entity_id in entity_ids:
            for relationship in self.outgoing(entity_id, kind=RelationshipKind.HAS_EVIDENCE):
                if relationship.target_id in self.evidence:
                    evidence_ids.add(relationship.target_id)
        return tuple(
            self.evidence[evidence_id]
            for evidence_id in sorted(evidence_ids)
            if self.evidence[evidence_id].visible_to(principal)
        )

    def context_for_change(
        self,
        *,
        repository_id: str,
        changed_services: Iterable[str],
        principal: BrainPrincipal,
    ) -> CompanyBrainContext:
        if repository_id not in self.entities or self.entities[repository_id].kind is not EntityKind.REPOSITORY:
            raise CompanyBrainError("repository_id does not identify a repository")
        repository_services = set(self.services_for_repository(repository_id))
        requested = tuple(sorted(set(changed_services)))
        scoped_changed = tuple(service for service in requested if service in repository_services)
        blast_radius = self.blast_radius(scoped_changed)
        context_entities = (repository_id, *blast_radius)
        authorized = self.authorized_evidence(context_entities, principal)
        owners = tuple(sorted({owner for service in blast_radius for owner in self.owner_ids_for_service(service)}))
        limitations: list[str] = []
        unmapped = sorted(set(requested).difference(repository_services))
        if unmapped:
            limitations.append(f"Changed services are outside the repository scope: {', '.join(unmapped)}.")
        if not authorized:
            limitations.append("No authorized evidence was available for the requested company context.")
        return CompanyBrainContext(
            repository_id=repository_id,
            changed_services=scoped_changed,
            blast_radius=blast_radius,
            owner_ids=owners,
            evidence=authorized,
            limitations=tuple(limitations),
        )
