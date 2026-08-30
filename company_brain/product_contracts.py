"""Small, typed contracts shared by Company Brain product workflows.

These records carry an already-authorized evidence *reference*, a reviewable
finding, and an explicit human or independently-correlated outcome. They do
not carry source bodies and cannot authorize a merge, deployment, or runbook.
Product packages translate their local vocabulary at this boundary instead of
making Company Brain depend on a particular product such as PR Guardian.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .model import BrainEntity, EntityKind, RelationshipKind


class ProductContractError(ValueError):
    """A cross-product Company Brain record violates a safety or shape rule."""


class EvidenceBasis(StrEnum):
    """How a product obtained the evidence presented with a finding."""

    MEASURED = "measured"
    DERIVED = "derived"
    MODELED = "modeled"


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}$")
_PRODUCT_NAME = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
_ATTRIBUTE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SEVERITIES = frozenset({"low", "moderate", "high", "critical"})


def _required(value: str, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise ProductContractError(f"{label} is invalid")
    return value


def _identifier(value: str, label: str) -> str:
    value = _required(value, label, 240)
    if not _IDENTIFIER.fullmatch(value):
        raise ProductContractError(f"{label} is invalid")
    return value


def _attributes(values: tuple[tuple[str, str], ...], label: str) -> tuple[tuple[str, str], ...]:
    if values != tuple(sorted(values)) or len({name for name, _ in values}) != len(values):
        raise ProductContractError(f"{label} must be sorted and have unique names")
    for name, value in values:
        if not _ATTRIBUTE_NAME.fullmatch(_required(name, f"{label} name", 80)):
            raise ProductContractError(f"{label} name is invalid")
        _required(value, f"{label} value", 500)
    return values


@dataclass(frozen=True)
class EvidenceReference:
    """An ACL-authorized pointer that a product can cite without copying content."""

    evidence_id: str
    source_kind: str
    locator: str
    authorized: bool

    def __post_init__(self) -> None:
        _identifier(self.evidence_id, "evidence_id")
        _required(self.source_kind, "source_kind", 80)
        _required(self.locator, "locator", 500)
        if self.authorized is not True:
            raise ProductContractError("unauthorized evidence cannot enter a product finding")


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence state is explicit even when a query yielded no usable reference."""

    basis: EvidenceBasis
    references: tuple[EvidenceReference, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.basis not in set(EvidenceBasis):
            raise ProductContractError("evidence basis is invalid")
        if self.references != tuple(sorted(self.references, key=lambda item: item.evidence_id)):
            raise ProductContractError("evidence references must be sorted by evidence_id")
        if len({item.evidence_id for item in self.references}) != len(self.references):
            raise ProductContractError("evidence references must be unique")
        if not self.references and not self.limitations:
            raise ProductContractError("missing evidence requires an explicit limitation")
        if self.basis is EvidenceBasis.MEASURED and not self.references:
            raise ProductContractError("measured evidence requires an authorized reference")
        for limitation in self.limitations:
            _required(limitation, "evidence limitation", 500)


@dataclass(frozen=True)
class ProductSubject:
    """A typed Company Brain entity reference owned by a product finding."""

    entity_id: str
    kind: EntityKind
    label: str
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "subject entity_id")
        if self.kind not in set(EntityKind):
            raise ProductContractError("subject kind is invalid")
        _required(self.label, "subject label", 500)
        _attributes(self.attributes, "subject attributes")

    def as_entity(self) -> BrainEntity:
        """Build the bounded entity accepted by the canonical Company Brain model."""

        return BrainEntity(
            entity_id=self.entity_id,
            kind=self.kind,
            label=self.label,
            attributes=self.attributes,
        )


@dataclass(frozen=True)
class FindingProvenance:
    """Versions and qualification state behind a product's derived finding."""

    assessment_version: str
    context_version: str
    context_qualified: bool

    def __post_init__(self) -> None:
        _required(self.assessment_version, "assessment_version", 160)
        _required(self.context_version, "context_version", 240)
        if type(self.context_qualified) is not bool:
            raise ProductContractError("context_qualified is invalid")


@dataclass(frozen=True)
class ProductFinding:
    """A product-neutral, reviewable finding projected into Company Brain memory."""

    finding_id: str
    product: str
    scope: ProductSubject
    subject: ProductSubject
    scope_relationship: RelationshipKind
    severity: str
    summary: str
    correlation_id: str
    evidence: EvidenceBundle
    provenance: FindingProvenance
    recommendation: str

    def __post_init__(self) -> None:
        _identifier(self.finding_id, "finding_id")
        if not _PRODUCT_NAME.fullmatch(_required(self.product, "product", 80)):
            raise ProductContractError("product is invalid")
        if self.scope.entity_id == self.subject.entity_id:
            raise ProductContractError("finding scope and subject must be distinct")
        if self.scope_relationship not in set(RelationshipKind):
            raise ProductContractError("scope_relationship is invalid")
        if self.severity not in _SEVERITIES:
            raise ProductContractError("severity is invalid")
        _required(self.summary, "summary", 1_000)
        _identifier(self.correlation_id, "correlation_id")
        _required(self.recommendation, "recommendation", 160)


@dataclass(frozen=True)
class ProductOutcome:
    """One explicit or independently-correlated outcome associated with a finding."""

    outcome_id: str
    finding_id: str
    outcome_kind: str
    disposition: str
    recorded_by: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.outcome_id, "outcome_id")
        _identifier(self.finding_id, "finding_id")
        if not _PRODUCT_NAME.fullmatch(_required(self.outcome_kind, "outcome_kind", 80)):
            raise ProductContractError("outcome_kind is invalid")
        _required(self.disposition, "disposition", 160)
        if self.recorded_by is not None:
            _required(self.recorded_by, "recorded_by", 200)
        if self.correlation_id is not None:
            _identifier(self.correlation_id, "correlation_id")
