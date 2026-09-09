"""Durable, signed read-before-write evidence receipts.

An evidence read receipt binds a later proposal to the exact authorized
Company Brain evidence snapshot it read. It is deliberately separate from an
ingestion projection receipt and from a remediation plan approval: neither of
those proves what evidence a product used to formulate a draft.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, NewType, Protocol

from control_plane.runtime import require_reference_storage

from .context_packet import ContextPacket, ContextPacketError, context_packet_from_decision_context
from .decision_context import DecisionContext
from .model import BrainPrincipal
from .product_contracts import EvidenceReference, ProductContractError
from .sqlite import SqliteReferenceDatabase


EvidenceReadReceiptId = NewType("EvidenceReadReceiptId", str)

DEFAULT_EVIDENCE_READ_RECEIPT_TTL = timedelta(minutes=10)
MAX_EVIDENCE_READ_RECEIPT_TTL = timedelta(minutes=15)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


class EvidenceReadReceiptError(ProductContractError):
    """Raised when a receipt is invalid, stale, forged, or used out of scope."""


def resolve_evidence_read_receipt_id(value: str) -> EvidenceReadReceiptId:
    """Validate a nominal receipt identifier at a product boundary."""

    return EvidenceReadReceiptId(_identifier(value, "evidence read receipt_id"))


@dataclass(frozen=True)
class EvidenceSnapshotReference:
    """One immutable evidence revision bound into a read receipt.

    The source locator is represented by a digest so the receipt can prove an
    exact read without duplicating an access-controlled path into a broader
    audit or workflow record.
    """

    evidence_id: str
    source_kind: str
    revision: str
    locator_digest: str

    def __post_init__(self) -> None:
        _identifier(self.evidence_id, "evidence snapshot evidence_id")
        _text(self.source_kind, "evidence snapshot source_kind", maximum=100)
        _text(self.revision, "evidence snapshot revision", maximum=200)
        _digest(self.locator_digest, "evidence snapshot locator_digest")

    @classmethod
    def from_reference(cls, reference: EvidenceReference) -> "EvidenceSnapshotReference":
        """Create a non-disclosing snapshot reference from authorized evidence."""

        return cls(
            evidence_id=str(reference.evidence_id),
            source_kind=reference.source_kind,
            revision=reference.revision,
            locator_digest="sha256:" + hashlib.sha256(reference.locator.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True)
class EvidenceReadReceipt:
    """A signed, tenant-scoped record of one authorized evidence read."""

    receipt_id: EvidenceReadReceiptId | str
    tenant_id: str
    product: str
    scope_id: str
    correlation_id: str
    principal_fingerprint: str
    context_version: str
    context_packet_digest: str
    context_qualified: bool
    packet_complete: bool
    evidence: tuple[EvidenceSnapshotReference, ...]
    issued_at: datetime
    expires_at: datetime
    signature: str

    def __post_init__(self) -> None:
        _identifier(str(self.receipt_id), "evidence read receipt_id")
        _identifier(self.tenant_id, "evidence read tenant_id")
        _product(self.product)
        _identifier(self.scope_id, "evidence read scope_id")
        _identifier(self.correlation_id, "evidence read correlation_id")
        _digest(self.principal_fingerprint, "evidence read principal_fingerprint")
        _text(self.context_version, "evidence read context_version", maximum=240)
        _digest(self.context_packet_digest, "evidence read context_packet_digest")
        if type(self.context_qualified) is not bool:
            raise EvidenceReadReceiptError("evidence read context_qualified is invalid")
        if type(self.packet_complete) is not bool:
            raise EvidenceReadReceiptError("evidence read packet_complete is invalid")
        if self.evidence != tuple(sorted(self.evidence, key=lambda item: item.evidence_id)):
            raise EvidenceReadReceiptError("evidence read evidence must be sorted")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise EvidenceReadReceiptError("evidence read evidence must be unique")
        if self.context_qualified and not self.evidence:
            raise EvidenceReadReceiptError("a qualified evidence receipt requires retained evidence")
        issued_at = _utc(self.issued_at, "evidence read issued_at")
        expires_at = _utc(self.expires_at, "evidence read expires_at")
        if expires_at <= issued_at:
            raise EvidenceReadReceiptError("evidence read receipt must expire after issuance")
        _digest(self.signature, "evidence read signature")

    def unsigned_payload(self) -> dict[str, object]:
        """Return the exact signed body, excluding only its detached signature."""

        return {
            "receipt_id": str(self.receipt_id),
            "tenant_id": self.tenant_id,
            "product": self.product,
            "scope_id": self.scope_id,
            "correlation_id": self.correlation_id,
            "principal_fingerprint": self.principal_fingerprint,
            "context_version": self.context_version,
            "context_packet_digest": self.context_packet_digest,
            "context_qualified": self.context_qualified,
            "packet_complete": self.packet_complete,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source_kind": item.source_kind,
                    "revision": item.revision,
                    "locator_digest": item.locator_digest,
                }
                for item in self.evidence
            ],
            "issued_at": _utc(self.issued_at, "evidence read issued_at").isoformat(),
            "expires_at": _utc(self.expires_at, "evidence read expires_at").isoformat(),
        }

    def payload(self) -> dict[str, object]:
        """Return the persistence representation, including its signature."""

        return {**self.unsigned_payload(), "signature": self.signature}

    def canonical_unsigned_json(self) -> str:
        """Encode the signed payload deterministically."""

        return _canonical(self.unsigned_payload())


class EvidenceReadReceiptStore(Protocol):
    """Durable receipt persistence needed before a proposal may rely on it."""

    def record(self, receipt: EvidenceReadReceipt) -> bool: ...

    def get(self, receipt_id: EvidenceReadReceiptId | str) -> EvidenceReadReceipt | None: ...


class EvidenceReadReceiptAuthority:
    """Issue and verify short-lived evidence snapshots for product proposals."""

    def __init__(
        self,
        *,
        secret: str,
        store: EvidenceReadReceiptStore,
        maximum_ttl: timedelta = MAX_EVIDENCE_READ_RECEIPT_TTL,
    ) -> None:
        if not isinstance(secret, str) or len(secret) < 32:
            raise EvidenceReadReceiptError("evidence receipt secret must contain at least 32 characters")
        if store is None:
            raise EvidenceReadReceiptError("evidence receipt store is required")
        if (
            not isinstance(maximum_ttl, timedelta)
            or maximum_ttl <= timedelta(0)
            or maximum_ttl > MAX_EVIDENCE_READ_RECEIPT_TTL
        ):
            raise EvidenceReadReceiptError("evidence receipt maximum_ttl is invalid")
        self._secret = secret.encode("utf-8")
        self._store = store
        self._maximum_ttl = maximum_ttl

    def issue(
        self,
        *,
        tenant_id: str,
        product: str,
        scope_id: str,
        correlation_id: str,
        principal: BrainPrincipal,
        context: DecisionContext,
        packet: ContextPacket,
        now: datetime | None = None,
        ttl: timedelta = DEFAULT_EVIDENCE_READ_RECEIPT_TTL,
    ) -> EvidenceReadReceipt:
        """Persist one signed receipt for an exact qualified-context read.

        The receipt can be issued for an incomplete or unqualified context so
        the audit trail remains truthful. ``require_for_proposal`` is the
        separate hard gate that refuses to use either for a proposal.
        """

        if not isinstance(principal, BrainPrincipal):
            raise EvidenceReadReceiptError("evidence receipt principal is invalid")
        if not isinstance(context, DecisionContext):
            raise EvidenceReadReceiptError("evidence receipt context is invalid")
        if not isinstance(packet, ContextPacket):
            raise EvidenceReadReceiptError("evidence receipt packet is invalid")
        _identifier(tenant_id, "evidence read tenant_id")
        _product(product)
        _identifier(scope_id, "evidence read scope_id")
        _identifier(correlation_id, "evidence read correlation_id")
        if packet.context_version != context.context_version:
            raise EvidenceReadReceiptError("evidence receipt packet context_version does not match the context")
        if packet.qualified is not context.qualified:
            raise EvidenceReadReceiptError("evidence receipt packet qualification does not match the context")
        try:
            expected_packet = context_packet_from_decision_context(context, budget=packet.budget)
        except ContextPacketError as error:
            raise EvidenceReadReceiptError("evidence receipt packet budget is invalid") from error
        if packet != expected_packet:
            raise EvidenceReadReceiptError(
                "evidence receipt packet must be the deterministic bounded projection of the source context"
            )
        issued_at = _utc(now or datetime.now(timezone.utc), "evidence read issued_at")
        if not isinstance(ttl, timedelta) or ttl <= timedelta(0) or ttl > self._maximum_ttl:
            raise EvidenceReadReceiptError("evidence receipt ttl is invalid")
        expires_at = issued_at + ttl
        evidence = tuple(
            sorted(
                (EvidenceSnapshotReference.from_reference(item) for item in packet.evidence),
                key=lambda item: item.evidence_id,
            )
        )
        base_payload = {
            "tenant_id": tenant_id,
            "product": product,
            "scope_id": scope_id,
            "correlation_id": correlation_id,
            "principal_fingerprint": principal_fingerprint(principal),
            "context_version": context.context_version,
            "context_packet_digest": packet.digest,
            "context_qualified": context.qualified,
            "packet_complete": packet.complete,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source_kind": item.source_kind,
                    "revision": item.revision,
                    "locator_digest": item.locator_digest,
                }
                for item in evidence
            ],
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        receipt_id = EvidenceReadReceiptId(
            "evidence-read:" + hashlib.sha256(_canonical(base_payload).encode("utf-8")).hexdigest()
        )
        unsigned = {"receipt_id": str(receipt_id), **base_payload}
        receipt = EvidenceReadReceipt(
            receipt_id=receipt_id,
            tenant_id=tenant_id,
            product=product,
            scope_id=scope_id,
            correlation_id=correlation_id,
            principal_fingerprint=principal_fingerprint(principal),
            context_version=context.context_version,
            context_packet_digest=packet.digest,
            context_qualified=context.qualified,
            packet_complete=packet.complete,
            evidence=evidence,
            issued_at=issued_at,
            expires_at=expires_at,
            signature=_signature(self._secret, unsigned),
        )
        self._store.record(receipt)
        return receipt

    def require_for_proposal(
        self,
        *,
        receipt_id: EvidenceReadReceiptId | str,
        tenant_id: str,
        product: str,
        scope_id: str,
        correlation_id: str,
        principal: BrainPrincipal,
        context_version: str,
        packet_digest: str,
        now: datetime | None = None,
    ) -> EvidenceReadReceipt:
        """Require a current, complete, qualified receipt before a proposal advances."""

        receipt = self._store.get(receipt_id)
        if receipt is None:
            raise EvidenceReadReceiptError("evidence read receipt was not found in durable storage")
        expected = {
            "tenant_id": tenant_id,
            "product": product,
            "scope_id": scope_id,
            "correlation_id": correlation_id,
            "principal_fingerprint": principal_fingerprint(principal),
            "context_version": context_version,
            "context_packet_digest": packet_digest,
        }
        actual = receipt.unsigned_payload()
        for field, value in expected.items():
            if actual[field] != value:
                raise EvidenceReadReceiptError(f"evidence read receipt is bound to a different {field}")
        if not hmac.compare_digest(receipt.signature, _signature(self._secret, actual)):
            raise EvidenceReadReceiptError("evidence read receipt signature is invalid")
        current = _utc(now or datetime.now(timezone.utc), "evidence read verification time")
        if current < _utc(receipt.issued_at, "evidence read issued_at") or current >= _utc(
            receipt.expires_at, "evidence read expires_at"
        ):
            raise EvidenceReadReceiptError("evidence read receipt is stale or not yet valid")
        if not receipt.context_qualified:
            raise EvidenceReadReceiptError("an unqualified evidence context cannot support a proposal")
        if not receipt.packet_complete:
            raise EvidenceReadReceiptError("a context packet with omissions cannot support a proposal")
        if not receipt.evidence:
            raise EvidenceReadReceiptError("a proposal requires at least one evidence snapshot")
        return receipt


class SqliteEvidenceReadReceiptStore(SqliteReferenceDatabase):
    """Tenant-scoped, append-only local receipt storage for reference paths."""

    def __init__(self, path: str | Path = "company-brain-evidence-receipts.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_brain_evidence_read_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    product TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_company_brain_evidence_read_receipts_scope
                    ON company_brain_evidence_read_receipts(tenant_id, product, scope_id, expires_at);
                """
            )

    def record(self, receipt: EvidenceReadReceipt) -> bool:
        """Append a receipt or prove that an exact replay was already retained."""

        payload = _canonical(receipt.payload())
        with self._connect() as database, self._immediate(database):
            row = database.execute(
                "SELECT payload FROM company_brain_evidence_read_receipts WHERE receipt_id=?",
                (str(receipt.receipt_id),),
            ).fetchone()
            if row is not None:
                if str(row["payload"]) != payload:
                    raise EvidenceReadReceiptError("evidence read receipt_id conflicts with retained history")
                return False
            database.execute(
                """INSERT INTO company_brain_evidence_read_receipts(
                       receipt_id, tenant_id, product, scope_id, expires_at, payload
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(receipt.receipt_id),
                    receipt.tenant_id,
                    receipt.product,
                    receipt.scope_id,
                    _utc(receipt.expires_at, "evidence read expires_at").isoformat(),
                    payload,
                ),
            )
        return True

    def get(self, receipt_id: EvidenceReadReceiptId | str) -> EvidenceReadReceipt | None:
        """Load one receipt, retaining strict shape checks at the persistence boundary."""

        identifier = resolve_evidence_read_receipt_id(str(receipt_id))
        with self._connect() as database:
            row = database.execute(
                "SELECT payload FROM company_brain_evidence_read_receipts WHERE receipt_id=?", (str(identifier),)
            ).fetchone()
        return _receipt_from_payload(_payload_from_json(str(row["payload"]))) if row is not None else None


def principal_fingerprint(principal: BrainPrincipal) -> str:
    """Hash a normalized principal rather than retaining raw group/user identifiers."""

    if not isinstance(principal, BrainPrincipal):
        raise EvidenceReadReceiptError("evidence receipt principal is invalid")
    payload = {"groups": list(principal.groups), "users": list(principal.users)}
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _receipt_from_payload(payload: Mapping[str, object]) -> EvidenceReadReceipt:
    evidence_values = payload.get("evidence")
    if not isinstance(evidence_values, list):
        raise EvidenceReadReceiptError("stored evidence read receipt evidence is invalid")
    evidence = tuple(
        sorted(
            (
                EvidenceSnapshotReference(
                    evidence_id=_required_text(item, "evidence_id", "stored evidence snapshot"),
                    source_kind=_required_text(item, "source_kind", "stored evidence snapshot"),
                    revision=_required_text(item, "revision", "stored evidence snapshot"),
                    locator_digest=_required_text(item, "locator_digest", "stored evidence snapshot"),
                )
                for item in evidence_values
            ),
            key=lambda item: item.evidence_id,
        )
    )
    return EvidenceReadReceipt(
        receipt_id=_required_text(payload, "receipt_id", "stored evidence read receipt"),
        tenant_id=_required_text(payload, "tenant_id", "stored evidence read receipt"),
        product=_required_text(payload, "product", "stored evidence read receipt"),
        scope_id=_required_text(payload, "scope_id", "stored evidence read receipt"),
        correlation_id=_required_text(payload, "correlation_id", "stored evidence read receipt"),
        principal_fingerprint=_required_text(payload, "principal_fingerprint", "stored evidence read receipt"),
        context_version=_required_text(payload, "context_version", "stored evidence read receipt"),
        context_packet_digest=_required_text(payload, "context_packet_digest", "stored evidence read receipt"),
        context_qualified=_required_bool(payload, "context_qualified", "stored evidence read receipt"),
        packet_complete=_required_bool(payload, "packet_complete", "stored evidence read receipt"),
        evidence=evidence,
        issued_at=_required_timestamp(payload, "issued_at", "stored evidence read receipt"),
        expires_at=_required_timestamp(payload, "expires_at", "stored evidence read receipt"),
        signature=_required_text(payload, "signature", "stored evidence read receipt"),
    )


def _payload_from_json(serialized: str) -> dict[str, object]:
    try:
        value: object = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise EvidenceReadReceiptError("stored evidence read receipt payload is not JSON") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EvidenceReadReceiptError("stored evidence read receipt payload is invalid")
    return value


def _required_text(payload: Mapping[str, object] | object, field: str, label: str) -> str:
    if not isinstance(payload, Mapping):
        raise EvidenceReadReceiptError(f"{label} must be an object")
    value = payload.get(field)
    if not isinstance(value, str):
        raise EvidenceReadReceiptError(f"{label}.{field} must be a string")
    return value


def _required_bool(payload: Mapping[str, object], field: str, label: str) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise EvidenceReadReceiptError(f"{label}.{field} must be a boolean")
    return value


def _required_timestamp(payload: Mapping[str, object], field: str, label: str) -> datetime:
    value = _required_text(payload, field, label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise EvidenceReadReceiptError(f"{label}.{field} must be an ISO timestamp") from error
    return _utc(parsed, f"{label}.{field}")


def _signature(secret: bytes, payload: Mapping[str, object]) -> str:
    return "sha256:" + hmac.new(secret, _canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise EvidenceReadReceiptError(f"{label} is invalid")
    return value


def _product(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value):
        raise EvidenceReadReceiptError("evidence read product is invalid")
    return value


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise EvidenceReadReceiptError(f"{label} is invalid")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceReadReceiptError(f"{label} is invalid")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceReadReceiptError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)
