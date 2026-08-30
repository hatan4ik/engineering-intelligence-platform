"""Review-only knowledge-maintenance planning over durable Company Brain memory.

The planner is the first bounded ``dreaming & pruning`` loop for Company
Brain.  It reads tenant-scoped records and returns deterministic proposals; it
does not publish a ticket, modify a source system, or write back to the Brain.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Protocol, assert_never

from intelligence.knowledge_decay import (
    KnowledgeDecayKind,
    KnowledgeRecord,
    detect_knowledge_decay,
)

from .model import EntityKind, RelationshipKind
from .serialization import PayloadValidationError, parse_timestamp
from .store import StoredEntity, StoredRelationship


class CompanyBrainMaintenanceError(ValueError):
    """A memory-maintenance request cannot be evaluated safely."""


class MemoryMaintenanceFindingKind(StrEnum):
    """Review conditions a Company Brain maintenance proposal may represent."""

    STALE = "stale"
    MISSING_OWNER = "missing-owner"
    CONFLICT = "conflict"
    MISSING_SOURCE_FRESHNESS = "missing-source-freshness"


class MemoryMaintenanceAction(StrEnum):
    """The only human-reviewed actions this planner may recommend."""

    REQUEST_OWNER_REVIEW = "request-owner-review"
    ASSIGN_ACCOUNTABLE_OWNER = "assign-accountable-owner"
    RESOLVE_CONFLICTING_ACTIVE_REVISIONS = "resolve-conflicting-active-revisions"
    REPAIR_SOURCE_FRESHNESS_METADATA = "repair-source-freshness-metadata"


_SOURCE_UPDATED_AT_ATTRIBUTE = "source_updated_at"
_SUPPORTED_KNOWLEDGE_KINDS = frozenset(
    {
        EntityKind.ADR,
        EntityKind.DOCUMENT,
        EntityKind.RUNBOOK,
    }
)
DEFAULT_MAINTENANCE_KINDS = tuple(
    sorted(_SUPPORTED_KNOWLEDGE_KINDS, key=lambda kind: kind.value)
)


def _required(value: str, label: str, *, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\n" in value
    ):
        raise CompanyBrainMaintenanceError(f"{label} is invalid")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CompanyBrainMaintenanceError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)


class CompanyBrainMaintenanceReader(Protocol):
    """The deliberately read-only port needed by memory-maintenance planning."""

    def list_entities(
        self, tenant_id: str, *, include_deleted: bool = False
    ) -> tuple[StoredEntity, ...]: ...

    def list_relationships(
        self, tenant_id: str, *, include_deleted: bool = False
    ) -> tuple[StoredRelationship, ...]: ...


@dataclass(frozen=True)
class MemoryMaintenancePolicy:
    """Explicit, versioned bounds for a deterministic maintenance pass."""

    policy_version: str = "company-brain-maintenance-v1"
    stale_after_days: int = 180
    eligible_kinds: tuple[EntityKind, ...] = DEFAULT_MAINTENANCE_KINDS

    def __post_init__(self) -> None:
        _required(self.policy_version, "maintenance policy_version", maximum=160)
        if type(self.stale_after_days) is not int or self.stale_after_days < 0:
            raise CompanyBrainMaintenanceError(
                "maintenance stale_after_days must be a non-negative integer"
            )
        if not isinstance(self.eligible_kinds, tuple) or any(
            not isinstance(kind, EntityKind) for kind in self.eligible_kinds
        ):
            raise CompanyBrainMaintenanceError(
                "maintenance eligible_kinds must contain entity kinds"
            )
        expected = tuple(sorted(set(self.eligible_kinds), key=lambda kind: kind.value))
        if not self.eligible_kinds or self.eligible_kinds != expected:
            raise CompanyBrainMaintenanceError(
                "maintenance eligible_kinds must be sorted and unique"
            )
        unsupported = set(self.eligible_kinds).difference(_SUPPORTED_KNOWLEDGE_KINDS)
        if unsupported:
            raise CompanyBrainMaintenanceError(
                "maintenance eligible_kinds contains an unsupported entity kind"
            )


@dataclass(frozen=True)
class MemoryMaintenanceProposal:
    """A source-version-bound proposal that always requires human review."""

    proposal_id: str
    tenant_id: str
    source_id: str
    source_kind: EntityKind
    source_label: str
    source_system: str
    source_record_id: str
    source_revision: str
    source_version: int
    finding_kind: MemoryMaintenanceFindingKind
    action: MemoryMaintenanceAction
    severity: int
    reason: str
    policy_version: str
    requires_human_review: Literal[True] = True

    def __post_init__(self) -> None:
        if not self.proposal_id.startswith("maintenance:"):
            raise CompanyBrainMaintenanceError("maintenance proposal_id is invalid")
        for value, label, maximum in (
            (self.tenant_id, "maintenance tenant_id", 200),
            (self.source_id, "maintenance source_id", 500),
            (self.source_label, "maintenance source_label", 300),
            (self.source_system, "maintenance source_system", 100),
            (self.source_record_id, "maintenance source_record_id", 500),
            (self.source_revision, "maintenance source_revision", 200),
            (self.reason, "maintenance reason", 1_000),
            (self.policy_version, "maintenance policy_version", 160),
        ):
            _required(value, label, maximum=maximum)
        if (
            not isinstance(self.source_kind, EntityKind)
            or self.source_kind not in _SUPPORTED_KNOWLEDGE_KINDS
        ):
            raise CompanyBrainMaintenanceError(
                "maintenance source_kind is not eligible"
            )
        if not isinstance(self.finding_kind, MemoryMaintenanceFindingKind):
            raise CompanyBrainMaintenanceError("maintenance finding_kind is invalid")
        if not isinstance(self.action, MemoryMaintenanceAction):
            raise CompanyBrainMaintenanceError("maintenance action is invalid")
        if type(self.source_version) is not int or self.source_version < 1:
            raise CompanyBrainMaintenanceError(
                "maintenance source_version must be positive"
            )
        if type(self.severity) is not int or not 1 <= self.severity <= 5:
            raise CompanyBrainMaintenanceError("maintenance severity must be in [1, 5]")
        if self.action is not _action_for(self.finding_kind):
            raise CompanyBrainMaintenanceError(
                "maintenance action does not match finding_kind"
            )
        if self.requires_human_review is not True:
            raise CompanyBrainMaintenanceError(
                "maintenance proposals always require human review"
            )

    def to_payload(self) -> dict[str, object]:
        """Return the bounded transport shape for an operator or later publisher."""

        return {
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "source_label": self.source_label,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "source_revision": self.source_revision,
            "source_version": self.source_version,
            "finding_kind": self.finding_kind.value,
            "action": self.action.value,
            "severity": self.severity,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "requires_human_review": self.requires_human_review,
        }


@dataclass(frozen=True)
class MemoryMaintenancePlan:
    """The complete, non-mutating result of one explicit maintenance pass."""

    tenant_id: str
    as_of: datetime
    policy: MemoryMaintenancePolicy
    assessed_source_count: int
    proposals: tuple[MemoryMaintenanceProposal, ...]

    def __post_init__(self) -> None:
        _required(self.tenant_id, "maintenance tenant_id", maximum=200)
        _utc(self.as_of, "maintenance as_of")
        if not isinstance(self.policy, MemoryMaintenancePolicy):
            raise CompanyBrainMaintenanceError("maintenance policy is invalid")
        if (
            type(self.assessed_source_count) is not int
            or self.assessed_source_count < 0
        ):
            raise CompanyBrainMaintenanceError(
                "maintenance assessed_source_count must be non-negative"
            )
        ordered = tuple(
            sorted(
                self.proposals,
                key=lambda item: (
                    -item.severity,
                    item.source_id,
                    item.action.value,
                    item.proposal_id,
                ),
            )
        )
        if self.proposals != ordered:
            raise CompanyBrainMaintenanceError(
                "maintenance proposals must be deterministically ordered"
            )
        if len({item.proposal_id for item in self.proposals}) != len(self.proposals):
            raise CompanyBrainMaintenanceError(
                "maintenance proposal IDs must be unique"
            )
        if any(item.tenant_id != self.tenant_id for item in self.proposals):
            raise CompanyBrainMaintenanceError(
                "maintenance proposal tenant does not match plan tenant"
            )

    @property
    def summary(self) -> str:
        if not self.proposals:
            return "No knowledge-maintenance proposals were generated."
        return (
            f"Generated {len(self.proposals)} review-only knowledge-maintenance proposal(s) "
            f"from {self.assessed_source_count} eligible source record(s)."
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize a plan without source bodies, citations, ACLs, or write instructions."""

        return {
            "schema_version": 1,
            "mode": "review-only",
            "tenant_id": self.tenant_id,
            "as_of": _utc(self.as_of, "maintenance as_of").isoformat(),
            "policy": {
                "policy_version": self.policy.policy_version,
                "stale_after_days": self.policy.stale_after_days,
                "eligible_kinds": [kind.value for kind in self.policy.eligible_kinds],
            },
            "assessed_source_count": self.assessed_source_count,
            "summary": self.summary,
            "proposals": [proposal.to_payload() for proposal in self.proposals],
        }


def plan_company_brain_maintenance(
    reader: CompanyBrainMaintenanceReader,
    *,
    tenant_id: str,
    as_of: datetime,
    policy: MemoryMaintenancePolicy = MemoryMaintenancePolicy(),
) -> MemoryMaintenancePlan:
    """Produce a deterministic, tenant-scoped plan without mutating the reader.

    ``as_of`` is required so a scheduler or operator can reproduce a plan.  A
    missing or malformed source timestamp produces a review request instead of
    falling back to the database write time and silently treating old knowledge
    as fresh.
    """

    tenant = _required(tenant_id, "maintenance tenant_id", maximum=200)
    reference_time = _utc(as_of, "maintenance as_of")
    entities = reader.list_entities(tenant, include_deleted=False)
    relationships = reader.list_relationships(tenant, include_deleted=False)
    _assert_tenant_scope(tenant, entities, relationships)

    active_entities = tuple(
        sorted(
            (item for item in entities if item.deleted_at is None),
            key=lambda item: item.entity.entity_id,
        )
    )
    entity_by_id = {item.entity.entity_id: item for item in active_entities}
    if len(entity_by_id) != len(active_entities):
        raise CompanyBrainMaintenanceError(
            "maintenance reader returned duplicate entity IDs"
        )
    active_relationships = tuple(
        item for item in relationships if item.deleted_at is None
    )
    owners = _owners_by_source(active_relationships, entity_by_id)
    candidates = tuple(
        item for item in active_entities if item.entity.kind in policy.eligible_kinds
    )

    source_records: dict[str, StoredEntity] = {}
    knowledge_records: list[KnowledgeRecord] = []
    raw_findings: list[tuple[StoredEntity, MemoryMaintenanceFindingKind, int, str]] = []
    for stored in candidates:
        source_records[stored.entity.entity_id] = stored
        source_updated_at = _source_updated_at(stored)
        if source_updated_at is None:
            raw_findings.append(
                (
                    stored,
                    MemoryMaintenanceFindingKind.MISSING_SOURCE_FRESHNESS,
                    3,
                    "source_updated_at is missing or invalid; replay the governed source projection "
                    "before assessing freshness",
                )
            )
        owner_labels = owners.get(stored.entity.entity_id, ())
        knowledge_records.append(
            KnowledgeRecord(
                source_id=stored.entity.entity_id,
                source_type=stored.entity.kind.value,
                title=stored.entity.label,
                revision=stored.provenance.source_revision,
                updated_at=source_updated_at,
                owner=", ".join(owner_labels) or None,
            )
        )

    for finding in detect_knowledge_decay(
        knowledge_records,
        stale_after_days=policy.stale_after_days,
        now=reference_time,
    ):
        raw_findings.append(
            (
                source_records[finding.source_id],
                _finding_kind(finding.kind),
                finding.severity,
                finding.evidence,
            )
        )

    proposals = tuple(
        sorted(
            (
                _proposal_for(
                    stored, finding_kind, severity, reason, tenant=tenant, policy=policy
                )
                for stored, finding_kind, severity, reason in raw_findings
            ),
            key=lambda item: (
                -item.severity,
                item.source_id,
                item.action.value,
                item.proposal_id,
            ),
        )
    )
    return MemoryMaintenancePlan(
        tenant_id=tenant,
        as_of=reference_time,
        policy=policy,
        assessed_source_count=len(candidates),
        proposals=proposals,
    )


def _assert_tenant_scope(
    tenant_id: str,
    entities: tuple[StoredEntity, ...],
    relationships: tuple[StoredRelationship, ...],
) -> None:
    if any(item.tenant_id != tenant_id for item in entities):
        raise CompanyBrainMaintenanceError(
            "maintenance reader returned an entity outside the requested tenant"
        )
    if any(item.tenant_id != tenant_id for item in relationships):
        raise CompanyBrainMaintenanceError(
            "maintenance reader returned a relationship outside the requested tenant"
        )


def _owners_by_source(
    relationships: tuple[StoredRelationship, ...],
    entities: dict[str, StoredEntity],
) -> dict[str, tuple[str, ...]]:
    owner_labels: dict[str, set[str]] = {}
    for stored in relationships:
        relationship = stored.relationship
        if relationship.kind is not RelationshipKind.OWNS:
            continue
        owner = entities.get(relationship.source_id)
        target = entities.get(relationship.target_id)
        if owner is None or target is None or owner.entity.kind is not EntityKind.OWNER:
            continue
        owner_labels.setdefault(target.entity.entity_id, set()).add(owner.entity.label)
    return {
        source_id: tuple(sorted(labels)) for source_id, labels in owner_labels.items()
    }


def _source_updated_at(stored: StoredEntity) -> datetime | None:
    value = stored.entity.metadata.get(_SOURCE_UPDATED_AT_ATTRIBUTE)
    if value is None:
        return None
    try:
        return parse_timestamp(
            value, label=f"{stored.entity.entity_id}.{_SOURCE_UPDATED_AT_ATTRIBUTE}"
        )
    except PayloadValidationError:
        return None


def _finding_kind(kind: KnowledgeDecayKind) -> MemoryMaintenanceFindingKind:
    match kind:
        case KnowledgeDecayKind.STALE:
            return MemoryMaintenanceFindingKind.STALE
        case KnowledgeDecayKind.MISSING_OWNER:
            return MemoryMaintenanceFindingKind.MISSING_OWNER
        case KnowledgeDecayKind.CONFLICT:
            return MemoryMaintenanceFindingKind.CONFLICT
        case _:
            assert_never(kind)


def _action_for(kind: MemoryMaintenanceFindingKind) -> MemoryMaintenanceAction:
    match kind:
        case MemoryMaintenanceFindingKind.STALE:
            return MemoryMaintenanceAction.REQUEST_OWNER_REVIEW
        case MemoryMaintenanceFindingKind.MISSING_OWNER:
            return MemoryMaintenanceAction.ASSIGN_ACCOUNTABLE_OWNER
        case MemoryMaintenanceFindingKind.CONFLICT:
            return MemoryMaintenanceAction.RESOLVE_CONFLICTING_ACTIVE_REVISIONS
        case MemoryMaintenanceFindingKind.MISSING_SOURCE_FRESHNESS:
            return MemoryMaintenanceAction.REPAIR_SOURCE_FRESHNESS_METADATA
        case _:
            assert_never(kind)


def _proposal_for(
    stored: StoredEntity,
    finding_kind: MemoryMaintenanceFindingKind,
    severity: int,
    reason: str,
    *,
    tenant: str,
    policy: MemoryMaintenancePolicy,
) -> MemoryMaintenanceProposal:
    action = _action_for(finding_kind)
    return MemoryMaintenanceProposal(
        proposal_id=_proposal_id(
            stored, finding_kind, action, tenant=tenant, policy=policy
        ),
        tenant_id=tenant,
        source_id=stored.entity.entity_id,
        source_kind=stored.entity.kind,
        source_label=stored.entity.label,
        source_system=stored.provenance.source_system,
        source_record_id=stored.provenance.source_record_id,
        source_revision=stored.provenance.source_revision,
        source_version=stored.version,
        finding_kind=finding_kind,
        action=action,
        severity=severity,
        reason=reason,
        policy_version=policy.policy_version,
    )


def _proposal_id(
    stored: StoredEntity,
    finding_kind: MemoryMaintenanceFindingKind,
    action: MemoryMaintenanceAction,
    *,
    tenant: str,
    policy: MemoryMaintenancePolicy,
) -> str:
    """Hash only immutable proposal semantics, never a clock or source body."""

    payload = {
        "tenant_id": tenant,
        "source_id": stored.entity.entity_id,
        "source_version": stored.version,
        "source_revision": stored.provenance.source_revision,
        "finding_kind": finding_kind.value,
        "action": action.value,
        "policy_version": policy.policy_version,
        "stale_after_days": policy.stale_after_days,
        "eligible_kinds": [kind.value for kind in policy.eligible_kinds],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "maintenance:" + hashlib.sha256(encoded).hexdigest()
