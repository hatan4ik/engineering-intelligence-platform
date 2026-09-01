"""Explicit, non-mutating outcomes for Company Brain maintenance proposals.

Maintenance planning creates review-only proposals. This module records the
next two facts without writing to a source system: an explicit human
disposition and, for an accepted proposal, a later source-revision observation
made by a different identity. It never infers acceptance from a missing ticket,
source mutation, or a new Brain projection.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Mapping, assert_never

from .maintenance import (
    CompanyBrainMaintenanceError,
    MemoryMaintenanceAction,
    MemoryMaintenanceFindingKind,
    MemoryMaintenanceProposal,
)
from .model import EntityKind


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLACEHOLDER_PARTS = frozenset({"example", "replace", "tbd", "todo", "undeclared"})


class MaintenanceReviewDisposition(StrEnum):
    """The only explicit human dispositions for a maintenance proposal."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MaintenanceOutcomeState(StrEnum):
    """A disposition remains non-successful until source truth is observed."""

    ACCEPTED_AWAITING_SOURCE_OBSERVATION = "accepted-awaiting-source-observation"
    VERIFIED_SOURCE_REVISION = "verified-source-revision"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True)
class MaintenanceReviewDecision:
    """A human decision bound to exactly one source-versioned proposal."""

    decision_id: str
    proposal_id: str
    tenant_id: str
    source_id: str
    source_system: str
    source_record_id: str
    source_revision: str
    source_version: int
    disposition: MaintenanceReviewDisposition
    reviewed_by: str
    reviewed_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        _prefixed_identifier(self.decision_id, "maintenance-decision:", "decision_id")
        _prefixed_identifier(self.proposal_id, "maintenance:", "proposal_id")
        _required(self.tenant_id, "decision tenant_id", maximum=200)
        _required(self.source_id, "decision source_id", maximum=500)
        _required(self.source_system, "decision source_system", maximum=100)
        _required(self.source_record_id, "decision source_record_id", maximum=500)
        _required(self.source_revision, "decision source_revision", maximum=200)
        if type(self.source_version) is not int or self.source_version < 1:
            raise CompanyBrainMaintenanceError(
                "decision source_version must be positive"
            )
        if not isinstance(self.disposition, MaintenanceReviewDisposition):
            raise CompanyBrainMaintenanceError("decision disposition is invalid")
        _named_identity(self.reviewed_by, "decision reviewed_by")
        _utc(self.reviewed_at, "decision reviewed_at")
        _required(self.rationale, "decision rationale", maximum=1_000)

    def to_payload(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "source_revision": self.source_revision,
            "source_version": self.source_version,
            "disposition": self.disposition.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": _utc(self.reviewed_at, "decision reviewed_at").isoformat(),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class SourceRevisionObservation:
    """An independently recorded source-of-truth revision after a decision."""

    observation_id: str
    tenant_id: str
    source_id: str
    source_system: str
    source_record_id: str
    observed_revision: str
    observed_at: datetime
    observed_by: str
    evidence_locator: str
    evidence_digest: str

    def __post_init__(self) -> None:
        _prefixed_identifier(
            self.observation_id, "maintenance-observation:", "observation_id"
        )
        _required(self.tenant_id, "observation tenant_id", maximum=200)
        _required(self.source_id, "observation source_id", maximum=500)
        _required(self.source_system, "observation source_system", maximum=100)
        _required(self.source_record_id, "observation source_record_id", maximum=500)
        _required(self.observed_revision, "observation observed_revision", maximum=200)
        _utc(self.observed_at, "observation observed_at")
        _named_identity(self.observed_by, "observation observed_by")
        _required(self.evidence_locator, "observation evidence_locator", maximum=500)
        _digest(self.evidence_digest, "observation evidence_digest")

    def to_payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "observed_revision": self.observed_revision,
            "observed_at": _utc(
                self.observed_at, "observation observed_at"
            ).isoformat(),
            "observed_by": self.observed_by,
            "evidence_locator": self.evidence_locator,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class MaintenanceOutcome:
    """The review result, explicitly distinguished from verified source truth."""

    outcome_id: str
    proposal_id: str
    decision_id: str
    disposition: MaintenanceReviewDisposition
    state: MaintenanceOutcomeState
    observation_id: str | None
    independently_observed: bool
    requires_human_review: Literal[True] = True

    def __post_init__(self) -> None:
        _prefixed_identifier(self.outcome_id, "maintenance-outcome:", "outcome_id")
        _prefixed_identifier(self.proposal_id, "maintenance:", "proposal_id")
        _prefixed_identifier(self.decision_id, "maintenance-decision:", "decision_id")
        if not isinstance(self.disposition, MaintenanceReviewDisposition):
            raise CompanyBrainMaintenanceError("outcome disposition is invalid")
        if not isinstance(self.state, MaintenanceOutcomeState):
            raise CompanyBrainMaintenanceError("outcome state is invalid")
        if self.observation_id is not None:
            _prefixed_identifier(
                self.observation_id,
                "maintenance-observation:",
                "outcome observation_id",
            )
        if type(self.independently_observed) is not bool:
            raise CompanyBrainMaintenanceError(
                "outcome independently_observed is invalid"
            )
        expected = {
            MaintenanceReviewDisposition.ACCEPTED: (
                MaintenanceOutcomeState.ACCEPTED_AWAITING_SOURCE_OBSERVATION,
                False,
                None,
            ),
            MaintenanceReviewDisposition.REJECTED: (
                MaintenanceOutcomeState.REJECTED,
                False,
                None,
            ),
            MaintenanceReviewDisposition.EXPIRED: (
                MaintenanceOutcomeState.EXPIRED,
                False,
                None,
            ),
        }
        if (
            self.disposition is MaintenanceReviewDisposition.ACCEPTED
            and self.independently_observed
        ):
            if (
                self.state is not MaintenanceOutcomeState.VERIFIED_SOURCE_REVISION
                or self.observation_id is None
            ):
                raise CompanyBrainMaintenanceError(
                    "an independently observed accepted outcome requires verified-source-revision"
                )
        elif (self.state, self.independently_observed, self.observation_id) != expected[
            self.disposition
        ]:
            raise CompanyBrainMaintenanceError(
                "outcome state does not match its explicit review disposition"
            )
        if self.requires_human_review is not True:
            raise CompanyBrainMaintenanceError(
                "maintenance outcomes always require human review"
            )

    @property
    def source_change_verified(self) -> bool:
        """Only a later independent source observation makes this true."""

        return self.state is MaintenanceOutcomeState.VERIFIED_SOURCE_REVISION

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome_id": self.outcome_id,
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "disposition": self.disposition.value,
            "state": self.state.value,
            "observation_id": self.observation_id,
            "independently_observed": self.independently_observed,
            "source_change_verified": self.source_change_verified,
            "requires_human_review": self.requires_human_review,
        }


_PROPOSAL_FIELDS = frozenset(
    {
        "proposal_id",
        "tenant_id",
        "source_id",
        "source_kind",
        "source_label",
        "source_system",
        "source_record_id",
        "source_revision",
        "source_version",
        "finding_kind",
        "action",
        "severity",
        "reason",
        "policy_version",
        "requires_human_review",
    }
)
_DECISION_FIELDS = frozenset(
    {
        "decision_id",
        "proposal_id",
        "tenant_id",
        "source_id",
        "source_system",
        "source_record_id",
        "source_revision",
        "source_version",
        "disposition",
        "reviewed_by",
        "reviewed_at",
        "rationale",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "observation_id",
        "tenant_id",
        "source_id",
        "source_system",
        "source_record_id",
        "observed_revision",
        "observed_at",
        "observed_by",
        "evidence_locator",
        "evidence_digest",
    }
)


def parse_maintenance_proposal(payload: object) -> MemoryMaintenanceProposal:
    """Parse a bounded review-only proposal artifact before correlating it."""

    raw = _mapping(payload, "maintenance proposal")
    _exact_keys(raw, _PROPOSAL_FIELDS, "maintenance proposal")
    try:
        source_kind = EntityKind(
            _text(raw.get("source_kind"), "proposal source_kind", maximum=80)
        )
        finding_kind = MemoryMaintenanceFindingKind(
            _text(raw.get("finding_kind"), "proposal finding_kind", maximum=80)
        )
        action = MemoryMaintenanceAction(
            _text(raw.get("action"), "proposal action", maximum=120)
        )
    except ValueError as error:
        raise CompanyBrainMaintenanceError(
            "maintenance proposal enum value is invalid"
        ) from error
    return MemoryMaintenanceProposal(
        proposal_id=_text(raw.get("proposal_id"), "proposal proposal_id", maximum=240),
        tenant_id=_text(raw.get("tenant_id"), "proposal tenant_id", maximum=200),
        source_id=_text(raw.get("source_id"), "proposal source_id", maximum=500),
        source_kind=source_kind,
        source_label=_text(
            raw.get("source_label"), "proposal source_label", maximum=300
        ),
        source_system=_text(
            raw.get("source_system"), "proposal source_system", maximum=100
        ),
        source_record_id=_text(
            raw.get("source_record_id"), "proposal source_record_id", maximum=500
        ),
        source_revision=_text(
            raw.get("source_revision"), "proposal source_revision", maximum=200
        ),
        source_version=_positive_int(
            raw.get("source_version"), "proposal source_version"
        ),
        finding_kind=finding_kind,
        action=action,
        severity=_positive_int(raw.get("severity"), "proposal severity"),
        reason=_text(raw.get("reason"), "proposal reason", maximum=1_000),
        policy_version=_text(
            raw.get("policy_version"), "proposal policy_version", maximum=160
        ),
        requires_human_review=_true(
            raw.get("requires_human_review"), "proposal requires_human_review"
        ),
    )


def parse_maintenance_review_decision(payload: object) -> MaintenanceReviewDecision:
    """Parse an explicit human disposition without interpreting a source update."""

    raw = _mapping(payload, "maintenance review decision")
    _exact_keys(raw, _DECISION_FIELDS, "maintenance review decision")
    try:
        disposition = MaintenanceReviewDisposition(
            _text(raw.get("disposition"), "decision disposition", maximum=40)
        )
    except ValueError as error:
        raise CompanyBrainMaintenanceError("decision disposition is invalid") from error
    return MaintenanceReviewDecision(
        decision_id=_text(raw.get("decision_id"), "decision decision_id", maximum=240),
        proposal_id=_text(raw.get("proposal_id"), "decision proposal_id", maximum=240),
        tenant_id=_text(raw.get("tenant_id"), "decision tenant_id", maximum=200),
        source_id=_text(raw.get("source_id"), "decision source_id", maximum=500),
        source_system=_text(
            raw.get("source_system"), "decision source_system", maximum=100
        ),
        source_record_id=_text(
            raw.get("source_record_id"), "decision source_record_id", maximum=500
        ),
        source_revision=_text(
            raw.get("source_revision"), "decision source_revision", maximum=200
        ),
        source_version=_positive_int(
            raw.get("source_version"), "decision source_version"
        ),
        disposition=disposition,
        reviewed_by=_text(raw.get("reviewed_by"), "decision reviewed_by", maximum=200),
        reviewed_at=_timestamp(raw.get("reviewed_at"), "decision reviewed_at"),
        rationale=_text(raw.get("rationale"), "decision rationale", maximum=1_000),
    )


def parse_source_revision_observation(payload: object) -> SourceRevisionObservation:
    """Parse an independent source observation without trusting a proposal's result."""

    raw = _mapping(payload, "source revision observation")
    _exact_keys(raw, _OBSERVATION_FIELDS, "source revision observation")
    return SourceRevisionObservation(
        observation_id=_text(
            raw.get("observation_id"), "observation observation_id", maximum=240
        ),
        tenant_id=_text(raw.get("tenant_id"), "observation tenant_id", maximum=200),
        source_id=_text(raw.get("source_id"), "observation source_id", maximum=500),
        source_system=_text(
            raw.get("source_system"), "observation source_system", maximum=100
        ),
        source_record_id=_text(
            raw.get("source_record_id"), "observation source_record_id", maximum=500
        ),
        observed_revision=_text(
            raw.get("observed_revision"), "observation observed_revision", maximum=200
        ),
        observed_at=_timestamp(raw.get("observed_at"), "observation observed_at"),
        observed_by=_text(
            raw.get("observed_by"), "observation observed_by", maximum=200
        ),
        evidence_locator=_text(
            raw.get("evidence_locator"), "observation evidence_locator", maximum=500
        ),
        evidence_digest=_digest(
            raw.get("evidence_digest"), "observation evidence_digest"
        ),
    )


def evaluate_maintenance_outcome(
    proposal: MemoryMaintenanceProposal,
    decision: MaintenanceReviewDecision,
    observation: SourceRevisionObservation | None = None,
) -> MaintenanceOutcome:
    """Correlate a decision with source truth, without writing either system.

    An accepted decision alone remains an awaiting-observation outcome. It
    becomes a verified source revision only when a separate identity observes a
    changed revision for the exact proposal source after the review timestamp.
    """

    _assert_decision_matches_proposal(proposal, decision)
    if decision.disposition is MaintenanceReviewDisposition.ACCEPTED:
        if observation is None:
            return _outcome_for(
                proposal,
                decision,
                state=MaintenanceOutcomeState.ACCEPTED_AWAITING_SOURCE_OBSERVATION,
                observation=None,
            )
        _assert_observation_matches_proposal(proposal, decision, observation)
        return _outcome_for(
            proposal,
            decision,
            state=MaintenanceOutcomeState.VERIFIED_SOURCE_REVISION,
            observation=observation,
        )
    if observation is not None:
        raise CompanyBrainMaintenanceError(
            "only an accepted decision may be correlated with a source revision observation"
        )
    if decision.disposition is MaintenanceReviewDisposition.REJECTED:
        return _outcome_for(
            proposal,
            decision,
            state=MaintenanceOutcomeState.REJECTED,
            observation=None,
        )
    if decision.disposition is MaintenanceReviewDisposition.EXPIRED:
        return _outcome_for(
            proposal,
            decision,
            state=MaintenanceOutcomeState.EXPIRED,
            observation=None,
        )
    assert_never(decision.disposition)


def _outcome_for(
    proposal: MemoryMaintenanceProposal,
    decision: MaintenanceReviewDecision,
    *,
    state: MaintenanceOutcomeState,
    observation: SourceRevisionObservation | None,
) -> MaintenanceOutcome:
    semantic_payload = {
        "proposal_id": proposal.proposal_id,
        "decision_id": decision.decision_id,
        "disposition": decision.disposition.value,
        "state": state.value,
        "observation_id": observation.observation_id
        if observation is not None
        else None,
    }
    digest = hashlib.sha256(
        json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return MaintenanceOutcome(
        outcome_id=f"maintenance-outcome:{digest}",
        proposal_id=proposal.proposal_id,
        decision_id=decision.decision_id,
        disposition=decision.disposition,
        state=state,
        observation_id=observation.observation_id if observation is not None else None,
        independently_observed=observation is not None,
    )


def _assert_decision_matches_proposal(
    proposal: MemoryMaintenanceProposal,
    decision: MaintenanceReviewDecision,
) -> None:
    for label, expected, actual in (
        ("proposal_id", proposal.proposal_id, decision.proposal_id),
        ("tenant_id", proposal.tenant_id, decision.tenant_id),
        ("source_id", proposal.source_id, decision.source_id),
        ("source_system", proposal.source_system, decision.source_system),
        ("source_record_id", proposal.source_record_id, decision.source_record_id),
        ("source_revision", proposal.source_revision, decision.source_revision),
        ("source_version", proposal.source_version, decision.source_version),
    ):
        if actual != expected:
            raise CompanyBrainMaintenanceError(
                f"maintenance decision {label} does not match the reviewed proposal"
            )


def _assert_observation_matches_proposal(
    proposal: MemoryMaintenanceProposal,
    decision: MaintenanceReviewDecision,
    observation: SourceRevisionObservation,
) -> None:
    for label, expected, actual in (
        ("tenant_id", proposal.tenant_id, observation.tenant_id),
        ("source_id", proposal.source_id, observation.source_id),
        ("source_system", proposal.source_system, observation.source_system),
        ("source_record_id", proposal.source_record_id, observation.source_record_id),
    ):
        if actual != expected:
            raise CompanyBrainMaintenanceError(
                f"source observation {label} does not match the reviewed proposal"
            )
    if observation.observed_revision == proposal.source_revision:
        raise CompanyBrainMaintenanceError(
            "source observation must record a revision different from the proposal revision"
        )
    if observation.observed_by == decision.reviewed_by:
        raise CompanyBrainMaintenanceError(
            "source observation identity must differ from the reviewing identity"
        )
    if _utc(observation.observed_at, "observation observed_at") < _utc(
        decision.reviewed_at, "decision reviewed_at"
    ):
        raise CompanyBrainMaintenanceError(
            "source observation must occur at or after the review decision"
        )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CompanyBrainMaintenanceError(f"{label} must be a JSON object")
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    if set(value) != set(expected):
        raise CompanyBrainMaintenanceError(f"{label} has unexpected or missing fields")


def _required(value: object, label: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\n" in value
    ):
        raise CompanyBrainMaintenanceError(f"{label} is invalid")
    return value


def _text(value: object, label: str, *, maximum: int) -> str:
    """Parse a bounded JSON string through the common maintenance guard."""

    return _required(value, label, maximum=maximum)


def _named_identity(value: object, label: str) -> str:
    identity = _required(value, label, maximum=240)
    if not _IDENTIFIER.fullmatch(identity):
        raise CompanyBrainMaintenanceError(f"{label} is invalid")
    if any(part in identity.casefold() for part in _PLACEHOLDER_PARTS):
        raise CompanyBrainMaintenanceError(
            f"{label} must name a real accountable identity"
        )
    return identity


def _prefixed_identifier(value: object, prefix: str, label: str) -> str:
    identifier = _required(value, label, maximum=240)
    if not identifier.startswith(prefix) or not _IDENTIFIER.fullmatch(identifier):
        raise CompanyBrainMaintenanceError(f"{label} is invalid")
    return identifier


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise CompanyBrainMaintenanceError(f"{label} must be a positive integer")
    return value


def _true(value: object, label: str) -> Literal[True]:
    if value is not True:
        raise CompanyBrainMaintenanceError(f"{label} must be true")
    return True


def _digest(value: object, label: str) -> str:
    digest = _required(value, label, maximum=80)
    if not _SHA256.fullmatch(digest):
        raise CompanyBrainMaintenanceError(f"{label} must be a lowercase sha256 digest")
    return digest


def _timestamp(value: object, label: str) -> datetime:
    raw = _required(value, label, maximum=80)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompanyBrainMaintenanceError(
            f"{label} must be an ISO-8601 timestamp"
        ) from error
    return _utc(parsed, label)


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CompanyBrainMaintenanceError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)
