"""Governed human corrections for Company Brain claims.

A correction is a reviewable request to revalidate source-backed knowledge. It
never overwrites a Company Brain fact or source document directly. The request
must be bound to a current, complete evidence-read receipt; an accepted review
can trigger source reconciliation in a separately authorized workflow.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Protocol

from control_plane.runtime import require_reference_storage

from .decision_brief import DecisionScope, DecisionScopeKind
from .evidence_receipts import EvidenceReadReceiptAuthority, EvidenceReadReceiptError, EvidenceReadReceiptId
from .model import BrainPrincipal
from .product_contracts import ProductContractError
from .sqlite import SqliteReferenceDatabase


class CorrectionError(ProductContractError):
    """Raised when a correction would bypass evidence, scope, or review controls."""


class CorrectionKind(StrEnum):
    REPLACE_CLAIM = "replace_claim"
    RETRACT_CLAIM = "retract_claim"
    REQUEST_REVALIDATION = "request_revalidation"


class CorrectionReviewDisposition(StrEnum):
    ACCEPT_FOR_REVALIDATION = "accept_for_revalidation"
    REJECT = "reject"


@dataclass(frozen=True)
class CorrectionProposal:
    """One immutable request to correct or revalidate a bounded claim."""

    correction_id: str
    request_id: str
    scope: DecisionScope
    evidence_read_receipt_id: EvidenceReadReceiptId | str
    context_version: str
    context_packet_digest: str
    target_key: str
    kind: CorrectionKind
    original_claim: str
    replacement_claim: str | None
    rationale: str
    requested_by: str
    requested_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.correction_id, "correction_id")
        _identifier(self.request_id, "correction request_id")
        _identifier(str(self.evidence_read_receipt_id), "correction evidence_read_receipt_id")
        _text(self.context_version, "correction context_version", maximum=240)
        _digest(self.context_packet_digest, "correction context_packet_digest")
        _identifier(self.target_key, "correction target_key")
        if not isinstance(self.kind, CorrectionKind):
            raise CorrectionError("correction kind is invalid")
        _text(self.original_claim, "correction original_claim", maximum=1_000)
        if self.kind is CorrectionKind.REPLACE_CLAIM:
            _text(self.replacement_claim or "", "correction replacement_claim", maximum=1_000)
        elif self.replacement_claim is not None:
            raise CorrectionError("only a replacement correction may contain replacement_claim")
        _text(self.rationale, "correction rationale", maximum=1_000)
        _identifier(self.requested_by, "correction requested_by")
        _utc(self.requested_at, "correction requested_at")

    def payload(self) -> dict[str, object]:
        """Return the stable, source-body-free persistence representation."""

        return {
            "correction_id": self.correction_id,
            "request_id": self.request_id,
            "scope": _scope_payload(self.scope),
            "evidence_read_receipt_id": str(self.evidence_read_receipt_id),
            "context_version": self.context_version,
            "context_packet_digest": self.context_packet_digest,
            "target_key": self.target_key,
            "kind": self.kind.value,
            "original_claim": self.original_claim,
            "replacement_claim": self.replacement_claim,
            "rationale": self.rationale,
            "requested_by": self.requested_by,
            "requested_at": _utc(self.requested_at, "correction requested_at").isoformat(),
        }


@dataclass(frozen=True)
class CorrectionReview:
    """One human review of a correction; it cannot mutate the target claim."""

    correction_id: str
    reviewer: str
    disposition: CorrectionReviewDisposition
    rationale: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.correction_id, "correction review correction_id")
        _identifier(self.reviewer, "correction review reviewer")
        if not isinstance(self.disposition, CorrectionReviewDisposition):
            raise CorrectionError("correction review disposition is invalid")
        _text(self.rationale, "correction review rationale", maximum=1_000)
        _utc(self.reviewed_at, "correction review reviewed_at")

    def payload(self) -> dict[str, object]:
        return {
            "correction_id": self.correction_id,
            "reviewer": self.reviewer,
            "disposition": self.disposition.value,
            "rationale": self.rationale,
            "reviewed_at": _utc(self.reviewed_at, "correction review reviewed_at").isoformat(),
        }


class CorrectionStore(Protocol):
    """Append-only persistence for correction requests and reviews."""

    def record_proposal(self, proposal: CorrectionProposal) -> bool: ...

    def proposal(self, correction_id: str) -> CorrectionProposal | None: ...

    def record_review(self, review: CorrectionReview) -> bool: ...

    def reviews(self, correction_id: str) -> tuple[CorrectionReview, ...]: ...


class CorrectionService:
    """Create correction proposals only after a receipt proves the evidence read."""

    def __init__(self, *, receipt_authority: EvidenceReadReceiptAuthority, store: CorrectionStore) -> None:
        self._receipt_authority = receipt_authority
        self._store = store

    def submit(
        self,
        *,
        request_id: str,
        scope: DecisionScope,
        receipt_id: EvidenceReadReceiptId | str,
        principal: BrainPrincipal,
        context_version: str,
        context_packet_digest: str,
        target_key: str,
        kind: CorrectionKind,
        original_claim: str,
        replacement_claim: str | None,
        rationale: str,
        requested_by: str,
        now: datetime | None = None,
    ) -> CorrectionProposal:
        """Record a proposal after validating its exact evidence snapshot binding."""

        if requested_by not in principal.users:
            raise CorrectionError("correction requested_by must be an authenticated principal user")
        if not isinstance(kind, CorrectionKind):
            raise CorrectionError("correction kind is invalid")
        try:
            receipt = self._receipt_authority.require_for_proposal(
                receipt_id=receipt_id,
                tenant_id=scope.tenant_id,
                product=scope.product,
                scope_id=scope.scope_id,
                correlation_id=scope.correlation_id,
                principal=principal,
                context_version=context_version,
                packet_digest=context_packet_digest,
                now=now,
            )
        except EvidenceReadReceiptError as error:
            raise CorrectionError(f"correction evidence receipt rejected: {error}") from error
        requested_at = _utc(now or datetime.now(timezone.utc), "correction requested_at")
        proposal = CorrectionProposal(
            correction_id=_correction_id(
                request_id=request_id,
                scope=scope,
                receipt_id=receipt.receipt_id,
                target_key=target_key,
                kind=kind,
                original_claim=original_claim,
                replacement_claim=replacement_claim,
                rationale=rationale,
                requested_by=requested_by,
            ),
            request_id=request_id,
            scope=scope,
            evidence_read_receipt_id=receipt.receipt_id,
            context_version=context_version,
            context_packet_digest=context_packet_digest,
            target_key=target_key,
            kind=kind,
            original_claim=original_claim,
            replacement_claim=replacement_claim,
            rationale=rationale,
            requested_by=requested_by,
            requested_at=requested_at,
        )
        self._store.record_proposal(proposal)
        return proposal

    def review(
        self,
        *,
        correction_id: str,
        reviewer: str,
        reviewer_principal: BrainPrincipal,
        disposition: CorrectionReviewDisposition,
        rationale: str,
        reviewed_at: datetime | None = None,
    ) -> CorrectionReview:
        """Append a human disposition without changing Company Brain source facts."""

        if reviewer not in reviewer_principal.users:
            raise CorrectionError("correction reviewer must be an authenticated principal user")
        if not isinstance(disposition, CorrectionReviewDisposition):
            raise CorrectionError("correction review disposition is invalid")
        if self._store.proposal(correction_id) is None:
            raise CorrectionError("a correction review requires a retained proposal")
        review = CorrectionReview(
            correction_id=correction_id,
            reviewer=reviewer,
            disposition=disposition,
            rationale=rationale,
            reviewed_at=_utc(reviewed_at or datetime.now(timezone.utc), "correction review reviewed_at"),
        )
        self._store.record_review(review)
        return review


class SqliteCorrectionStore(SqliteReferenceDatabase):
    """Local/reference append-only store; accepted reviews still do not mutate sources."""

    def __init__(self, path: str | Path = "company-brain-corrections.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_brain_correction_proposals (
                    correction_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    product TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_company_brain_correction_scope
                    ON company_brain_correction_proposals(tenant_id, product, scope_id, correction_id);
                CREATE TABLE IF NOT EXISTS company_brain_correction_reviews (
                    review_key TEXT PRIMARY KEY,
                    correction_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(correction_id) REFERENCES company_brain_correction_proposals(correction_id)
                );
                CREATE INDEX IF NOT EXISTS idx_company_brain_correction_reviews
                    ON company_brain_correction_reviews(correction_id, review_key);
                """
            )

    def record_proposal(self, proposal: CorrectionProposal) -> bool:
        """Record an immutable proposal or prove an exact idempotent replay."""

        payload = _canonical(proposal.payload())
        with self._connect() as database, self._immediate(database):
            row = database.execute(
                "SELECT payload FROM company_brain_correction_proposals WHERE correction_id=?",
                (proposal.correction_id,),
            ).fetchone()
            if row is not None:
                if str(row["payload"]) != payload:
                    raise CorrectionError("correction_id conflicts with retained history")
                return False
            database.execute(
                """INSERT INTO company_brain_correction_proposals(
                       correction_id, tenant_id, product, scope_id, payload
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    proposal.correction_id,
                    proposal.scope.tenant_id,
                    proposal.scope.product,
                    proposal.scope.scope_id,
                    payload,
                ),
            )
        return True

    def proposal(self, correction_id: str) -> CorrectionProposal | None:
        """Load one immutable proposal with strict payload validation."""

        _identifier(correction_id, "correction_id")
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM company_brain_correction_proposals WHERE correction_id=?", (correction_id,)
            ).fetchone()
        return _proposal_from_payload(_payload_from_json(str(row["payload"]))) if row is not None else None

    def record_review(self, review: CorrectionReview) -> bool:
        """Append a review only when its target proposal exists."""

        if self.proposal(review.correction_id) is None:
            raise CorrectionError("a correction review requires a retained proposal")
        payload = _canonical(review.payload())
        review_key = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._connect() as database, self._immediate(database):
            cursor = database.execute(
                """INSERT OR IGNORE INTO company_brain_correction_reviews(review_key, correction_id, payload)
                   VALUES (?, ?, ?)""",
                (review_key, review.correction_id, payload),
            )
        return cursor.rowcount == 1

    def reviews(self, correction_id: str) -> tuple[CorrectionReview, ...]:
        """Return all retained human dispositions; no source update is implied."""

        _identifier(correction_id, "correction_id")
        with self._connect() as database:
            rows = database.execute(
                """SELECT payload FROM company_brain_correction_reviews
                   WHERE correction_id=? ORDER BY review_key""",
                (correction_id,),
            ).fetchall()
        return tuple(_review_from_payload(_payload_from_json(str(row["payload"]))) for row in rows)


def _correction_id(
    *,
    request_id: str,
    scope: DecisionScope,
    receipt_id: EvidenceReadReceiptId | str,
    target_key: str,
    kind: CorrectionKind,
    original_claim: str,
    replacement_claim: str | None,
    rationale: str,
    requested_by: str,
) -> str:
    if not isinstance(kind, CorrectionKind):
        raise CorrectionError("correction kind is invalid")
    payload = {
        "request_id": request_id,
        "scope": _scope_payload(scope),
        "receipt_id": str(receipt_id),
        "target_key": target_key,
        "kind": kind.value,
        "original_claim": original_claim,
        "replacement_claim": replacement_claim,
        "rationale": rationale,
        "requested_by": requested_by,
    }
    return "correction:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _scope_payload(scope: DecisionScope) -> dict[str, str]:
    return {
        "tenant_id": scope.tenant_id,
        "product": scope.product,
        "kind": scope.kind.value,
        "scope_id": scope.scope_id,
        "label": scope.label,
        "correlation_id": scope.correlation_id,
    }


def _scope_from_payload(payload: Mapping[str, object]) -> DecisionScope:
    return DecisionScope(
        tenant_id=_required_text(payload, "tenant_id", "stored correction scope"),
        product=_required_text(payload, "product", "stored correction scope"),
        kind=DecisionScopeKind(_required_text(payload, "kind", "stored correction scope")),
        scope_id=_required_text(payload, "scope_id", "stored correction scope"),
        label=_required_text(payload, "label", "stored correction scope"),
        correlation_id=_required_text(payload, "correlation_id", "stored correction scope"),
    )


def _proposal_from_payload(payload: Mapping[str, object]) -> CorrectionProposal:
    scope_payload = payload.get("scope")
    if not isinstance(scope_payload, Mapping):
        raise CorrectionError("stored correction proposal scope is invalid")
    replacement = payload.get("replacement_claim")
    if replacement is not None and not isinstance(replacement, str):
        raise CorrectionError("stored correction proposal replacement_claim is invalid")
    return CorrectionProposal(
        correction_id=_required_text(payload, "correction_id", "stored correction proposal"),
        request_id=_required_text(payload, "request_id", "stored correction proposal"),
        scope=_scope_from_payload(scope_payload),
        evidence_read_receipt_id=_required_text(payload, "evidence_read_receipt_id", "stored correction proposal"),
        context_version=_required_text(payload, "context_version", "stored correction proposal"),
        context_packet_digest=_required_text(payload, "context_packet_digest", "stored correction proposal"),
        target_key=_required_text(payload, "target_key", "stored correction proposal"),
        kind=CorrectionKind(_required_text(payload, "kind", "stored correction proposal")),
        original_claim=_required_text(payload, "original_claim", "stored correction proposal"),
        replacement_claim=replacement,
        rationale=_required_text(payload, "rationale", "stored correction proposal"),
        requested_by=_required_text(payload, "requested_by", "stored correction proposal"),
        requested_at=_timestamp_from_payload(payload, "requested_at", "stored correction proposal"),
    )


def _review_from_payload(payload: Mapping[str, object]) -> CorrectionReview:
    return CorrectionReview(
        correction_id=_required_text(payload, "correction_id", "stored correction review"),
        reviewer=_required_text(payload, "reviewer", "stored correction review"),
        disposition=CorrectionReviewDisposition(
            _required_text(payload, "disposition", "stored correction review")
        ),
        rationale=_required_text(payload, "rationale", "stored correction review"),
        reviewed_at=_timestamp_from_payload(payload, "reviewed_at", "stored correction review"),
    )


def _payload_from_json(serialized: str) -> dict[str, object]:
    try:
        value: object = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise CorrectionError("stored correction payload is not JSON") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CorrectionError("stored correction payload is invalid")
    return value


def _required_text(payload: Mapping[str, object], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise CorrectionError(f"{label}.{field} must be a string")
    return value


def _timestamp_from_payload(payload: Mapping[str, object], field: str, label: str) -> datetime:
    value = _required_text(payload, field, label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CorrectionError(f"{label}.{field} must be an ISO timestamp") from error
    return _utc(parsed, f"{label}.{field}")


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}", value):
        raise CorrectionError(f"{label} is invalid")
    return value


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise CorrectionError(f"{label} is invalid")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise CorrectionError(f"{label} is invalid")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CorrectionError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)
