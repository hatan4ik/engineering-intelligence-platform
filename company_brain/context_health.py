"""Deterministic health reporting for an authorized Company Brain context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from .context_packet import ContextPacket, ContextPacketSection
from .decision_context import DecisionContext
from .product_contracts import ProductContractError


class ContextHealthError(ProductContractError):
    """Raised when a context-health report cannot preserve a trusted boundary."""


class ContextHealthState(StrEnum):
    READY = "ready"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNQUALIFIED = "unqualified"


class ContextHealthIssueKind(StrEnum):
    CONTEXT_UNQUALIFIED = "context_unqualified"
    PACKET_OMISSION = "packet_omission"
    LIMITATION = "limitation"
    CONFLICT = "conflict"


def describe_context_health_state(state: ContextHealthState) -> str:
    """Describe each health state exhaustively for a human-facing surface."""

    match state:
        case ContextHealthState.READY:
            return "The authorized context is complete and qualified for an advisory decision."
        case ContextHealthState.LIMITED:
            return "The context is qualified but incomplete or limited and needs human review."
        case ContextHealthState.CONFLICTED:
            return "The context contains conflicting facts and cannot support a decision without review."
        case ContextHealthState.UNQUALIFIED:
            return "The context is insufficient for a decision and must not advance a proposal."
        case _ as unreachable:
            assert_never(unreachable)


@dataclass(frozen=True)
class ContextHealthIssue:
    """One non-disclosing reason a context cannot be relied on without review."""

    kind: ContextHealthIssueKind
    count: int
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ContextHealthIssueKind):
            raise ContextHealthError("context health issue kind is invalid")
        if type(self.count) is not int or self.count < 1:
            raise ContextHealthError("context health issue count must be a positive integer")
        if not isinstance(self.message, str) or not self.message or len(self.message) > 500 or "\n" in self.message:
            raise ContextHealthError("context health issue message is invalid")


@dataclass(frozen=True)
class ContextHealthReport:
    """A deterministic report explaining readiness without exposing source content."""

    context_version: str
    context_packet_digest: str
    state: ContextHealthState
    issues: tuple[ContextHealthIssue, ...]
    qualified_relationship_count: int
    retained_evidence_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.context_version, str) or not self.context_version or len(self.context_version) > 240:
            raise ContextHealthError("context health context_version is invalid")
        if not isinstance(self.context_packet_digest, str) or not self.context_packet_digest.startswith("sha256:"):
            raise ContextHealthError("context health context_packet_digest is invalid")
        if not isinstance(self.state, ContextHealthState):
            raise ContextHealthError("context health state is invalid")
        if self.issues != tuple(sorted(self.issues, key=lambda item: item.kind.value)):
            raise ContextHealthError("context health issues must be sorted")
        if len({item.kind for item in self.issues}) != len(self.issues):
            raise ContextHealthError("context health issues must be unique by kind")
        for value, label in (
            (self.qualified_relationship_count, "qualified_relationship_count"),
            (self.retained_evidence_count, "retained_evidence_count"),
        ):
            if type(value) is not int or value < 0:
                raise ContextHealthError(f"context health {label} is invalid")

    @property
    def proposal_eligible(self) -> bool:
        """Only a complete, qualified, non-conflicted context may support a proposal."""

        return self.state is ContextHealthState.READY


def context_health_report(
    context: DecisionContext,
    packet: ContextPacket,
) -> ContextHealthReport:
    """Explain all known limitations of a packet without a second data read."""

    if packet.context_version != context.context_version:
        raise ContextHealthError("context health packet context_version does not match the Decision Context")
    if packet.qualified is not context.qualified:
        raise ContextHealthError("context health packet qualification does not match the Decision Context")
    issues: list[ContextHealthIssue] = []
    if not context.qualified:
        issues.append(
            ContextHealthIssue(
                ContextHealthIssueKind.CONTEXT_UNQUALIFIED,
                1,
                "The qualified world-model policy did not admit this context to a decision path.",
            )
        )
    if packet.omissions:
        sections = tuple(sorted({item.section for item in packet.omissions}, key=lambda item: item.value))
        issues.append(
            ContextHealthIssue(
                ContextHealthIssueKind.PACKET_OMISSION,
                sum(item.count for item in packet.omissions),
                _omission_message(sections),
            )
        )
    if context.limitations:
        issues.append(
            ContextHealthIssue(
                ContextHealthIssueKind.LIMITATION,
                len(context.limitations),
                "The qualified context includes explicit evidence, freshness, or scope limitations.",
            )
        )
    if context.conflict_ids:
        issues.append(
            ContextHealthIssue(
                ContextHealthIssueKind.CONFLICT,
                len(context.conflict_ids),
                "Conflicting Company Brain facts require human review before use.",
            )
        )
    state = _state(context, packet)
    return ContextHealthReport(
        context_version=context.context_version,
        context_packet_digest=packet.digest,
        state=state,
        issues=tuple(sorted(issues, key=lambda item: item.kind.value)),
        qualified_relationship_count=len(packet.relationships),
        retained_evidence_count=len(packet.evidence),
    )


def _state(context: DecisionContext, packet: ContextPacket) -> ContextHealthState:
    if not context.qualified:
        return ContextHealthState.UNQUALIFIED
    if context.conflict_ids:
        return ContextHealthState.CONFLICTED
    if packet.omissions or context.limitations:
        return ContextHealthState.LIMITED
    return ContextHealthState.READY


def _omission_message(sections: tuple[ContextPacketSection, ...]) -> str:
    names = ", ".join(item.value for item in sections)
    return f"The packet omitted bounded {names} material; it cannot be treated as complete."
