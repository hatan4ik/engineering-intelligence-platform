"""Evidence read receipts bind proposals to one current authorized snapshot."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from company_brain import (
    BrainPrincipal,
    ContextPacket,
    ContextPacketBudget,
    DecisionContext,
    DecisionContextRelationship,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReadReceipt,
    EvidenceReadReceiptAuthority,
    EvidenceReadReceiptError,
    EvidenceReadReceiptId,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    SqliteEvidenceReadReceiptStore,
    context_packet_from_decision_context,
)


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
SECRET = "evidence-receipt-test-secret-at-least-32-chars"
PRINCIPAL = BrainPrincipal(groups=("engineering",))


def _context(*, qualified: bool = True, relationship_count: int = 1) -> DecisionContext:
    references = tuple(
        EvidenceReference(
            evidence_id=f"evidence:{number}",
            source_kind="adr",
            locator=f"knowledge://adr/{number}",
            revision=f"revision-{number}",
            authorized=True,
        )
        for number in range(relationship_count)
    )
    relationships = tuple(
        DecisionContextRelationship(
            source_id=f"service:{number}",
            source_label=f"service-{number}",
            relationship=RelationshipKind.DEPENDS_ON,
            target_id=f"service:dependency-{number}",
            target_label=f"dependency-{number}",
            confidence=0.9,
            freshness=FactFreshness.FRESH,
            evidence=(references[number],),
        )
        for number in range(relationship_count)
    )
    return DecisionContext(
        context_version="world-model:v1:evidence-receipt-test",
        qualified=qualified,
        confidence=0.9 if qualified else 0.0,
        relationships=relationships,
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, references, ()),
        limitations=(),
        conflict_ids=(),
    )


def _authority(tmp_path: Path) -> EvidenceReadReceiptAuthority:
    return EvidenceReadReceiptAuthority(
        secret=SECRET,
        store=SqliteEvidenceReadReceiptStore(str(tmp_path / "receipts.db")),
    )


def _issue(
    authority: EvidenceReadReceiptAuthority, context: DecisionContext
) -> tuple[EvidenceReadReceipt, ContextPacket]:
    packet = context_packet_from_decision_context(context)
    receipt = authority.issue(
        tenant_id="tenant-acme",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        principal=PRINCIPAL,
        context=context,
        packet=packet,
        now=NOW,
    )
    return receipt, packet


def test_receipt_is_durable_signed_and_binds_exact_evidence_revisions(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    receipt, packet = _issue(authority, _context())

    verified = authority.require_for_proposal(
        receipt_id=receipt.receipt_id,
        tenant_id="tenant-acme",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        principal=PRINCIPAL,
        context_version=packet.context_version,
        packet_digest=packet.digest,
        now=NOW + timedelta(minutes=1),
    )

    assert verified == receipt
    assert receipt.evidence[0].revision == "revision-0"
    assert receipt.evidence[0].locator_digest.startswith("sha256:")
    assert "knowledge://" not in receipt.canonical_unsigned_json()


def test_receipt_rejects_a_stale_or_different_principal_scope_or_packet(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    receipt, packet = _issue(authority, _context())

    with pytest.raises(EvidenceReadReceiptError, match="stale"):
        authority.require_for_proposal(
            receipt_id=receipt.receipt_id,
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:42:deadbeef",
            correlation_id="corr-pr-42",
            principal=PRINCIPAL,
            context_version=packet.context_version,
            packet_digest=packet.digest,
            now=NOW + timedelta(minutes=10),
        )
    with pytest.raises(EvidenceReadReceiptError, match="principal_fingerprint"):
        authority.require_for_proposal(
            receipt_id=receipt.receipt_id,
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:42:deadbeef",
            correlation_id="corr-pr-42",
            principal=BrainPrincipal(groups=("security",)),
            context_version=packet.context_version,
            packet_digest=packet.digest,
            now=NOW + timedelta(minutes=1),
        )
    with pytest.raises(EvidenceReadReceiptError, match="scope_id"):
        authority.require_for_proposal(
            receipt_id=receipt.receipt_id,
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:43:deadbeef",
            correlation_id="corr-pr-42",
            principal=PRINCIPAL,
            context_version=packet.context_version,
            packet_digest=packet.digest,
            now=NOW + timedelta(minutes=1),
        )


def test_proposal_requires_complete_qualified_context(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    context = _context(relationship_count=2)
    incomplete_packet = context_packet_from_decision_context(
        context,
        budget=ContextPacketBudget(
            maximum_relationships=1,
            maximum_evidence=2,
            maximum_limitations=1,
            maximum_conflicts=1,
            maximum_rendered_bytes=4_096,
        ),
    )
    receipt = authority.issue(
        tenant_id="tenant-acme",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        principal=PRINCIPAL,
        context=context,
        packet=incomplete_packet,
        now=NOW,
    )

    with pytest.raises(EvidenceReadReceiptError, match="omissions"):
        authority.require_for_proposal(
            receipt_id=receipt.receipt_id,
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:42:deadbeef",
            correlation_id="corr-pr-42",
            principal=PRINCIPAL,
            context_version=context.context_version,
            packet_digest=incomplete_packet.digest,
            now=NOW + timedelta(minutes=1),
        )


def test_receipt_retains_only_the_bounded_packet_evidence(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    context = _context(relationship_count=2)
    packet = context_packet_from_decision_context(
        context,
        budget=ContextPacketBudget(
            maximum_relationships=1,
            maximum_evidence=1,
            maximum_limitations=1,
            maximum_conflicts=1,
            maximum_rendered_bytes=4_096,
        ),
    )

    receipt = authority.issue(
        tenant_id="tenant-acme",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        principal=PRINCIPAL,
        context=context,
        packet=packet,
        now=NOW,
    )

    assert tuple(item.evidence_id for item in receipt.evidence) == tuple(
        str(item.evidence_id) for item in packet.evidence
    )


def test_receipt_refuses_a_packet_that_claims_to_be_complete_after_removing_evidence(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    context = _context()
    packet = context_packet_from_decision_context(context)
    forged = ContextPacket(
        context_version=packet.context_version,
        qualified=packet.qualified,
        confidence=packet.confidence,
        relationships=(),
        evidence=(),
        limitations=(),
        conflict_ids=(),
        omissions=(),
        budget=packet.budget,
    )

    with pytest.raises(EvidenceReadReceiptError, match="deterministic bounded projection"):
        authority.issue(
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:42:deadbeef",
            correlation_id="corr-pr-42",
            principal=PRINCIPAL,
            context=context,
            packet=forged,
            now=NOW,
        )


def test_tampered_stored_receipt_cannot_advance_a_proposal() -> None:
    store = _TamperedReceiptStore()
    authority = EvidenceReadReceiptAuthority(secret=SECRET, store=store)
    receipt, packet = _issue(authority, _context())
    store.value = replace(receipt, signature="sha256:" + "0" * 64)

    with pytest.raises(EvidenceReadReceiptError, match="signature"):
        authority.require_for_proposal(
            receipt_id=receipt.receipt_id,
            tenant_id="tenant-acme",
            product="pr-guardian",
            scope_id="pr:acme/payments:42:deadbeef",
            correlation_id="corr-pr-42",
            principal=PRINCIPAL,
            context_version=packet.context_version,
            packet_digest=packet.digest,
            now=NOW + timedelta(minutes=1),
        )


class _TamperedReceiptStore:
    """Minimal persistence fake used only to prove authority signature checks."""

    value: EvidenceReadReceipt | None = None

    def record(self, receipt: EvidenceReadReceipt) -> bool:
        self.value = receipt
        return True

    def get(self, receipt_id: EvidenceReadReceiptId | str) -> EvidenceReadReceipt | None:
        del receipt_id
        return self.value
