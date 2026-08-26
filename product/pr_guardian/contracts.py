"""Versioned, product-level contracts for PR Guardian.

The existing shadow observation and closure schemas are GitHub workflow transfer
formats. These contracts are the product boundary that future storage, API,
retrieval, and evaluation adapters must share. They deliberately contain no
merge authorization field: a finding can describe only a simulated action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ProductContractError(ValueError):
    """Raised when a product record violates a safety or shape invariant."""


class ProductMode(StrEnum):
    SHADOW = "shadow"
    ADVISORY = "advisory"


class EvidenceBasis(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    MODELED = "modeled"


class FindingAction(StrEnum):
    NONE = "none"
    EXTENDED_TESTS = "extended-tests"
    ADDITIONAL_APPROVAL = "additional-approval"
    WOULD_BLOCK = "would-block"


class ReviewerRiskDisposition(StrEnum):
    CONFIRMED_RISK = "confirmed-risk"
    FALSE_POSITIVE = "false-positive"
    NOT_REVIEWED = "not-reviewed"


class ReviewerUtilityDisposition(StrEnum):
    USEFUL = "useful"
    NOT_USEFUL = "not-useful"
    NOT_REVIEWED = "not-reviewed"


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{4,64}$")
_SEVERITIES = frozenset({"low", "moderate", "high", "critical"})


def _required(value: str, label: str, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise ProductContractError(f"{label} is invalid")
    return value


def _sorted_unique(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not values or values != tuple(sorted(set(values))):
        raise ProductContractError(f"{label} must be non-empty, sorted, and unique")
    return tuple(_required(value, label, 160) for value in values)


@dataclass(frozen=True)
class RepositoryConfig:
    """Named owner and scope for one non-enforcing product installation."""

    repository: str
    service_ids: tuple[str, ...]
    owner_ids: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    policy_version: str
    mode: ProductMode = ProductMode.SHADOW

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(_required(self.repository, "repository", 200)):
            raise ProductContractError("repository is invalid")
        _sorted_unique(self.service_ids, "service_ids")
        _sorted_unique(self.owner_ids, "owner_ids")
        _sorted_unique(self.evidence_sources, "evidence_sources")
        _required(self.policy_version, "policy_version", 120)
        if self.mode not in {ProductMode.SHADOW, ProductMode.ADVISORY}:
            raise ProductContractError("mode is invalid")


@dataclass(frozen=True)
class EvidenceReference:
    """An ACL-authorized, minimally exposed reference used by a finding."""

    evidence_id: str
    source_kind: str
    locator: str
    authorized: bool

    def __post_init__(self) -> None:
        _required(self.evidence_id, "evidence_id", 200)
        _required(self.source_kind, "source_kind", 80)
        _required(self.locator, "locator", 500)
        if self.authorized is not True:
            raise ProductContractError("unauthorized evidence cannot enter a product finding")


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence state is explicit even when no authorized source was found."""

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
class PRFinding:
    """One reviewable risk finding; it cannot authorize a merge decision."""

    finding_id: str
    repository: str
    pr_number: int
    head_sha: str
    severity: str
    summary: str
    correlation_id: str
    policy_version: str
    simulated_action: FindingAction
    evidence: EvidenceBundle

    def __post_init__(self) -> None:
        _required(self.finding_id, "finding_id")
        if not _REPOSITORY.fullmatch(_required(self.repository, "repository", 200)):
            raise ProductContractError("repository is invalid")
        if type(self.pr_number) is not int or self.pr_number < 1:
            raise ProductContractError("pr_number is invalid")
        if not _SHA.fullmatch(_required(self.head_sha, "head_sha", 64)):
            raise ProductContractError("head_sha is invalid")
        if self.severity not in _SEVERITIES:
            raise ProductContractError("severity is invalid")
        _required(self.summary, "summary", 1_000)
        _required(self.correlation_id, "correlation_id")
        _required(self.policy_version, "policy_version", 120)
        if self.simulated_action not in set(FindingAction):
            raise ProductContractError("simulated_action is invalid")


@dataclass(frozen=True)
class FindingOutcome:
    """Explicit human disposition, not an inferred merge or closure judgment."""

    finding_id: str
    reviewer_risk: ReviewerRiskDisposition
    reviewer_utility: ReviewerUtilityDisposition
    recorded_by: str | None = None
    post_merge_correlation_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.finding_id, "finding_id")
        if self.reviewer_risk not in set(ReviewerRiskDisposition):
            raise ProductContractError("reviewer_risk is invalid")
        if self.reviewer_utility not in set(ReviewerUtilityDisposition):
            raise ProductContractError("reviewer_utility is invalid")
        if self.recorded_by is not None:
            _required(self.recorded_by, "recorded_by", 200)
        if self.post_merge_correlation_id is not None:
            _required(self.post_merge_correlation_id, "post_merge_correlation_id")

    @property
    def is_explicit_reviewer_feedback(self) -> bool:
        return (
            self.reviewer_risk is not ReviewerRiskDisposition.NOT_REVIEWED
            or self.reviewer_utility is not ReviewerUtilityDisposition.NOT_REVIEWED
        )


@dataclass(frozen=True)
class EvaluationRun:
    """A reproducible quality run bound to a dataset and deterministic policy."""

    evaluation_id: str
    dataset_version: str
    policy_version: str
    finding_ids: tuple[str, ...]
    methodology: str

    def __post_init__(self) -> None:
        _required(self.evaluation_id, "evaluation_id")
        _required(self.dataset_version, "dataset_version", 120)
        _required(self.policy_version, "policy_version", 120)
        _sorted_unique(self.finding_ids, "finding_ids")
        _required(self.methodology, "methodology", 1_000)
