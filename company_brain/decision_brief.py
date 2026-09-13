"""A safe, product-neutral working brief for one Company Brain decision.

The brief is deliberately not an open-ended chat room or an authority object.
It combines human request metadata with a bounded, authorized Context Packet so
the question, owners, uncertainty, and evidence boundary remain visible at the
moment a human makes a decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import assert_never

from .context_packet import ContextPacket
from .model import RelationshipKind
from .product_contracts import ProductContractError


class DecisionBriefError(ProductContractError):
    """Raised when a decision brief would hide scope or uncertainty."""


class DecisionScopeKind(StrEnum):
    """The bounded product situations that can share Company Brain context."""

    PULL_REQUEST = "pull_request"
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    RELEASE = "release"
    ARCHITECTURE_DECISION = "architecture_decision"
    RUNBOOK = "runbook"


def describe_decision_scope(kind: DecisionScopeKind) -> str:
    """Render every supported cross-product decision scope exhaustively."""

    match kind:
        case DecisionScopeKind.PULL_REQUEST:
            return "pull request"
        case DecisionScopeKind.INCIDENT:
            return "incident"
        case DecisionScopeKind.DEPLOYMENT:
            return "deployment"
        case DecisionScopeKind.RELEASE:
            return "release"
        case DecisionScopeKind.ARCHITECTURE_DECISION:
            return "architecture decision"
        case DecisionScopeKind.RUNBOOK:
            return "runbook"
        case _ as unreachable:
            assert_never(unreachable)


@dataclass(frozen=True)
class DecisionScope:
    """A tenant-scoped, typed subject for a bounded decision experience."""

    tenant_id: str
    product: str
    kind: DecisionScopeKind
    scope_id: str
    label: str
    correlation_id: str

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "decision scope tenant_id")
        _product(self.product)
        if not isinstance(self.kind, DecisionScopeKind):
            raise DecisionBriefError("decision scope kind is invalid")
        _identifier(self.scope_id, "decision scope scope_id")
        _text(self.label, "decision scope label", maximum=300)
        _identifier(self.correlation_id, "decision scope correlation_id")


@dataclass(frozen=True)
class DecisionRequest:
    """Human-provided request metadata kept distinct from evidence-backed facts."""

    objective: str
    decision_question: str
    requested_by: str

    def __post_init__(self) -> None:
        _text(self.objective, "decision request objective", maximum=1_000)
        _text(self.decision_question, "decision request question", maximum=1_000)
        _identifier(self.requested_by, "decision request requested_by")


@dataclass(frozen=True)
class DecisionBrief:
    """One reviewable decision request plus its bounded evidence context."""

    scope: DecisionScope
    request: DecisionRequest
    context_packet: ContextPacket
    owner_ids: tuple[str, ...]
    brief_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.owner_ids != tuple(sorted(set(self.owner_ids))):
            raise DecisionBriefError("decision brief owner_ids must be sorted and unique")
        for owner_id in self.owner_ids:
            _identifier(owner_id, "decision brief owner_id")
        payload = self.payload()
        object.__setattr__(
            self,
            "brief_id",
            "decision-brief:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
        )

    @property
    def requires_human_review(self) -> bool:
        """No partial, conflicted, or unqualified brief may be treated as a decision."""

        return (
            not self.context_packet.qualified
            or not self.context_packet.complete
            or bool(self.context_packet.limitations)
            or bool(self.context_packet.conflict_ids)
        )

    def payload(self) -> dict[str, object]:
        """Return stable request and context metadata without source body content."""

        return {
            "scope": {
                "tenant_id": self.scope.tenant_id,
                "product": self.scope.product,
                "kind": self.scope.kind.value,
                "scope_id": self.scope.scope_id,
                "label": self.scope.label,
                "correlation_id": self.scope.correlation_id,
            },
            "request": {
                "objective": self.request.objective,
                "decision_question": self.request.decision_question,
                "requested_by": self.request.requested_by,
            },
            "context_version": self.context_packet.context_version,
            "context_packet_digest": self.context_packet.digest,
            "owner_ids": list(self.owner_ids),
        }


def decision_brief_from_packet(
    *,
    scope: DecisionScope,
    request: DecisionRequest,
    context_packet: ContextPacket,
) -> DecisionBrief:
    """Build a brief using only qualified ownership relationships in the packet."""

    owner_ids = tuple(
        sorted(
            {
                str(relationship.source_id)
                for relationship in context_packet.relationships
                if relationship.relationship is RelationshipKind.OWNS
            }
        )
    )
    return DecisionBrief(
        scope=scope,
        request=request,
        context_packet=context_packet,
        owner_ids=owner_ids,
    )


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}", value):
        raise DecisionBriefError(f"{label} is invalid")
    return value


def _product(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value):
        raise DecisionBriefError("decision scope product is invalid")
    return value


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise DecisionBriefError(f"{label} is invalid")
    return value
