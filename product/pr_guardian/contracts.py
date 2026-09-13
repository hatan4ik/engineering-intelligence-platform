"""Versioned, product-level contracts for PR Guardian.

The existing shadow observation and closure schemas are GitHub workflow transfer
formats. These contracts are the product boundary that future storage, API,
retrieval, and evaluation adapters must share. They deliberately contain no
merge authorization field: a finding can describe only a simulated action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import NewType, assert_never

from company_brain.product_contracts import (
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FindingId,
    ProductContractError,
)

RepositoryName = NewType("RepositoryName", str)
ServiceId = NewType("ServiceId", str)
PrNumber = NewType("PrNumber", int)
EvaluationId = NewType("EvaluationId", str)
HeadSha = NewType("HeadSha", str)


__all__ = [
    "EnforcementPolicy",
    "EnforcementRule",
    "EnforcementWaiver",
    "EvaluationId",
    "EvaluationRun",
    "EvidenceBasis",
    "EvidenceBundle",
    "EvidenceReference",
    "FindingAction",
    "FindingId",
    "FindingOutcome",
    "HeadSha",
    "PRFinding",
    "PrNumber",
    "ProductContractError",
    "ProductMode",
    "RepositoryConfig",
    "RepositoryName",
    "ReviewerRiskDisposition",
    "ReviewerUtilityDisposition",
    "ServiceId",
    "describe_enforcement_rule",
    "describe_finding_action",
    "describe_product_mode",
    "resolve_evaluation_id",
    "resolve_head_sha",
    "resolve_pr_number",
    "resolve_repository_name",
    "resolve_service_id",
]


class ProductMode(StrEnum):
    """The publishing authority a repository has granted this product.

    ``ENFORCE`` exists only because a service owner recorded an approval in
    their own repository configuration.  The platform cannot set it.
    """

    SHADOW = "shadow"
    ADVISORY = "advisory"
    ENFORCE = "enforce"


def describe_product_mode(mode: ProductMode) -> str:
    """Exhaustively describe product operational mode."""
    match mode:
        case ProductMode.SHADOW:
            return "Shadow mode: observations recorded without blocking or developer interruption"
        case ProductMode.ADVISORY:
            return "Advisory mode: observations published as non-blocking comments/checks"
        case ProductMode.ENFORCE:
            return "Enforce mode: policy violations fail checks per repository owner consent"
        case _ as unreachable:
            assert_never(unreachable)


class EnforcementRule(StrEnum):
    """The complete set of conditions that may ever fail a merge check.

    Each rule is deterministic and narrow: it names an artifact class, the
    absence of test evidence, and a risk threshold.  A repository selects
    exactly one; nothing else can block.
    """

    IAC_CHANGE_WITHOUT_TEST_EVIDENCE = "iac-change-without-test-evidence-at-high-risk"
    SECURITY_CHANGE_WITHOUT_TEST_EVIDENCE = (
        "security-boundary-change-without-test-evidence-at-high-risk"
    )


def describe_enforcement_rule(rule: EnforcementRule) -> str:
    """Exhaustively describe enforcement rule trigger."""
    match rule:
        case EnforcementRule.IAC_CHANGE_WITHOUT_TEST_EVIDENCE:
            return "Infrastructure-as-Code changes requiring test evidence at high risk"
        case EnforcementRule.SECURITY_CHANGE_WITHOUT_TEST_EVIDENCE:
            return "Security boundary changes requiring test evidence at high risk"
        case _ as unreachable:
            assert_never(unreachable)


class FindingAction(StrEnum):
    NONE = "none"
    EXTENDED_TESTS = "extended-tests"
    ADDITIONAL_APPROVAL = "additional-approval"
    WOULD_BLOCK = "would-block"


def describe_finding_action(action: FindingAction) -> str:
    """Exhaustively format human-facing description for each simulated action."""
    match action:
        case FindingAction.NONE:
            return "No gating action required"
        case FindingAction.EXTENDED_TESTS:
            return "Extended test suites required prior to merge"
        case FindingAction.ADDITIONAL_APPROVAL:
            return "Additional service-owner approval required"
        case FindingAction.WOULD_BLOCK:
            return "Merge blocked by enforcement policy"
        case _ as unreachable:
            assert_never(unreachable)


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


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_date(value: str, label: str) -> date:
    """Parse a calendar date, refusing anything a human might mistype."""
    _required(value, label, 10)
    if not _ISO_DATE.fullmatch(value):
        raise ProductContractError(f"{label} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # e.g. 2026-13-01
        raise ProductContractError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc


@dataclass(frozen=True)
class EnforcementWaiver:
    """A named owner's time-boxed exemption for one path glob."""

    path_glob: str
    reason: str
    owner: str
    expires_on: str

    def __post_init__(self) -> None:
        _required(self.path_glob, "waivers path_glob", 200)
        _required(self.reason, "waivers reason", 500)
        _required(self.owner, "waivers owner", 200)
        _iso_date(self.expires_on, "waivers expires_on")

    def is_active_on(self, day: date) -> bool:
        return date.fromisoformat(self.expires_on) >= day


@dataclass(frozen=True)
class EnforcementPolicy:
    """One rule, one owner approval, one expiry, and its waiver list.

    The expiry is deliberately mandatory: an enforcement decision has to be
    re-taken by a human on a schedule rather than persisting by inertia.
    """

    rule: EnforcementRule
    threshold: int
    approved_by: str
    approved_on: str
    expires_on: str
    waivers: tuple[EnforcementWaiver, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rule, EnforcementRule):
            raise ProductContractError("enforcement.rule is invalid")
        if type(self.threshold) is not int or not 0 <= self.threshold <= 100:
            raise ProductContractError("enforcement.threshold is invalid")
        _required(self.approved_by, "enforcement.approved_by", 200)
        approved_on = _iso_date(self.approved_on, "enforcement.approved_on")
        expires_on = _iso_date(self.expires_on, "enforcement.expires_on")
        if expires_on < approved_on:
            raise ProductContractError("enforcement.expires_on precedes enforcement.approved_on")
        if len(self.waivers) > 64:
            raise ProductContractError("enforcement.waivers is too large")

    def is_active_on(self, day: date) -> bool:
        return date.fromisoformat(self.expires_on) >= day


def resolve_repository_name(value: str) -> RepositoryName:
    val = _required(value, "repository", 200)
    if not _REPOSITORY.fullmatch(val):
        raise ProductContractError("repository is invalid")
    return RepositoryName(val)


def resolve_service_id(value: str) -> ServiceId:
    return ServiceId(_required(value, "service_id", 160))


def resolve_pr_number(value: int) -> PrNumber:
    if type(value) is not int or value < 1:
        raise ProductContractError("pr_number is invalid")
    return PrNumber(value)


def resolve_head_sha(value: str) -> HeadSha:
    val = _required(value, "head_sha", 64)
    if not _SHA.fullmatch(val):
        raise ProductContractError("head_sha is invalid")
    return HeadSha(val)


def resolve_evaluation_id(value: str) -> EvaluationId:
    return EvaluationId(_required(value, "evaluation_id", 240))


@dataclass(frozen=True)
class RepositoryConfig:
    """Named owner and scope for one product installation in one repository.

    Enforcement is opt-in and owner-signed: the platform can construct this
    record but only a repository's own configuration file supplies
    ``ProductMode.ENFORCE`` together with a complete, unexpired approval.
    """

    repository: RepositoryName | str
    service_ids: tuple[ServiceId | str, ...]
    owner_ids: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    policy_version: str
    mode: ProductMode = ProductMode.SHADOW
    enforcement: EnforcementPolicy | None = None

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(_required(str(self.repository), "repository", 200)):
            raise ProductContractError("repository is invalid")
        _sorted_unique(tuple(str(s) for s in self.service_ids), "service_ids")
        _sorted_unique(self.owner_ids, "owner_ids")
        _sorted_unique(self.evidence_sources, "evidence_sources")
        _required(self.policy_version, "policy_version", 120)
        if not isinstance(self.mode, ProductMode):
            raise ProductContractError("mode is invalid")
        if self.mode is ProductMode.ENFORCE:
            if self.enforcement is None:
                raise ProductContractError("enforcement is required when mode is enforce")
            if self.enforcement.approved_by not in self.owner_ids:
                raise ProductContractError(
                    "enforcement.approved_by must name a declared service owner"
                )
            for waiver in self.enforcement.waivers:
                if waiver.owner not in self.owner_ids:
                    raise ProductContractError("waivers owner must name a declared service owner")
        elif self.enforcement is not None:
            raise ProductContractError("enforcement is allowed only when mode is enforce")


@dataclass(frozen=True)
class PRFinding:
    """One reviewable risk finding; it cannot authorize a merge decision."""

    finding_id: FindingId | str
    repository: RepositoryName | str
    pr_number: PrNumber | int
    head_sha: HeadSha | str
    severity: str
    summary: str
    correlation_id: str
    policy_version: str
    context_version: str
    context_qualified: bool
    simulated_action: FindingAction
    evidence: EvidenceBundle

    def __post_init__(self) -> None:
        _required(str(self.finding_id), "finding_id")
        if not _REPOSITORY.fullmatch(_required(str(self.repository), "repository", 200)):
            raise ProductContractError("repository is invalid")
        if type(self.pr_number) is not int or self.pr_number < 1:
            raise ProductContractError("pr_number is invalid")
        if not _SHA.fullmatch(_required(str(self.head_sha), "head_sha", 64)):
            raise ProductContractError("head_sha is invalid")
        if self.severity not in _SEVERITIES:
            raise ProductContractError("severity is invalid")
        _required(self.summary, "summary", 1_000)
        _required(self.correlation_id, "correlation_id")
        _required(self.policy_version, "policy_version", 120)
        _required(self.context_version, "context_version", 200)
        if type(self.context_qualified) is not bool:
            raise ProductContractError("context_qualified is invalid")
        if not isinstance(self.simulated_action, FindingAction):
            raise ProductContractError("simulated_action is invalid")
        if not self.context_qualified and self.simulated_action is not FindingAction.NONE:
            raise ProductContractError("unqualified context cannot simulate a control")


@dataclass(frozen=True)
class FindingOutcome:
    """Explicit human disposition, not an inferred merge or closure judgment."""

    finding_id: FindingId | str
    reviewer_risk: ReviewerRiskDisposition
    reviewer_utility: ReviewerUtilityDisposition
    recorded_by: str | None = None
    post_merge_correlation_id: str | None = None

    def __post_init__(self) -> None:
        _required(str(self.finding_id), "finding_id")
        if not isinstance(self.reviewer_risk, ReviewerRiskDisposition):
            raise ProductContractError("reviewer_risk is invalid")
        if not isinstance(self.reviewer_utility, ReviewerUtilityDisposition):
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

    evaluation_id: EvaluationId | str
    dataset_version: str
    policy_version: str
    finding_ids: tuple[FindingId | str, ...]
    methodology: str

    def __post_init__(self) -> None:
        _required(str(self.evaluation_id), "evaluation_id")
        _required(self.dataset_version, "dataset_version", 120)
        _required(self.policy_version, "policy_version", 120)
        _sorted_unique(tuple(str(f) for f in self.finding_ids), "finding_ids")
        _required(self.methodology, "methodology", 1_000)
