"""Non-authorizing evidence contract for a PR Guardian advisory review.

This module binds a shadow report to retained evidence references before a
human promotion review. It deliberately cannot change repository configuration,
enable a GitHub check, or authorize advisory/enforcement mode. An evidence
reference describes an external record; it is not proof that the record exists
or that a reviewer approved a product change.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal, Mapping, Sequence

from company_brain.product_contracts import EvidenceBasis, ProductContractError

from .pr_guardian_shadow import canonical_json_sha256


MINIMUM_EVIDENCE_RETENTION_DAYS = 90
MINIMUM_JOINED_OBSERVATIONS = 30
MINIMUM_REVIEWER_CLASSIFICATIONS = 30
MINIMUM_CONFIRMED_RISKS = 5
MINIMUM_SIMULATED_BLOCK_PRECISION = 0.50
MINIMUM_SIMULATED_BLOCK_RECALL = 0.80

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}$")
_PILOT_ID = re.compile(r"^pr-guardian-[a-z0-9][a-z0-9-]{2,79}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PLACEHOLDER_PARTS = frozenset({"example", "replace", "tbd", "todo", "undeclared"})


class PromotionReviewPacketError(ProductContractError):
    """A proposed advisory-review packet is incomplete or unsafe."""


class RetainedEvidencePurpose(StrEnum):
    """The external evidence categories required before human review."""

    SHADOW_OUTCOME_EXPORT = "shadow-outcome-export"
    SHADOW_REPORT = "shadow-report"
    CITATION_QUALITY_REVIEW = "citation-quality-review"
    PERFORMANCE_AND_COST_REPORT = "performance-and-cost-report"
    INDEPENDENT_POST_MERGE_CORRELATION = "independent-post-merge-correlation"


class RequiredReviewRole(StrEnum):
    """Human roles that must review a complete packet outside this process."""

    DEVELOPER_EXPERIENCE = "developer-experience"
    SECURITY_SRE = "security-sre"
    SERVICE_OWNER = "service-owner"


REQUIRED_EVIDENCE_PURPOSES = frozenset(RetainedEvidencePurpose)
REQUIRED_REVIEW_ROLES: tuple[RequiredReviewRole, ...] = (
    RequiredReviewRole.DEVELOPER_EXPERIENCE,
    RequiredReviewRole.SECURITY_SRE,
    RequiredReviewRole.SERVICE_OWNER,
)
_PROMOTION_REQUIREMENTS = frozenset(
    {
        "minimum_joined_observations",
        "minimum_reviewer_classifications",
        "minimum_confirmed_risks",
        "minimum_simulated_block_precision",
        "minimum_simulated_block_recall",
    }
)


@dataclass(frozen=True)
class RetainedEvidenceReference:
    """A pointer to externally retained evidence with its integrity controls."""

    evidence_id: str
    purpose: RetainedEvidencePurpose
    basis: EvidenceBasis
    source_system: str
    locator: str
    content_digest: str
    retention_days: int
    access_control_ref: str
    immutability_control_ref: str
    produced_by: str
    independently_verified_by: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.evidence_id, "evidence_id")
        if self.purpose not in set(RetainedEvidencePurpose):
            raise PromotionReviewPacketError("evidence purpose is invalid")
        if self.basis not in set(EvidenceBasis):
            raise PromotionReviewPacketError("evidence basis is invalid")
        _non_placeholder_text(self.source_system, "source_system", maximum=160)
        _non_placeholder_text(self.locator, "locator", maximum=500)
        _digest(self.content_digest, "content_digest")
        if (
            type(self.retention_days) is not int
            or self.retention_days < MINIMUM_EVIDENCE_RETENTION_DAYS
        ):
            raise PromotionReviewPacketError(
                f"retention_days must be an integer >= {MINIMUM_EVIDENCE_RETENTION_DAYS}"
            )
        _non_placeholder_text(
            self.access_control_ref, "access_control_ref", maximum=500
        )
        _non_placeholder_text(
            self.immutability_control_ref,
            "immutability_control_ref",
            maximum=500,
        )
        _named_identity(self.produced_by, "produced_by")
        if self.independently_verified_by is not None:
            _named_identity(self.independently_verified_by, "independently_verified_by")
        combined = f"{self.source_system} {self.locator}".casefold()
        if (
            "github actions" in combined
            or "github-actions" in combined
            or "/actions/runs/" in combined
        ):
            raise PromotionReviewPacketError(
                "retained evidence must reference an approved external system, not an Actions artifact"
            )
        if self.purpose is RetainedEvidencePurpose.SHADOW_OUTCOME_EXPORT:
            if self.basis is not EvidenceBasis.MEASURED:
                raise PromotionReviewPacketError(
                    "shadow-outcome-export evidence must be measured"
                )
        elif self.purpose is RetainedEvidencePurpose.SHADOW_REPORT:
            if self.basis is not EvidenceBasis.DERIVED:
                raise PromotionReviewPacketError(
                    "shadow-report evidence must be derived"
                )
        elif self.purpose is RetainedEvidencePurpose.INDEPENDENT_POST_MERGE_CORRELATION:
            if self.basis is not EvidenceBasis.MEASURED:
                raise PromotionReviewPacketError(
                    "independent-post-merge-correlation evidence must be measured"
                )
            if self.independently_verified_by is None:
                raise PromotionReviewPacketError(
                    "independent-post-merge-correlation requires an independent verifier"
                )
            if self.independently_verified_by == self.produced_by:
                raise PromotionReviewPacketError(
                    "independent-post-merge-correlation verifier must differ from producer"
                )
        elif self.basis is EvidenceBasis.MODELED:
            raise PromotionReviewPacketError(
                "citation and performance evidence cannot be modeled for an advisory review"
            )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "evidence_id": self.evidence_id,
            "purpose": self.purpose.value,
            "basis": self.basis.value,
            "source_system": self.source_system,
            "locator": self.locator,
            "content_digest": self.content_digest,
            "retention_days": self.retention_days,
            "access_control_ref": self.access_control_ref,
            "immutability_control_ref": self.immutability_control_ref,
            "produced_by": self.produced_by,
        }
        if self.independently_verified_by is not None:
            payload["independently_verified_by"] = self.independently_verified_by
        return payload


@dataclass(frozen=True)
class FeedbackLoopSummary:
    """The minimum measurable feedback loop extracted from a shadow report."""

    report_evidence_id: str
    outcome_export_evidence_id: str
    report_digest: str
    outcome_export_digest: str
    joined_observations: int
    reviewer_classifications: int
    confirmed_risks: int
    simulated_block_precision: float
    simulated_block_recall: float
    report_decision: Literal["advisory-candidate"] = "advisory-candidate"
    blocking_authorized: Literal[False] = False

    def __post_init__(self) -> None:
        _identifier(self.report_evidence_id, "feedback.report_evidence_id")
        _identifier(
            self.outcome_export_evidence_id, "feedback.outcome_export_evidence_id"
        )
        _digest(self.report_digest, "feedback.report_digest")
        _digest(self.outcome_export_digest, "feedback.outcome_export_digest")
        for value, minimum, label in (
            (
                self.joined_observations,
                MINIMUM_JOINED_OBSERVATIONS,
                "feedback.joined_observations",
            ),
            (
                self.reviewer_classifications,
                MINIMUM_REVIEWER_CLASSIFICATIONS,
                "feedback.reviewer_classifications",
            ),
            (self.confirmed_risks, MINIMUM_CONFIRMED_RISKS, "feedback.confirmed_risks"),
        ):
            if type(value) is not int or value < minimum:
                raise PromotionReviewPacketError(
                    f"{label} must be an integer >= {minimum}"
                )
        if self.reviewer_classifications > self.joined_observations:
            raise PromotionReviewPacketError(
                "feedback.reviewer_classifications cannot exceed joined_observations"
            )
        _ratio(
            self.simulated_block_precision,
            "feedback.simulated_block_precision",
            MINIMUM_SIMULATED_BLOCK_PRECISION,
        )
        _ratio(
            self.simulated_block_recall,
            "feedback.simulated_block_recall",
            MINIMUM_SIMULATED_BLOCK_RECALL,
        )
        if self.report_decision != "advisory-candidate":
            raise PromotionReviewPacketError(
                "feedback.report_decision must be advisory-candidate"
            )
        if self.blocking_authorized is not False:
            raise PromotionReviewPacketError(
                "feedback.blocking_authorized must be false"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "report_evidence_id": self.report_evidence_id,
            "outcome_export_evidence_id": self.outcome_export_evidence_id,
            "report_digest": self.report_digest,
            "outcome_export_digest": self.outcome_export_digest,
            "joined_observations": self.joined_observations,
            "reviewer_classifications": self.reviewer_classifications,
            "confirmed_risks": self.confirmed_risks,
            "simulated_block_precision": self.simulated_block_precision,
            "simulated_block_recall": self.simulated_block_recall,
            "report_decision": self.report_decision,
            "blocking_authorized": self.blocking_authorized,
        }


@dataclass(frozen=True)
class AdvisoryPromotionReviewPacket:
    """A complete, expiring input to human review, never a product authorization."""

    pilot_id: str
    repository: str
    policy_version: str
    pilot_manifest_digest: str
    runtime_configuration_digest: str
    prepared_on: str
    review_expires_on: str
    feedback: FeedbackLoopSummary
    retained_evidence: tuple[RetainedEvidenceReference, ...]
    required_review_roles: tuple[RequiredReviewRole, ...] = REQUIRED_REVIEW_ROLES
    schema_version: Literal[1] = 1
    runtime_mode: Literal["shadow"] = "shadow"
    review_state: Literal["human-review-required"] = "human-review-required"

    def __post_init__(self) -> None:
        pilot_id = _non_placeholder_text(self.pilot_id, "pilot_id", maximum=80)
        if not _PILOT_ID.fullmatch(pilot_id):
            raise PromotionReviewPacketError(
                "pilot_id must be pr-guardian- followed by lowercase words"
            )
        repository = _non_placeholder_text(self.repository, "repository", maximum=200)
        if not _REPOSITORY.fullmatch(repository):
            raise PromotionReviewPacketError("repository is invalid")
        _non_placeholder_text(self.policy_version, "policy_version", maximum=120)
        _digest(self.pilot_manifest_digest, "pilot_manifest_digest")
        _digest(self.runtime_configuration_digest, "runtime_configuration_digest")
        prepared_on = _iso_date(self.prepared_on, "prepared_on")
        review_expires_on = _iso_date(self.review_expires_on, "review_expires_on")
        if review_expires_on < prepared_on:
            raise PromotionReviewPacketError("review_expires_on precedes prepared_on")
        if not isinstance(self.feedback, FeedbackLoopSummary):
            raise PromotionReviewPacketError("feedback is invalid")
        _retained_evidence_by_purpose(self.retained_evidence)
        if self.required_review_roles != REQUIRED_REVIEW_ROLES:
            raise PromotionReviewPacketError(
                "required_review_roles must name the reviewed PR Guardian promotion roles"
            )
        if self.schema_version != 1:
            raise PromotionReviewPacketError("schema_version must be 1")
        if self.runtime_mode != "shadow":
            raise PromotionReviewPacketError(
                "runtime_mode must remain shadow during review"
            )
        if self.review_state != "human-review-required":
            raise PromotionReviewPacketError(
                "review_state must be human-review-required"
            )
        evidence_by_purpose = _retained_evidence_by_purpose(self.retained_evidence)
        report = evidence_by_purpose[RetainedEvidencePurpose.SHADOW_REPORT]
        export = evidence_by_purpose[RetainedEvidencePurpose.SHADOW_OUTCOME_EXPORT]
        if report.evidence_id != self.feedback.report_evidence_id:
            raise PromotionReviewPacketError(
                "feedback.report_evidence_id must name shadow-report evidence"
            )
        if export.evidence_id != self.feedback.outcome_export_evidence_id:
            raise PromotionReviewPacketError(
                "feedback.outcome_export_evidence_id must name shadow-outcome-export evidence"
            )
        if report.content_digest != self.feedback.report_digest:
            raise PromotionReviewPacketError(
                "shadow-report evidence digest does not match feedback"
            )
        if export.content_digest != self.feedback.outcome_export_digest:
            raise PromotionReviewPacketError(
                "shadow-outcome-export evidence digest does not match feedback"
            )

    @property
    def advisory_or_enforcement_authorized(self) -> Literal[False]:
        """A packet may request review but cannot change product authority."""

        return False

    def is_current_on(self, day: date) -> bool:
        """Whether the packet still has a live human-review window."""

        return date.fromisoformat(self.review_expires_on) >= day

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "pr-guardian-advisory-review-packet",
            "pilot_id": self.pilot_id,
            "repository": self.repository,
            "policy_version": self.policy_version,
            "pilot_manifest_digest": self.pilot_manifest_digest,
            "runtime_configuration_digest": self.runtime_configuration_digest,
            "prepared_on": self.prepared_on,
            "review_expires_on": self.review_expires_on,
            "runtime_mode": self.runtime_mode,
            "review_state": self.review_state,
            "feedback": self.feedback.to_payload(),
            "retained_evidence": [item.to_payload() for item in self.retained_evidence],
            "required_review_roles": [
                item.value for item in self.required_review_roles
            ],
        }


_PACKET_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "pilot_id",
        "repository",
        "policy_version",
        "pilot_manifest_digest",
        "runtime_configuration_digest",
        "prepared_on",
        "review_expires_on",
        "runtime_mode",
        "review_state",
        "feedback",
        "retained_evidence",
        "required_review_roles",
    }
)
_FEEDBACK_FIELDS = frozenset(
    {
        "report_evidence_id",
        "outcome_export_evidence_id",
        "report_digest",
        "outcome_export_digest",
        "joined_observations",
        "reviewer_classifications",
        "confirmed_risks",
        "simulated_block_precision",
        "simulated_block_recall",
        "report_decision",
        "blocking_authorized",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "purpose",
        "basis",
        "source_system",
        "locator",
        "content_digest",
        "retention_days",
        "access_control_ref",
        "immutability_control_ref",
        "produced_by",
        "independently_verified_by",
    }
)
_EVIDENCE_OPTIONAL_FIELDS = frozenset({"independently_verified_by"})
_REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "scope",
        "input_provenance",
        "sample",
        "simulated_block_decision",
        "utility",
        "calibration",
        "promotion_readiness",
        "limitations",
    }
)


def feedback_summary_from_shadow_report(
    report: Mapping[str, object],
    *,
    report_evidence_id: str,
    outcome_export_evidence_id: str,
) -> FeedbackLoopSummary:
    """Extract a promotion-safe summary from a complete generated shadow report.

    This validates the report's candidate decision and input fingerprint. It
    cannot attest that either JSON document was retained in the referenced
    external system; that remains an operator and reviewer responsibility.
    """

    _exact_keys(report, _REPORT_FIELDS, "shadow report")
    if (
        report.get("schema_version") != 1
        or report.get("kind") != "pr-guardian-shadow-report"
    ):
        raise PromotionReviewPacketError("unsupported shadow report schema")
    input_provenance = _mapping(
        report.get("input_provenance"), "shadow report input_provenance"
    )
    _exact_keys(
        input_provenance,
        {"canonical_outcome_export_sha256", "closure_records", "canonicalization"},
        "shadow report input_provenance",
    )
    outcome_export_digest = _digest(
        input_provenance.get("canonical_outcome_export_sha256"),
        "shadow report input_provenance.canonical_outcome_export_sha256",
    )
    sample = _mapping(report.get("sample"), "shadow report sample")
    _exact_keys(
        sample,
        {
            "closure_records",
            "joined_observations",
            "reviewer_classifications",
            "confirmed_risks",
            "utility_responses",
        },
        "shadow report sample",
    )
    closure_records = _non_negative_int(
        sample.get("closure_records"), "shadow report sample.closure_records"
    )
    if closure_records != _non_negative_int(
        input_provenance.get("closure_records"),
        "shadow report input_provenance.closure_records",
    ):
        raise PromotionReviewPacketError(
            "shadow report input provenance does not match sample"
        )
    decision = _mapping(
        report.get("simulated_block_decision"), "shadow report simulated_block_decision"
    )
    _exact_keys(
        decision,
        {
            "true_positive",
            "false_positive",
            "true_negative",
            "false_negative",
            "precision",
            "recall",
        },
        "shadow report simulated_block_decision",
    )
    readiness = _mapping(
        report.get("promotion_readiness"), "shadow report promotion_readiness"
    )
    _exact_keys(
        readiness,
        {
            "requirements",
            "unmet_requirements",
            "blocking_authorized",
            "decision",
            "next_review",
        },
        "shadow report promotion_readiness",
    )
    requirements = _mapping(
        readiness.get("requirements"), "shadow report promotion requirements"
    )
    _exact_keys(
        requirements, _PROMOTION_REQUIREMENTS, "shadow report promotion requirements"
    )
    if any(value is not True for value in requirements.values()):
        raise PromotionReviewPacketError(
            "shadow report does not meet every promotion requirement"
        )
    unmet = readiness.get("unmet_requirements")
    if not isinstance(unmet, list) or unmet:
        raise PromotionReviewPacketError(
            "shadow report must have no unmet promotion requirements"
        )
    if readiness.get("decision") != "advisory-candidate":
        raise PromotionReviewPacketError(
            "shadow report decision must be advisory-candidate"
        )
    if readiness.get("blocking_authorized") is not False:
        raise PromotionReviewPacketError(
            "shadow report blocking_authorized must be false"
        )
    return FeedbackLoopSummary(
        report_evidence_id=report_evidence_id,
        outcome_export_evidence_id=outcome_export_evidence_id,
        report_digest=canonical_json_sha256(dict(report)),
        outcome_export_digest=outcome_export_digest,
        joined_observations=_non_negative_int(
            sample.get("joined_observations"),
            "shadow report sample.joined_observations",
        ),
        reviewer_classifications=_non_negative_int(
            sample.get("reviewer_classifications"),
            "shadow report sample.reviewer_classifications",
        ),
        confirmed_risks=_non_negative_int(
            sample.get("confirmed_risks"), "shadow report sample.confirmed_risks"
        ),
        simulated_block_precision=_report_ratio(
            decision.get("precision"),
            "shadow report simulated_block_decision.precision",
        ),
        simulated_block_recall=_report_ratio(
            decision.get("recall"), "shadow report simulated_block_decision.recall"
        ),
    )


def parse_advisory_promotion_review_packet(
    payload: object,
    *,
    today: date | None = None,
) -> AdvisoryPromotionReviewPacket:
    """Parse an exact JSON review packet and fail closed after its expiry."""

    raw = _mapping(payload, "advisory promotion review packet")
    _exact_keys(raw, _PACKET_FIELDS, "advisory promotion review packet")
    if raw.get("schema_version") != 1:
        raise PromotionReviewPacketError("schema_version must be 1")
    if raw.get("kind") != "pr-guardian-advisory-review-packet":
        raise PromotionReviewPacketError("kind is invalid")
    packet = AdvisoryPromotionReviewPacket(
        pilot_id=_text(raw.get("pilot_id"), "pilot_id", maximum=80),
        repository=_text(raw.get("repository"), "repository", maximum=200),
        policy_version=_text(raw.get("policy_version"), "policy_version", maximum=120),
        pilot_manifest_digest=_digest(
            raw.get("pilot_manifest_digest"), "pilot_manifest_digest"
        ),
        runtime_configuration_digest=_digest(
            raw.get("runtime_configuration_digest"), "runtime_configuration_digest"
        ),
        prepared_on=_text(raw.get("prepared_on"), "prepared_on", maximum=10),
        review_expires_on=_text(
            raw.get("review_expires_on"), "review_expires_on", maximum=10
        ),
        feedback=_feedback_summary(raw.get("feedback")),
        retained_evidence=_retained_evidence(raw.get("retained_evidence")),
        required_review_roles=_review_roles(raw.get("required_review_roles")),
        runtime_mode=_shadow_mode(raw.get("runtime_mode")),
        review_state=_review_required(raw.get("review_state")),
    )
    day = today or datetime.now(timezone.utc).date()
    if not packet.is_current_on(day):
        raise PromotionReviewPacketError(
            "review packet has expired and must be regenerated"
        )
    return packet


def validate_packet_against_shadow_report(
    packet: AdvisoryPromotionReviewPacket,
    report: Mapping[str, object],
) -> None:
    """Bind a packet's feedback claim to the actual generated report content."""

    expected = feedback_summary_from_shadow_report(
        report,
        report_evidence_id=packet.feedback.report_evidence_id,
        outcome_export_evidence_id=packet.feedback.outcome_export_evidence_id,
    )
    if expected != packet.feedback:
        raise PromotionReviewPacketError(
            "packet feedback does not match the supplied generated shadow report"
        )


def _feedback_summary(value: object) -> FeedbackLoopSummary:
    raw = _mapping(value, "feedback")
    _exact_keys(raw, _FEEDBACK_FIELDS, "feedback")
    return FeedbackLoopSummary(
        report_evidence_id=_text(
            raw.get("report_evidence_id"), "feedback.report_evidence_id", maximum=240
        ),
        outcome_export_evidence_id=_text(
            raw.get("outcome_export_evidence_id"),
            "feedback.outcome_export_evidence_id",
            maximum=240,
        ),
        report_digest=_digest(raw.get("report_digest"), "feedback.report_digest"),
        outcome_export_digest=_digest(
            raw.get("outcome_export_digest"), "feedback.outcome_export_digest"
        ),
        joined_observations=_non_negative_int(
            raw.get("joined_observations"), "feedback.joined_observations"
        ),
        reviewer_classifications=_non_negative_int(
            raw.get("reviewer_classifications"), "feedback.reviewer_classifications"
        ),
        confirmed_risks=_non_negative_int(
            raw.get("confirmed_risks"), "feedback.confirmed_risks"
        ),
        simulated_block_precision=_report_ratio(
            raw.get("simulated_block_precision"), "feedback.simulated_block_precision"
        ),
        simulated_block_recall=_report_ratio(
            raw.get("simulated_block_recall"), "feedback.simulated_block_recall"
        ),
        report_decision=_advisory_candidate(raw.get("report_decision")),
        blocking_authorized=_false(
            raw.get("blocking_authorized"), "feedback.blocking_authorized"
        ),
    )


def _retained_evidence(value: object) -> tuple[RetainedEvidenceReference, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise PromotionReviewPacketError(
            "retained_evidence must be a non-empty JSON array"
        )
    references = tuple(_retained_evidence_reference(item) for item in value)
    _retained_evidence_by_purpose(references)
    return references


def _retained_evidence_reference(value: object) -> RetainedEvidenceReference:
    raw = _mapping(value, "retained evidence")
    if not set(raw).issubset(_EVIDENCE_FIELDS) or not (
        _EVIDENCE_FIELDS - _EVIDENCE_OPTIONAL_FIELDS
    ).issubset(raw):
        raise PromotionReviewPacketError(
            "retained evidence has unexpected or missing fields"
        )
    purpose_text = _text(raw.get("purpose"), "retained evidence purpose", maximum=80)
    basis_text = _text(raw.get("basis"), "retained evidence basis", maximum=40)
    try:
        purpose = RetainedEvidencePurpose(purpose_text)
    except ValueError as error:
        raise PromotionReviewPacketError(
            "retained evidence purpose is invalid"
        ) from error
    try:
        basis = EvidenceBasis(basis_text)
    except ValueError as error:
        raise PromotionReviewPacketError(
            "retained evidence basis is invalid"
        ) from error
    verified_by = raw.get("independently_verified_by")
    return RetainedEvidenceReference(
        evidence_id=_text(
            raw.get("evidence_id"), "retained evidence evidence_id", maximum=240
        ),
        purpose=purpose,
        basis=basis,
        source_system=_text(
            raw.get("source_system"), "retained evidence source_system", maximum=160
        ),
        locator=_text(raw.get("locator"), "retained evidence locator", maximum=500),
        content_digest=_digest(
            raw.get("content_digest"), "retained evidence content_digest"
        ),
        retention_days=_non_negative_int(
            raw.get("retention_days"), "retained evidence retention_days"
        ),
        access_control_ref=_text(
            raw.get("access_control_ref"),
            "retained evidence access_control_ref",
            maximum=500,
        ),
        immutability_control_ref=_text(
            raw.get("immutability_control_ref"),
            "retained evidence immutability_control_ref",
            maximum=500,
        ),
        produced_by=_text(
            raw.get("produced_by"), "retained evidence produced_by", maximum=200
        ),
        independently_verified_by=(
            _text(
                verified_by, "retained evidence independently_verified_by", maximum=200
            )
            if verified_by is not None
            else None
        ),
    )


def _retained_evidence_by_purpose(
    evidence: tuple[RetainedEvidenceReference, ...],
) -> dict[RetainedEvidencePurpose, RetainedEvidenceReference]:
    if evidence != tuple(sorted(evidence, key=lambda item: item.evidence_id)):
        raise PromotionReviewPacketError(
            "retained_evidence must be sorted by evidence_id"
        )
    by_purpose = {item.purpose: item for item in evidence}
    if (
        len(by_purpose) != len(evidence)
        or set(by_purpose) != REQUIRED_EVIDENCE_PURPOSES
    ):
        raise PromotionReviewPacketError(
            "retained_evidence must contain each required evidence purpose exactly once"
        )
    if len({item.evidence_id for item in evidence}) != len(evidence):
        raise PromotionReviewPacketError(
            "retained_evidence evidence_id values must be unique"
        )
    return by_purpose


def _review_roles(value: object) -> tuple[RequiredReviewRole, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PromotionReviewPacketError("required_review_roles must be a JSON array")
    roles: list[RequiredReviewRole] = []
    for item in value:
        try:
            roles.append(
                RequiredReviewRole(_text(item, "required_review_roles", maximum=80))
            )
        except ValueError as error:
            raise PromotionReviewPacketError(
                "required_review_roles is invalid"
            ) from error
    return tuple(roles)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PromotionReviewPacketError(f"{label} must be a JSON object")
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str] | set[str], label: str
) -> None:
    if set(value) != set(expected):
        raise PromotionReviewPacketError(f"{label} has unexpected or missing fields")


def _text(value: object, label: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\n" in value
    ):
        raise PromotionReviewPacketError(f"{label} is invalid")
    return value


def _non_placeholder_text(value: object, label: str, *, maximum: int) -> str:
    text = _text(value, label, maximum=maximum)
    if any(part in text.casefold() for part in _PLACEHOLDER_PARTS):
        raise PromotionReviewPacketError(f"{label} must not contain a placeholder")
    return text


def _identifier(value: object, label: str) -> str:
    text = _non_placeholder_text(value, label, maximum=240)
    if not _IDENTIFIER.fullmatch(text):
        raise PromotionReviewPacketError(f"{label} is invalid")
    return text


def _named_identity(value: object, label: str) -> str:
    return _identifier(value, label)


def _digest(value: object, label: str) -> str:
    digest = _text(value, label, maximum=80)
    if not _SHA256.fullmatch(digest):
        raise PromotionReviewPacketError(f"{label} must be a lowercase sha256 digest")
    return digest


def _non_negative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PromotionReviewPacketError(f"{label} must be a non-negative integer")
    return value


def _ratio(value: object, label: str, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise PromotionReviewPacketError(f"{label} must be a number")
    ratio = float(value)
    if not math.isfinite(ratio) or not 0 <= ratio <= 1 or ratio < minimum:
        raise PromotionReviewPacketError(
            f"{label} must be between {minimum:.2f} and 1.00"
        )
    return ratio


def _report_ratio(value: object, label: str) -> float:
    if value is None:
        raise PromotionReviewPacketError(
            f"{label} must be present for an advisory candidate"
        )
    return _ratio(value, label, 0.0)


def _iso_date(value: object, label: str) -> date:
    text = _text(value, label, maximum=10)
    if not _ISO_DATE.fullmatch(text):
        raise PromotionReviewPacketError(f"{label} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise PromotionReviewPacketError(
            f"{label} must be an ISO date (YYYY-MM-DD)"
        ) from error


def _shadow_mode(value: object) -> Literal["shadow"]:
    if value != "shadow":
        raise PromotionReviewPacketError("runtime_mode must be shadow")
    return "shadow"


def _review_required(value: object) -> Literal["human-review-required"]:
    if value != "human-review-required":
        raise PromotionReviewPacketError("review_state must be human-review-required")
    return "human-review-required"


def _advisory_candidate(value: object) -> Literal["advisory-candidate"]:
    if value != "advisory-candidate":
        raise PromotionReviewPacketError(
            "feedback.report_decision must be advisory-candidate"
        )
    return "advisory-candidate"


def _false(value: object, label: str) -> Literal[False]:
    if value is not False:
        raise PromotionReviewPacketError(f"{label} must be false")
    return False
