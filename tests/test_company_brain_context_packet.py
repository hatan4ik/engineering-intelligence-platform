"""The bounded Context Packet never hides a partial decision context."""

from __future__ import annotations

import pytest

from company_brain import (
    ContextPacket,
    ContextPacketBudget,
    ContextPacketError,
    ContextPacketOmissionReason,
    ContextPacketSection,
    DecisionContext,
    DecisionContextRelationship,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    context_packet_from_decision_context,
)


def _reference(number: int) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=f"evidence:{number}",
        source_kind="adr",
        locator=f"knowledge://adr/{number}",
        revision=f"revision-{number}",
        authorized=True,
    )


def _relationship(number: int) -> DecisionContextRelationship:
    return DecisionContextRelationship(
        source_id=f"service:{number}",
        source_label=f"service-{number}",
        relationship=RelationshipKind.DEPENDS_ON,
        target_id=f"service:dependency-{number}",
        target_label=f"dependency-{number}",
        confidence=0.9,
        freshness=FactFreshness.FRESH,
        evidence=(_reference(number),),
    )


def _context(*, long_values: bool = False) -> DecisionContext:
    relationships: tuple[DecisionContextRelationship, ...] = (_relationship(1), _relationship(2))
    if long_values:
        relationships = (
            DecisionContextRelationship(
                source_id="service:very-long-source",
                source_label="source-" + "x" * 290,
                relationship=RelationshipKind.DEPENDS_ON,
                target_id="service:very-long-target",
                target_label="target-" + "y" * 290,
                confidence=0.9,
                freshness=FactFreshness.FRESH,
                evidence=(
                    EvidenceReference(
                        evidence_id="evidence:long",
                        source_kind="documentation",
                        locator="knowledge://" + "z" * 480,
                        revision="revision-long",
                        authorized=True,
                    ),
                ),
            ),
        )
    evidence = tuple(
        sorted(
            {reference for relationship in relationships for reference in relationship.evidence} | {_reference(3)},
            key=lambda item: str(item.evidence_id),
        )
    )
    return DecisionContext(
        context_version="world-model:v1:context-packet-test",
        qualified=True,
        confidence=0.9,
        relationships=relationships,
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, evidence, ()),
        limitations=("A source is awaiting routine revalidation.",),
        conflict_ids=("ambiguous-ownership:service:legacy",),
    )


def test_packet_is_deterministic_bounded_and_discloses_every_omission() -> None:
    context = _context()
    budget = ContextPacketBudget(
        maximum_relationships=1,
        maximum_evidence=1,
        maximum_limitations=1,
        maximum_conflicts=1,
        maximum_rendered_bytes=4_096,
    )

    packet = context_packet_from_decision_context(context, budget=budget)

    assert [item.statement for item in packet.relationships] == ["service-1 depends on dependency-1"]
    assert [str(item.evidence_id) for item in packet.evidence] == ["evidence:1"]
    assert packet.complete is False
    assert packet.rendered_bytes <= budget.maximum_rendered_bytes
    assert (
        ContextPacketSection.RELATIONSHIPS,
        ContextPacketOmissionReason.RELATIONSHIP_LIMIT,
        1,
    ) in {(item.section, item.reason, item.count) for item in packet.omissions}
    assert (
        ContextPacketSection.EVIDENCE,
        ContextPacketOmissionReason.EVIDENCE_LIMIT,
        2,
    ) in {(item.section, item.reason, item.count) for item in packet.omissions}
    assert context_packet_from_decision_context(context, budget=budget).digest == packet.digest


def test_packet_drops_whole_relationship_when_its_evidence_cannot_fit() -> None:
    first = _reference(1)
    second = _reference(2)
    relationship = DecisionContextRelationship(
        source_id="service:payments",
        source_label="payments",
        relationship=RelationshipKind.DEPENDS_ON,
        target_id="service:ledger",
        target_label="ledger",
        confidence=0.9,
        freshness=FactFreshness.FRESH,
        evidence=(first, second),
    )
    context = DecisionContext(
        context_version="world-model:v1:two-evidence",
        qualified=True,
        confidence=0.9,
        relationships=(relationship,),
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, (first, second), ()),
        limitations=(),
        conflict_ids=(),
    )
    budget = ContextPacketBudget(
        maximum_relationships=2,
        maximum_evidence=1,
        maximum_limitations=1,
        maximum_conflicts=1,
        maximum_rendered_bytes=4_096,
    )

    packet = context_packet_from_decision_context(context, budget=budget)

    assert packet.relationships == ()
    assert [str(item.evidence_id) for item in packet.evidence] == ["evidence:1"]
    assert (
        ContextPacketSection.RELATIONSHIPS,
        ContextPacketOmissionReason.EVIDENCE_LIMIT,
        1,
    ) in {(item.section, item.reason, item.count) for item in packet.omissions}


def test_packet_enforces_byte_budget_with_a_visible_omission() -> None:
    packet = context_packet_from_decision_context(
        _context(long_values=True),
        budget=ContextPacketBudget(
            maximum_relationships=1,
            maximum_evidence=2,
            maximum_limitations=1,
            maximum_conflicts=1,
            maximum_rendered_bytes=1_024,
        ),
    )

    assert packet.relationships == ()
    assert packet.rendered_bytes <= packet.budget.maximum_rendered_bytes
    assert any(
        item.section is ContextPacketSection.RELATIONSHIPS
        and item.reason is ContextPacketOmissionReason.BYTE_LIMIT
        for item in packet.omissions
    )


def test_packet_rejects_a_relationship_without_all_of_its_evidence() -> None:
    context = _context()
    with pytest.raises(ContextPacketError, match="retain every evidence"):
        ContextPacket(
            context_version=context.context_version,
            qualified=context.qualified,
            confidence=context.confidence,
            relationships=(context.relationships[0],),
            evidence=(),
            limitations=(),
            conflict_ids=(),
            omissions=(),
            budget=ContextPacketBudget(maximum_rendered_bytes=4_096),
        )


def test_packet_enforces_hard_and_configured_budget_ceilings() -> None:
    with pytest.raises(ContextPacketError, match="maximum_relationships"):
        ContextPacketBudget(maximum_relationships=101)
    with pytest.raises(ContextPacketError, match="maximum_evidence"):
        ContextPacketBudget(maximum_evidence=201)
    with pytest.raises(ContextPacketError, match="maximum_rendered_bytes"):
        ContextPacketBudget(maximum_rendered_bytes=65_537)

    context = _context()
    with pytest.raises(ContextPacketError, match="relationships exceed"):
        ContextPacket(
            context_version=context.context_version,
            qualified=context.qualified,
            confidence=context.confidence,
            relationships=context.relationships,
            evidence=context.evidence.references,
            limitations=context.limitations,
            conflict_ids=context.conflict_ids,
            omissions=(),
            budget=ContextPacketBudget(
                maximum_relationships=1,
                maximum_evidence=3,
                maximum_limitations=1,
                maximum_conflicts=1,
                maximum_rendered_bytes=4_096,
            ),
        )
