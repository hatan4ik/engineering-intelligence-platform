"""The why-answer evaluator checks citations, scope, abstention, and omissions."""

from __future__ import annotations

from pathlib import Path

from company_brain import (
    DecisionContext,
    DecisionContextRelationship,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FactFreshness,
    RelationshipKind,
    WhyAnswer,
    WhyAnswerDisposition,
    WhyEvaluationFailure,
    context_packet_from_decision_context,
    evaluate_why_answer,
    load_why_evaluation_cases,
    relationship_key,
)


CORPUS = Path(__file__).resolve().parents[1] / "eval" / "company_brain_why_cases.json"


def _context(*, qualified: bool = True) -> DecisionContext:
    reference = EvidenceReference(
        "evidence:dependency",
        "adr",
        "knowledge://adr/dependency",
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
        context_version="world-model:v1:why-eval",
        qualified=qualified,
        confidence=0.9 if qualified else 0.0,
        relationships=(relationship,),
        evidence=EvidenceBundle(EvidenceBasis.MEASURED, (reference,), ()),
        limitations=(),
        conflict_ids=(),
    )


def test_reviewed_corpus_loads_and_a_cited_answer_passes() -> None:
    first, _ = load_why_evaluation_cases(CORPUS)
    context = _context()
    packet = context_packet_from_decision_context(context)
    answer = WhyAnswer(
        context_version=packet.context_version,
        context_packet_digest=packet.digest,
        disposition=WhyAnswerDisposition.ANSWER,
        explanation="Checkout has a qualified dependency on payments.",
        relationship_keys=(relationship_key(context.relationships[0]),),
        cited_evidence_ids=("evidence:dependency",),
        limitations_disclosed=False,
    )

    result = evaluate_why_answer(first, answer, packet)

    assert result.passed is True
    assert result.citation_coverage == 1.0


def test_evaluator_rejects_hallucinated_claims_and_unsafe_answers() -> None:
    _, abstention_case = load_why_evaluation_cases(CORPUS)
    packet = context_packet_from_decision_context(_context(qualified=False))
    answer = WhyAnswer(
        context_version=packet.context_version,
        context_packet_digest=packet.digest,
        disposition=WhyAnswerDisposition.ANSWER,
        explanation="This unsupported relationship is safe.",
        relationship_keys=("service:checkout|depends_on|service:payments",),
        cited_evidence_ids=("evidence:dependency",),
        limitations_disclosed=False,
    )

    result = evaluate_why_answer(abstention_case, answer, packet)

    assert result.passed is False
    assert WhyEvaluationFailure.WRONG_DISPOSITION in result.failures
    assert WhyEvaluationFailure.UNSAFE_CONTEXT_ANSWER in result.failures
    assert WhyEvaluationFailure.LIMITATIONS_NOT_DISCLOSED in result.failures
