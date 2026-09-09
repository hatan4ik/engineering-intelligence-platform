"""Decision Briefs distinguish a human request from evidence-backed context."""

from __future__ import annotations

from company_brain import (
    ContextPacketBudget,
    DecisionContext,
    DecisionContextRelationship,
    DecisionRequest,
    DecisionScope,
    DecisionScopeKind,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    context_packet_from_decision_context,
    decision_brief_from_packet,
)


def _packet():
    ownership = DecisionContextRelationship(
        source_id="owner:payments",
        source_label="Payments Team",
        relationship=RelationshipKind.OWNS,
        target_id="service:payments",
        target_label="payments",
        confidence=0.9,
        freshness=FactFreshness.FRESH,
        evidence=(
            EvidenceReference(
                "evidence:ownership",
                "adr",
                "knowledge://adr/payments-owner",
                "revision-1",
                authorized=True,
            ),
        ),
    )
    context = DecisionContext(
        context_version="world-model:v1:brief",
        qualified=True,
        confidence=0.9,
        relationships=(ownership,),
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, ownership.evidence, ()),
        limitations=(),
        conflict_ids=(),
    )
    return context_packet_from_decision_context(
        context,
        budget=ContextPacketBudget(maximum_rendered_bytes=4_096),
    )


def test_brief_derives_owners_from_qualified_relationships_and_is_reproducible() -> None:
    packet = _packet()
    scope = DecisionScope(
        tenant_id="tenant-acme",
        product="pr-guardian",
        kind=DecisionScopeKind.PULL_REQUEST,
        scope_id="pr:acme/payments:42:deadbeef",
        label="acme/payments PR #42",
        correlation_id="corr-pr-42",
    )
    request = DecisionRequest(
        objective="Review the dependency impact before merge.",
        decision_question="Does this change require an additional owner review?",
        requested_by="user:alice",
    )

    brief = decision_brief_from_packet(scope=scope, request=request, context_packet=packet)

    assert brief.owner_ids == ("owner:payments",)
    assert brief.requires_human_review is False
    assert brief.payload()["context_packet_digest"] == packet.digest
    assert decision_brief_from_packet(scope=scope, request=request, context_packet=packet).brief_id == brief.brief_id


def test_brief_requires_human_review_when_the_bounded_context_is_limited() -> None:
    packet = _packet()
    limited = context_packet_from_decision_context(
        DecisionContext(
            context_version=packet.context_version,
            qualified=True,
            confidence=0.9,
            relationships=(),
            evidence=EvidenceBundle(
                EvidenceBasis.DERIVED,
                (),
                ("No decision relationship was retained.",),
            ),
            limitations=("No decision relationship was retained.",),
            conflict_ids=(),
        ),
        budget=ContextPacketBudget(maximum_rendered_bytes=4_096),
    )
    brief = decision_brief_from_packet(
        scope=DecisionScope(
            tenant_id="tenant-acme",
            product="pr-guardian",
            kind=DecisionScopeKind.PULL_REQUEST,
            scope_id="pr:acme/payments:43:deadbeef",
            label="acme/payments PR #43",
            correlation_id="corr-pr-43",
        ),
        request=DecisionRequest("Review", "Should this advance?", "user:alice"),
        context_packet=limited,
    )

    assert brief.requires_human_review is True
