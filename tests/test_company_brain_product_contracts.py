"""Cross-product Company Brain contracts stay typed and product-independent."""

from __future__ import annotations

from pathlib import Path

import pytest

import company_brain.product_contracts as shared_contracts
from company_brain import (
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FindingProvenance,
    ProductContractError,
    ProductFinding,
    ProductSubject,
)
from company_brain.model import EntityKind, RelationshipKind
from product.pr_guardian.company_brain_records import finding_record, outcome_records
from product.pr_guardian.contracts import (
    EvidenceBundle as PRGuardianEvidenceBundle,
    FindingAction,
    FindingOutcome,
    PRFinding,
    ReviewerRiskDisposition,
    ReviewerUtilityDisposition,
)


def _evidence() -> EvidenceBundle:
    return EvidenceBundle(
        basis=EvidenceBasis.MEASURED,
        references=(
            EvidenceReference("evidence:adr-001", "adr", "knowledge://adr/001", authorized=True),
        ),
        limitations=(),
    )


def _pr_finding() -> PRFinding:
    return PRFinding(
        finding_id="pr:acme/payments:42:dependency",
        repository="acme/payments",
        pr_number=42,
        head_sha="deadbeef",
        severity="high",
        summary="Payments dependency boundary changed.",
        correlation_id="corr-42",
        policy_version="pr-policy-2026-08",
        context_version="world-model:v1:test",
        context_qualified=True,
        simulated_action=FindingAction.WOULD_BLOCK,
        evidence=_evidence(),
    )


def test_pr_guardian_reuses_the_company_brain_evidence_contract() -> None:
    assert PRGuardianEvidenceBundle is shared_contracts.EvidenceBundle


def test_product_finding_requires_a_typed_scope_subject_and_provenance() -> None:
    scope = ProductSubject("repository:github:acme/payments", EntityKind.REPOSITORY, "acme/payments")
    subject = ProductSubject("incident:payments:42", EntityKind.INCIDENT, "Incident 42")
    record = ProductFinding(
        finding_id="operations:incident:42",
        product="operations",
        scope=scope,
        subject=subject,
        scope_relationship=RelationshipKind.CHANGED_BY,
        severity="high",
        summary="A typed operational finding.",
        correlation_id="corr-42",
        evidence=EvidenceBundle(
            basis=EvidenceBasis.DERIVED,
            references=(),
            limitations=("No authorized source was available.",),
        ),
        provenance=FindingProvenance("ops-policy-v1", "world-model:v1:test", False),
        recommendation="ticket",
    )

    assert record.scope.kind is EntityKind.REPOSITORY
    with pytest.raises(ProductContractError, match="must be distinct"):
        ProductFinding(**{**record.__dict__, "subject": scope})


def test_pr_adapter_maps_one_finding_and_two_explicit_outcome_dimensions() -> None:
    finding = _pr_finding()
    record = finding_record(finding)
    outcomes = outcome_records(
        FindingOutcome(
            finding_id=finding.finding_id,
            reviewer_risk=ReviewerRiskDisposition.CONFIRMED_RISK,
            reviewer_utility=ReviewerUtilityDisposition.USEFUL,
        )
    )

    assert record.product == "pr-guardian"
    assert record.scope.kind is EntityKind.REPOSITORY
    assert record.subject.kind is EntityKind.CHANGE
    assert {item.outcome_kind for item in outcomes} == {"reviewer-risk", "reviewer-utility"}


def test_company_brain_feedback_has_no_product_specific_import() -> None:
    source = (Path(__file__).resolve().parents[1] / "company_brain" / "feedback.py").read_text()

    assert "product.pr_guardian" not in source
