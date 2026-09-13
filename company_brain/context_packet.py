"""Deterministically bounded Company Brain context for an authorized consumer.

``DecisionContext`` retains every qualified fact needed for audit. A
``ContextPacket`` is its explicitly bounded working subset for a particular
authorized product or agent step. It never copies source bodies, never makes a
new authorization decision, and reports every omitted section rather than
silently presenting a partial context as complete.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum

from .decision_context import DecisionContext, DecisionContextRelationship
from .model import RelationshipKind
from .product_contracts import EvidenceReference, ProductContractError


class ContextPacketError(ProductContractError):
    """Raised when a bounded context packet cannot preserve its safety contract."""


class ContextPacketSection(StrEnum):
    """A packet section whose source material may be deliberately omitted."""

    RELATIONSHIPS = "relationships"
    EVIDENCE = "evidence"
    LIMITATIONS = "limitations"
    CONFLICTS = "conflicts"


class ContextPacketOmissionReason(StrEnum):
    """Why an authorized section did not fit into the working packet."""

    RELATIONSHIP_LIMIT = "relationship_limit"
    EVIDENCE_LIMIT = "evidence_limit"
    ITEM_LIMIT = "item_limit"
    BYTE_LIMIT = "byte_limit"


_MAXIMUM_CONTEXT_PACKET_RELATIONSHIPS = 100
_MAXIMUM_CONTEXT_PACKET_EVIDENCE = 200
_MAXIMUM_CONTEXT_PACKET_LIMITATIONS = 100
_MAXIMUM_CONTEXT_PACKET_CONFLICTS = 100
_MAXIMUM_CONTEXT_PACKET_RENDERED_BYTES = 64 * 1024


@dataclass(frozen=True)
class ContextPacketBudget:
    """Hard, deterministic limits for a consumer's working context.

    ``maximum_rendered_bytes`` applies to the canonical packet JSON, including
    its omission disclosures. It is intentionally a byte limit, not a claimed
    model-token limit: callers with a tokenizer must apply a stricter, explicit
    token budget at their own model boundary.
    """

    maximum_relationships: int = 20
    maximum_evidence: int = 40
    maximum_limitations: int = 12
    maximum_conflicts: int = 12
    maximum_rendered_bytes: int = 12_000

    def __post_init__(self) -> None:
        for value, label, ceiling in (
            (
                self.maximum_relationships,
                "maximum_relationships",
                _MAXIMUM_CONTEXT_PACKET_RELATIONSHIPS,
            ),
            (self.maximum_evidence, "maximum_evidence", _MAXIMUM_CONTEXT_PACKET_EVIDENCE),
            (self.maximum_limitations, "maximum_limitations", _MAXIMUM_CONTEXT_PACKET_LIMITATIONS),
            (self.maximum_conflicts, "maximum_conflicts", _MAXIMUM_CONTEXT_PACKET_CONFLICTS),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ContextPacketError(f"context packet {label} must be between 1 and {ceiling}")
        if (
            type(self.maximum_rendered_bytes) is not int
            or not 1_024 <= self.maximum_rendered_bytes <= _MAXIMUM_CONTEXT_PACKET_RENDERED_BYTES
        ):
            raise ContextPacketError(
                "context packet maximum_rendered_bytes must be between 1024 and 65536"
            )


DEFAULT_CONTEXT_PACKET_BUDGET = ContextPacketBudget()


@dataclass(frozen=True)
class ContextPacketOmission:
    """One counted omission; it carries no omitted source content or labels."""

    section: ContextPacketSection
    reason: ContextPacketOmissionReason
    count: int

    def __post_init__(self) -> None:
        if not isinstance(self.section, ContextPacketSection):
            raise ContextPacketError("context packet omission section is invalid")
        if not isinstance(self.reason, ContextPacketOmissionReason):
            raise ContextPacketError("context packet omission reason is invalid")
        if type(self.count) is not int or self.count < 1:
            raise ContextPacketError("context packet omission count must be a positive integer")


@dataclass(frozen=True)
class ContextPacket:
    """A bounded, reproducible subset of one authorized Decision Context."""

    context_version: str
    qualified: bool
    confidence: float
    relationships: tuple[DecisionContextRelationship, ...]
    evidence: tuple[EvidenceReference, ...]
    limitations: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    omissions: tuple[ContextPacketOmission, ...]
    budget: ContextPacketBudget
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_packet_header(self)
        _validate_packet_budget_counts(self)
        _validate_packet_ordering(self)
        _validate_relationship_evidence(self)
        serialized = self.canonical_json()
        if len(serialized.encode("utf-8")) > self.budget.maximum_rendered_bytes:
            raise ContextPacketError("context packet exceeds maximum_rendered_bytes")
        object.__setattr__(self, "digest", "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest())

    @property
    def complete(self) -> bool:
        """Whether the packet retained every source section of the Decision Context."""

        return not self.omissions

    @property
    def rendered_bytes(self) -> int:
        """The exact size of the stable representation governed by the budget."""

        return len(self.canonical_json().encode("utf-8"))

    def payload(self) -> dict[str, object]:
        """Return the stable, source-body-free representation for an authorized consumer."""

        return _payload(
            context_version=self.context_version,
            qualified=self.qualified,
            confidence=self.confidence,
            relationships=self.relationships,
            evidence=self.evidence,
            limitations=self.limitations,
            conflict_ids=self.conflict_ids,
            omissions=self.omissions,
            budget=self.budget,
        )

    def canonical_json(self) -> str:
        """Encode the packet deterministically for an audit record or bounded prompt."""

        return json.dumps(self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_packet_header(packet: ContextPacket) -> None:
    _text(packet.context_version, "context packet context_version", maximum=240)
    if type(packet.qualified) is not bool:
        raise ContextPacketError("context packet qualified is invalid")
    if not isinstance(packet.budget, ContextPacketBudget):
        raise ContextPacketError("context packet budget is invalid")
    if not 0.0 <= packet.confidence <= 1.0:
        raise ContextPacketError("context packet confidence is invalid")


def _validate_packet_budget_counts(packet: ContextPacket) -> None:
    for values, maximum, label in (
        (packet.relationships, packet.budget.maximum_relationships, "relationships"),
        (packet.evidence, packet.budget.maximum_evidence, "evidence"),
        (packet.limitations, packet.budget.maximum_limitations, "limitations"),
        (packet.conflict_ids, packet.budget.maximum_conflicts, "conflicts"),
    ):
        if len(values) > maximum:
            raise ContextPacketError(f"context packet {label} exceed the configured budget")


def _validate_packet_ordering(packet: ContextPacket) -> None:
    if packet.relationships != tuple(sorted(packet.relationships, key=_relationship_key)):
        raise ContextPacketError("context packet relationships must be sorted")
    if len({_relationship_key(item) for item in packet.relationships}) != len(packet.relationships):
        raise ContextPacketError("context packet relationships must be unique")
    if packet.evidence != tuple(sorted(packet.evidence, key=lambda item: str(item.evidence_id))):
        raise ContextPacketError("context packet evidence must be sorted")
    if len({item.evidence_id for item in packet.evidence}) != len(packet.evidence):
        raise ContextPacketError("context packet evidence must be unique")
    _sorted_unique_texts(packet.limitations, "context packet limitations", maximum=500)
    _sorted_unique_texts(packet.conflict_ids, "context packet conflict_ids", maximum=240)
    if packet.omissions != tuple(sorted(packet.omissions, key=_omission_key)):
        raise ContextPacketError("context packet omissions must be sorted")
    if len({_omission_key(item) for item in packet.omissions}) != len(packet.omissions):
        raise ContextPacketError("context packet omissions must be unique")


def _validate_relationship_evidence(packet: ContextPacket) -> None:
    required_evidence = {
        reference.evidence_id
        for relationship in packet.relationships
        for reference in relationship.evidence
    }
    if not required_evidence.issubset({item.evidence_id for item in packet.evidence}):
        raise ContextPacketError(
            "context packet must retain every evidence reference for an included relationship"
        )


def context_packet_from_decision_context(
    context: DecisionContext,
    *,
    budget: ContextPacketBudget = DEFAULT_CONTEXT_PACKET_BUDGET,
) -> ContextPacket:
    """Build a bounded packet without re-querying or widening a Decision Context.

    An included relationship retains all of its evidence references. If that is
    impossible within the evidence budget, the relationship is omitted as a
    whole and the omission is visible. This prevents a partial citation list
    from making an incomplete claim look fully supported.
    """

    selected_relationships: list[DecisionContextRelationship] = []
    selected_evidence_ids: set[str] = set()
    omissions: dict[tuple[ContextPacketSection, ContextPacketOmissionReason], int] = {}
    for relationship in context.relationships:
        relationship_evidence_ids = {str(item.evidence_id) for item in relationship.evidence}
        if len(selected_relationships) >= budget.maximum_relationships:
            _record_omission(
                omissions,
                ContextPacketSection.RELATIONSHIPS,
                ContextPacketOmissionReason.RELATIONSHIP_LIMIT,
            )
        elif len(selected_evidence_ids | relationship_evidence_ids) > budget.maximum_evidence:
            _record_omission(
                omissions,
                ContextPacketSection.RELATIONSHIPS,
                ContextPacketOmissionReason.EVIDENCE_LIMIT,
            )
        else:
            selected_relationships.append(relationship)
            selected_evidence_ids.update(relationship_evidence_ids)

    selected_extras: list[EvidenceReference] = []
    for reference in context.evidence.references:
        if str(reference.evidence_id) in selected_evidence_ids:
            continue
        if len(selected_evidence_ids) + len(selected_extras) >= budget.maximum_evidence:
            _record_omission(
                omissions,
                ContextPacketSection.EVIDENCE,
                ContextPacketOmissionReason.EVIDENCE_LIMIT,
            )
        else:
            selected_extras.append(reference)

    selected_limitations = list(context.limitations[: budget.maximum_limitations])
    if len(context.limitations) > len(selected_limitations):
        _record_omission(
            omissions,
            ContextPacketSection.LIMITATIONS,
            ContextPacketOmissionReason.ITEM_LIMIT,
            len(context.limitations) - len(selected_limitations),
        )
    selected_conflicts = list(context.conflict_ids[: budget.maximum_conflicts])
    if len(context.conflict_ids) > len(selected_conflicts):
        _record_omission(
            omissions,
            ContextPacketSection.CONFLICTS,
            ContextPacketOmissionReason.ITEM_LIMIT,
            len(context.conflict_ids) - len(selected_conflicts),
        )

    while True:
        if _rendered_bytes(
            context=context,
            relationships=selected_relationships,
            extras=selected_extras,
            limitations=selected_limitations,
            conflicts=selected_conflicts,
            omissions=omissions,
            budget=budget,
        ) <= budget.maximum_rendered_bytes:
            return _packet(
                context=context,
                relationships=selected_relationships,
                extras=selected_extras,
                limitations=selected_limitations,
                conflicts=selected_conflicts,
                omissions=omissions,
                budget=budget,
            )
        if selected_extras:
            selected_extras.pop()
            _record_omission(
                omissions,
                ContextPacketSection.EVIDENCE,
                ContextPacketOmissionReason.BYTE_LIMIT,
            )
            continue
        if selected_limitations:
            selected_limitations.pop()
            _record_omission(
                omissions,
                ContextPacketSection.LIMITATIONS,
                ContextPacketOmissionReason.BYTE_LIMIT,
            )
            continue
        if selected_conflicts:
            selected_conflicts.pop()
            _record_omission(
                omissions,
                ContextPacketSection.CONFLICTS,
                ContextPacketOmissionReason.BYTE_LIMIT,
            )
            continue
        if selected_relationships:
            selected_relationships.pop()
            _record_omission(
                omissions,
                ContextPacketSection.RELATIONSHIPS,
                ContextPacketOmissionReason.BYTE_LIMIT,
            )
            continue
        raise ContextPacketError("context packet budget cannot encode mandatory context fields")


def _packet(
    *,
    context: DecisionContext,
    relationships: list[DecisionContextRelationship],
    extras: list[EvidenceReference],
    limitations: list[str],
    conflicts: list[str],
    omissions: dict[tuple[ContextPacketSection, ContextPacketOmissionReason], int],
    budget: ContextPacketBudget,
) -> ContextPacket:
    evidence = _packet_evidence(relationships, extras)
    return ContextPacket(
        context_version=context.context_version,
        qualified=context.qualified,
        confidence=context.confidence,
        relationships=tuple(relationships),
        evidence=evidence,
        limitations=tuple(limitations),
        conflict_ids=tuple(conflicts),
        omissions=_omissions(omissions),
        budget=budget,
    )


def _rendered_bytes(
    *,
    context: DecisionContext,
    relationships: list[DecisionContextRelationship],
    extras: list[EvidenceReference],
    limitations: list[str],
    conflicts: list[str],
    omissions: dict[tuple[ContextPacketSection, ContextPacketOmissionReason], int],
    budget: ContextPacketBudget,
) -> int:
    payload = _payload(
        context_version=context.context_version,
        qualified=context.qualified,
        confidence=context.confidence,
        relationships=tuple(relationships),
        evidence=_packet_evidence(relationships, extras),
        limitations=tuple(limitations),
        conflict_ids=tuple(conflicts),
        omissions=_omissions(omissions),
        budget=budget,
    )
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _packet_evidence(
    relationships: list[DecisionContextRelationship], extras: list[EvidenceReference]
) -> tuple[EvidenceReference, ...]:
    references: dict[str, EvidenceReference] = {}
    for relationship in relationships:
        for reference in relationship.evidence:
            _add_evidence_reference(references, reference)
    for reference in extras:
        _add_evidence_reference(references, reference)
    return tuple(sorted(references.values(), key=lambda item: str(item.evidence_id)))


def _add_evidence_reference(
    references: dict[str, EvidenceReference], reference: EvidenceReference
) -> None:
    identifier = str(reference.evidence_id)
    prior = references.setdefault(identifier, reference)
    if prior != reference:
        raise ContextPacketError("context packet has conflicting representations of one evidence reference")


def _payload(
    *,
    context_version: str,
    qualified: bool,
    confidence: float,
    relationships: tuple[DecisionContextRelationship, ...],
    evidence: tuple[EvidenceReference, ...],
    limitations: tuple[str, ...],
    conflict_ids: tuple[str, ...],
    omissions: tuple[ContextPacketOmission, ...],
    budget: ContextPacketBudget,
) -> dict[str, object]:
    return {
        "context_version": context_version,
        "qualified": qualified,
        "confidence": confidence,
        "relationships": [_relationship_payload(item) for item in relationships],
        "evidence": [_evidence_payload(item) for item in evidence],
        "limitations": list(limitations),
        "conflict_ids": list(conflict_ids),
        "omissions": [
            {"section": item.section.value, "reason": item.reason.value, "count": item.count}
            for item in omissions
        ],
        "budget": {
            "maximum_relationships": budget.maximum_relationships,
            "maximum_evidence": budget.maximum_evidence,
            "maximum_limitations": budget.maximum_limitations,
            "maximum_conflicts": budget.maximum_conflicts,
            "maximum_rendered_bytes": budget.maximum_rendered_bytes,
        },
    }


def _record_omission(
    omissions: dict[tuple[ContextPacketSection, ContextPacketOmissionReason], int],
    section: ContextPacketSection,
    reason: ContextPacketOmissionReason,
    count: int = 1,
) -> None:
    key = (section, reason)
    omissions[key] = omissions.get(key, 0) + count


def _omissions(
    counts: dict[tuple[ContextPacketSection, ContextPacketOmissionReason], int],
) -> tuple[ContextPacketOmission, ...]:
    return tuple(
        ContextPacketOmission(section=section, reason=reason, count=count)
        for (section, reason), count in sorted(counts.items(), key=lambda item: _omission_key_parts(*item[0]))
    )


def _relationship_payload(relationship: DecisionContextRelationship) -> dict[str, object]:
    return {
        "source_id": str(relationship.source_id),
        "source_label": relationship.source_label,
        "relationship": relationship.relationship.value,
        "target_id": str(relationship.target_id),
        "target_label": relationship.target_label,
        "confidence": relationship.confidence,
        "freshness": relationship.freshness.value,
        "evidence_ids": [str(item.evidence_id) for item in relationship.evidence],
    }


def _evidence_payload(reference: EvidenceReference) -> dict[str, str]:
    return {
        "evidence_id": str(reference.evidence_id),
        "source_kind": reference.source_kind,
        "locator": reference.locator,
        "revision": reference.revision,
    }


def _relationship_key(
    relationship: DecisionContextRelationship,
) -> tuple[str, RelationshipKind, str]:
    return str(relationship.source_id), relationship.relationship, str(relationship.target_id)


def _omission_key(omission: ContextPacketOmission) -> tuple[str, str]:
    return _omission_key_parts(omission.section, omission.reason)


def _omission_key_parts(
    section: ContextPacketSection, reason: ContextPacketOmissionReason
) -> tuple[str, str]:
    return section.value, reason.value


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise ContextPacketError(f"{label} is invalid")
    return value


def _sorted_unique_texts(values: tuple[str, ...], label: str, *, maximum: int) -> None:
    if values != tuple(sorted(set(values))):
        raise ContextPacketError(f"{label} must be sorted and unique")
    for value in values:
        _text(value, label, maximum=maximum)
