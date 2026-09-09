"""Context health exposes uncertainty instead of silently degrading a decision."""

from __future__ import annotations

import pytest

from company_brain import (
    ContextHealthError,
    ContextHealthIssueKind,
    ContextHealthState,
    ContextPacketBudget,
    DecisionContext,
    DecisionContextRelationship,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    context_health_report,
    context_packet_from_decision_context,
)


def _context(*, qualified: bool = True, limitations: tuple[str, ...] = ()) -> DecisionContext:
    reference = EvidenceReference("evidence:health", "adr", "knowledge://adr/health", "revision-1", authorized=True)
    relationship = DecisionContextRelationship(
        source_id="service:payments",
        source_label="payments",
        relationship=RelationshipKind.DEPENDS_ON,
        target_id="service:ledger",
        target_label="ledger",
        confidence=0.9,
        freshness=FactFreshness.FRESH,
        evidence=(reference,),
    )
    return DecisionContext(
        context_version="world-model:v1:health",
        qualified=qualified,
        confidence=0.9 if qualified else 0.0,
        relationships=(relationship,),
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, (reference,), limitations),
        limitations=limitations,
        conflict_ids=(),
    )


def test_ready_context_health_can_support_an_advisory_decision() -> None:
    context = _context()
    report = context_health_report(context, context_packet_from_decision_context(context))

    assert report.state is ContextHealthState.READY
    assert report.proposal_eligible is True
    assert report.issues == ()


def test_limited_and_unqualified_contexts_explain_why_they_cannot_advance() -> None:
    limited = _context(limitations=("A required source is stale.",))
    limited_report = context_health_report(
        limited,
        context_packet_from_decision_context(
            limited,
            budget=ContextPacketBudget(
                maximum_relationships=1,
                maximum_evidence=1,
                maximum_limitations=1,
                maximum_conflicts=1,
                maximum_rendered_bytes=4_096,
            ),
        ),
    )
    unqualified = _context(qualified=False)
    unqualified_report = context_health_report(unqualified, context_packet_from_decision_context(unqualified))

    assert limited_report.state is ContextHealthState.LIMITED
    assert {item.kind for item in limited_report.issues} == {ContextHealthIssueKind.LIMITATION}
    assert limited_report.proposal_eligible is False
    assert unqualified_report.state is ContextHealthState.UNQUALIFIED
    assert ContextHealthIssueKind.CONTEXT_UNQUALIFIED in {item.kind for item in unqualified_report.issues}


def test_health_refuses_to_mix_a_packet_from_another_context() -> None:
    context = _context()
    unrelated = DecisionContext(
        context_version="world-model:v1:other",
        qualified=True,
        confidence=0.9,
        relationships=(),
        evidence=EvidenceBundle(EvidenceBasis.DERIVED, (), ("No relationship.",)),
        limitations=("No relationship.",),
        conflict_ids=(),
    )

    with pytest.raises(ContextHealthError, match="context_version"):
        context_health_report(context, context_packet_from_decision_context(unrelated))
