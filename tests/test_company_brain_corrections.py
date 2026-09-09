"""Human correction requests never mutate Company Brain facts directly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from company_brain import (
    BrainPrincipal,
    CorrectionError,
    CorrectionKind,
    CorrectionReviewDisposition,
    CorrectionService,
    DecisionContext,
    DecisionContextRelationship,
    DecisionScope,
    DecisionScopeKind,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReadReceiptAuthority,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    SqliteCorrectionStore,
    SqliteEvidenceReadReceiptStore,
    context_packet_from_decision_context,
)


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
PRINCIPAL = BrainPrincipal(users=("user:alice",))
SECRET = "correction-receipt-test-secret-at-least-32-chars"


def _context() -> DecisionContext:
    reference = EvidenceReference(
        "evidence:dependency",
        "adr",
        "knowledge://adr/payments-dependency",
        "revision-1",
        authorized=True,
    )
    relationship = DecisionContextRelationship(
        source_id="service:checkout",
        source_label="checkout",
        relationship=RelationshipKind.DEPENDS_ON,
        target_id="service:payments",
        target_label="payments",
        confidence=0.9,
        freshness=FactFreshness.FRESH,
        evidence=(reference,),
    )
    return DecisionContext(
        context_version="world-model:v1:correction",
        qualified=True,
        confidence=0.9,
        relationships=(relationship,),
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, (reference,), ()),
        limitations=(),
        conflict_ids=(),
    )


def _scope() -> DecisionScope:
    return DecisionScope(
        tenant_id="tenant-acme",
        product="pr-guardian",
        kind=DecisionScopeKind.PULL_REQUEST,
        scope_id="pr:acme/payments:42:deadbeef",
        label="acme/payments PR #42",
        correlation_id="corr-pr-42",
    )


def _service(tmp_path: Path) -> tuple[CorrectionService, EvidenceReadReceiptAuthority]:
    authority = EvidenceReadReceiptAuthority(
        secret=SECRET,
        store=SqliteEvidenceReadReceiptStore(tmp_path / "receipts.db"),
    )
    return CorrectionService(
        receipt_authority=authority,
        store=SqliteCorrectionStore(tmp_path / "corrections.db"),
    ), authority


def _receipt(authority: EvidenceReadReceiptAuthority):
    context = _context()
    packet = context_packet_from_decision_context(context)
    return authority.issue(
        tenant_id="tenant-acme",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        principal=PRINCIPAL,
        context=context,
        packet=packet,
        now=NOW,
    ), packet


def test_correction_is_receipt_bound_append_only_and_reviewable(tmp_path: Path) -> None:
    service, authority = _service(tmp_path)
    receipt, packet = _receipt(authority)
    scope = _scope()

    proposal = service.submit(
        request_id="correction-request-42",
        scope=scope,
        receipt_id=receipt.receipt_id,
        principal=PRINCIPAL,
        context_version=packet.context_version,
        context_packet_digest=packet.digest,
        target_key="relationship:service:checkout:depends_on:service:payments",
        kind=CorrectionKind.REPLACE_CLAIM,
        original_claim="checkout depends on payments",
        replacement_claim="checkout depends on payments-v2",
        rationale="The ADR was superseded by the verified migration decision.",
        requested_by="user:alice",
        now=NOW + timedelta(minutes=1),
    )
    review = service.review(
        correction_id=proposal.correction_id,
        reviewer="user:bob",
        reviewer_principal=BrainPrincipal(users=("user:bob",)),
        disposition=CorrectionReviewDisposition.ACCEPT_FOR_REVALIDATION,
        rationale="Reconcile the source before changing any retained relationship.",
        reviewed_at=NOW + timedelta(minutes=2),
    )

    store = SqliteCorrectionStore(tmp_path / "corrections.db")
    assert store.proposal(proposal.correction_id) == proposal
    assert store.reviews(proposal.correction_id) == (review,)
    assert proposal.requested_at == NOW + timedelta(minutes=1)
    assert review.disposition is CorrectionReviewDisposition.ACCEPT_FOR_REVALIDATION


def test_correction_rejects_a_receipt_after_it_expires(tmp_path: Path) -> None:
    service, authority = _service(tmp_path)
    receipt, packet = _receipt(authority)

    with pytest.raises(CorrectionError, match="stale"):
        service.submit(
            request_id="correction-request-stale",
            scope=_scope(),
            receipt_id=receipt.receipt_id,
            principal=PRINCIPAL,
            context_version=packet.context_version,
            context_packet_digest=packet.digest,
            target_key="relationship:service:checkout:depends_on:service:payments",
            kind=CorrectionKind.RETRACT_CLAIM,
            original_claim="checkout depends on payments",
            replacement_claim=None,
            rationale="The source needs revalidation.",
            requested_by="user:alice",
            now=NOW + timedelta(minutes=10),
        )


def test_correction_review_requires_a_retained_proposal(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(CorrectionError, match="requires a retained proposal"):
        service.review(
            correction_id="correction:missing",
            reviewer="user:bob",
            reviewer_principal=BrainPrincipal(users=("user:bob",)),
            disposition=CorrectionReviewDisposition.REJECT,
            rationale="There is no retained source-bound proposal.",
            reviewed_at=NOW,
        )


def test_correction_rejects_a_spoofed_human_identity(tmp_path: Path) -> None:
    service, authority = _service(tmp_path)
    receipt, packet = _receipt(authority)

    with pytest.raises(CorrectionError, match="authenticated principal user"):
        service.submit(
            request_id="correction-request-spoofed",
            scope=_scope(),
            receipt_id=receipt.receipt_id,
            principal=PRINCIPAL,
            context_version=packet.context_version,
            context_packet_digest=packet.digest,
            target_key="relationship:service:checkout:depends_on:service:payments",
            kind=CorrectionKind.RETRACT_CLAIM,
            original_claim="checkout depends on payments",
            replacement_claim=None,
            rationale="This actor is not the authenticated user.",
            requested_by="user:mallory",
            now=NOW + timedelta(minutes=1),
        )
