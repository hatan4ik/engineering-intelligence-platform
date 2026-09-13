"""Bounded, evidence-qualified explanations derived from Company Brain context.

``DecisionContext`` is an internal product contract for answering *why* a
qualified world-model result matters.  It contains only relationship claims
that are fresh, authorized, sufficiently confident, and conflict-free for the
requesting principal.  It never carries source bodies or action authority.

The contract is deliberately distinct from a public presentation.  A caller
must apply the audience's authorization boundary before rendering evidence
pointers or relationship labels outside an authenticated Company Brain
experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from .model import RelationshipKind
from .product_contracts import (
    EntityId,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    ProductContractError,
    resolve_entity_id,
)
from .world_model import FactFreshness, QualifiedWorldModelContext, RelationshipQualification


@dataclass(frozen=True)
class DecisionContextRelationship:
    """One source-backed, decision-usable relationship claim.

    The referenced evidence is authorized for the principal that requested the
    source ``QualifiedWorldModelContext``.  It is not implicitly authorized for
    another user or for a GitHub-comment audience.
    """

    source_id: EntityId | str
    source_label: str
    relationship: RelationshipKind
    target_id: EntityId | str
    target_label: str
    confidence: float
    freshness: FactFreshness
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        source_id = resolve_entity_id(str(self.source_id))
        target_id = resolve_entity_id(str(self.target_id))
        if source_id == target_id:
            raise ProductContractError("decision-context relationship endpoints must differ")
        _text(self.source_label, "decision-context source_label", maximum=300)
        _text(self.target_label, "decision-context target_label", maximum=300)
        if not isinstance(self.relationship, RelationshipKind):
            raise ProductContractError("decision-context relationship kind is invalid")
        if self.relationship is RelationshipKind.HAS_EVIDENCE:
            raise ProductContractError("evidence links are not decision-context relationship claims")
        if not 0.0 < self.confidence <= 1.0:
            raise ProductContractError("decision-context relationship confidence is invalid")
        if self.freshness is not FactFreshness.FRESH:
            raise ProductContractError("decision-context relationship freshness must be fresh")
        if not self.evidence:
            raise ProductContractError("decision-context relationship requires authorized evidence")
        if self.evidence != tuple(sorted(self.evidence, key=lambda item: str(item.evidence_id))):
            raise ProductContractError("decision-context relationship evidence must be sorted")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ProductContractError("decision-context relationship evidence must be unique")

    @property
    def statement(self) -> str:
        """A deterministic, source-free statement of the relationship claim."""

        return f"{self.source_label} {describe_relationship(self.relationship)} {self.target_label}"


@dataclass(frozen=True)
class DecisionContext:
    """A bounded explanation prepared for one authorized world-model query.

    ``evidence`` is the complete authorized evidence inventory retained by the
    source context.  ``relationships`` is the narrower set of evidence-backed
    facts that passed the decision-usable qualification path.
    """

    context_version: str
    qualified: bool
    confidence: float
    relationships: tuple[DecisionContextRelationship, ...]
    evidence: EvidenceBundle
    limitations: tuple[str, ...]
    conflict_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.context_version, "decision-context context_version", maximum=240)
        if type(self.qualified) is not bool:
            raise ProductContractError("decision-context qualified is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ProductContractError("decision-context confidence is invalid")
        if self.relationships != tuple(sorted(self.relationships, key=_relationship_key)):
            raise ProductContractError("decision-context relationships must be sorted")
        if len({_relationship_key(item) for item in self.relationships}) != len(self.relationships):
            raise ProductContractError("decision-context relationships must be unique")
        _sorted_unique_texts(self.limitations, "decision-context limitations", maximum=500)
        _sorted_unique_texts(self.conflict_ids, "decision-context conflict_ids", maximum=240)


def decision_context_from_world_model(
    context: QualifiedWorldModelContext,
    *,
    context_version: str,
    qualified: bool,
    limitations: tuple[str, ...],
) -> DecisionContext:
    """Project one qualified world-model result into a stable explanation.

    A relationship is included only when it is usable, conflict-free, not an
    implementation-only evidence edge, and both endpoint labels are already in
    the authorized context.  The function never re-queries storage or widens
    the principal's access.
    """

    labels = {item.entity.entity_id: item.entity.label for item in context.entities}
    relationships = tuple(
        sorted(
            (
                relation
                for item in context.relationships
                if (relation := _relationship_from_qualification(item, labels)) is not None
            ),
            key=_relationship_key,
        )
    )
    normalized_limitations = tuple(sorted(set(limitations)))
    evidence = _evidence_bundle(context, normalized_limitations)
    return DecisionContext(
        context_version=context_version,
        qualified=qualified,
        confidence=context.confidence,
        relationships=relationships,
        evidence=evidence,
        limitations=normalized_limitations,
        conflict_ids=tuple(sorted(conflict.conflict_id for conflict in context.conflicts)),
    )


def describe_relationship(relationship: RelationshipKind) -> str:
    """Render each permissible relationship kind exhaustively."""

    match relationship:
        case RelationshipKind.OWNS:
            return "owns"
        case RelationshipKind.DEPENDS_ON:
            return "depends on"
        case RelationshipKind.CHANGED_BY:
            return "changed because of"
        case RelationshipKind.CAUSED:
            return "caused"
        case RelationshipKind.RESOLVED_BY:
            return "was resolved by"
        case RelationshipKind.GOVERNED_BY:
            return "is governed by"
        case RelationshipKind.BELONGS_TO:
            return "belongs to"
        case RelationshipKind.ASSESSED_BY:
            return "was assessed by"
        case RelationshipKind.HAS_OUTCOME:
            return "has outcome"
        case RelationshipKind.HAS_EVIDENCE:
            raise ProductContractError("evidence links are not decision-context relationship claims")
        case _ as unreachable:
            assert_never(unreachable)


def _relationship_from_qualification(
    qualification: RelationshipQualification,
    labels: dict[str, str],
) -> DecisionContextRelationship | None:
    relationship = qualification.relationship
    if (
        not qualification.usable
        or qualification.conflicts
        or relationship.kind is RelationshipKind.HAS_EVIDENCE
        or relationship.source_id not in labels
        or relationship.target_id not in labels
    ):
        return None
    evidence = tuple(
        sorted(
            (
                EvidenceReference(
                    evidence_id=item.evidence_id,
                    source_kind=item.source_kind,
                    locator=item.citation,
                    revision=item.revision,
                    authorized=True,
                )
                for item in qualification.evidence
                if item.freshness is FactFreshness.FRESH
            ),
            key=lambda item: str(item.evidence_id),
        )
    )
    if not evidence:
        return None
    return DecisionContextRelationship(
        source_id=relationship.source_id,
        source_label=labels[relationship.source_id],
        relationship=relationship.kind,
        target_id=relationship.target_id,
        target_label=labels[relationship.target_id],
        confidence=qualification.confidence,
        freshness=qualification.freshness,
        evidence=evidence,
    )


def _evidence_bundle(
    context: QualifiedWorldModelContext,
    limitations: tuple[str, ...],
) -> EvidenceBundle:
    references = tuple(
        sorted(
            (
                EvidenceReference(
                    evidence_id=item.evidence_id,
                    source_kind=item.source_kind,
                    locator=item.citation,
                    revision=item.revision,
                    authorized=True,
                )
                for item in context.evidence
            ),
            key=lambda item: str(item.evidence_id),
        )
    )
    if references:
        return EvidenceBundle(
            basis=EvidenceBasis.MEASURED,
            references=references,
            limitations=limitations,
        )
    return EvidenceBundle(
        basis=EvidenceBasis.DERIVED,
        references=(),
        limitations=limitations or ("No qualified Company Brain evidence was available.",),
    )


def _relationship_key(
    relationship: DecisionContextRelationship,
) -> tuple[str, str, str]:
    return (
        str(relationship.source_id),
        relationship.relationship.value,
        str(relationship.target_id),
    )


def _text(value: str, label: str, *, maximum: int) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise ProductContractError(f"{label} is invalid")


def _sorted_unique_texts(values: tuple[str, ...], label: str, *, maximum: int) -> None:
    if values != tuple(sorted(set(values))):
        raise ProductContractError(f"{label} must be sorted and unique")
    for value in values:
        _text(value, label, maximum=maximum)
