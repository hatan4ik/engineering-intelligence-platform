"""Cross-product Company Brain contracts stay typed and product-independent."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import company_brain.product_contracts as shared_contracts
from company_brain import (
    BrainEntity,
    CompanyBrainError,
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FindingProvenance,
    ProductContractError,
    ProductFinding,
    ProductSubject,
)
from company_brain.model import BrainRelationship, EntityKind, RelationshipKind
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
            EvidenceReference("evidence:adr-001", "adr", "knowledge://adr/001", "revision-001", authorized=True),
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


def test_nominal_identifiers_resolve_and_validate_shape() -> None:
    evidence_id = shared_contracts.resolve_evidence_id("evidence:test-001")
    finding_id = shared_contracts.resolve_finding_id("finding:test-001")
    outcome_id = shared_contracts.resolve_outcome_id("outcome:test-001")
    entity_id = shared_contracts.resolve_entity_id("entity:test-001")

    assert evidence_id == "evidence:test-001"
    assert finding_id == "finding:test-001"
    assert outcome_id == "outcome:test-001"
    assert entity_id == "entity:test-001"

    with pytest.raises(shared_contracts.ProductContractError, match="evidence_id is invalid"):
        shared_contracts.resolve_evidence_id("invalid/id/with\nnewline")


def test_describe_evidence_basis_is_exhaustive() -> None:
    for basis in EvidenceBasis:
        desc = shared_contracts.describe_evidence_basis(basis)
        assert desc == basis.value


def test_strenum_backing_strings_are_rejected_at_domain_boundaries() -> None:
    with pytest.raises(CompanyBrainError, match="entity kind"):
        BrainEntity("service:payments", cast(EntityKind, "service"), "payments")
    with pytest.raises(CompanyBrainError, match="relationship kind"):
        BrainRelationship("service:checkout", "service:payments", cast(RelationshipKind, "depends_on"))
    with pytest.raises(ProductContractError, match="evidence basis"):
        EvidenceBundle(cast(EvidenceBasis, "measured"), _evidence().references, ())
    with pytest.raises(ProductContractError, match="subject kind"):
        ProductSubject(
            "repository:github:acme/payments",
            cast(EntityKind, "repository"),
            "acme/payments",
        )

    valid = ProductFinding(
        finding_id="operations:incident:42",
        product="operations",
        scope=ProductSubject("repository:github:acme/payments", EntityKind.REPOSITORY, "acme/payments"),
        subject=ProductSubject("incident:payments:42", EntityKind.INCIDENT, "Incident 42"),
        scope_relationship=RelationshipKind.CHANGED_BY,
        severity="high",
        summary="A typed operational finding.",
        correlation_id="corr-42",
        evidence=EvidenceBundle(EvidenceBasis.DERIVED, (), ("No authorized source was available.",)),
        provenance=FindingProvenance("ops-policy-v1", "world-model:v1:test", False),
        recommendation="ticket",
    )
    with pytest.raises(ProductContractError, match="scope_relationship"):
        ProductFinding(**{**valid.__dict__, "scope_relationship": cast(RelationshipKind, "changed_by")})
