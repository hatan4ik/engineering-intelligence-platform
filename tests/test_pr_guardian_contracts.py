import pytest

from product.pr_guardian.contracts import (
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    EvaluationRun,
    FindingAction,
    FindingOutcome,
    PRFinding,
    ProductContractError,
    ProductMode,
    RepositoryConfig,
    ReviewerRiskDisposition,
    ReviewerUtilityDisposition,
)


def evidence() -> EvidenceBundle:
    return EvidenceBundle(
        basis=EvidenceBasis.MEASURED,
        references=(
            EvidenceReference(
                evidence_id="adr-001",
                source_kind="adr",
                locator="knowledge://adr/001",
                authorized=True,
            ),
        ),
        limitations=("No deployment history was available for this service.",),
    )


def test_repository_scope_requires_named_owners_sources_and_a_non_enforcing_mode():
    config = RepositoryConfig(
        repository="acme/payments",
        service_ids=("payments",),
        owner_ids=("team-payments",),
        evidence_sources=("engineering-knowledge",),
        policy_version="pr-policy-2026-08",
        mode=ProductMode.SHADOW,
    )

    assert config.mode is ProductMode.SHADOW

    with pytest.raises(ProductContractError, match="owner_ids"):
        RepositoryConfig(
            repository="acme/payments",
            service_ids=("payments",),
            owner_ids=(),
            evidence_sources=("engineering-knowledge",),
            policy_version="pr-policy-2026-08",
        )


def test_finding_requires_authorized_evidence_and_only_simulates_actions():
    finding = PRFinding(
        finding_id="pr:acme/payments:42:architecture-boundary",
        repository="acme/payments",
        pr_number=42,
        head_sha="deadbeef",
        severity="high",
        summary="This change crosses the payments architecture boundary.",
        correlation_id="corr-42",
        policy_version="pr-policy-2026-08",
        context_version="world-model:v1:test",
        context_qualified=True,
        simulated_action=FindingAction.WOULD_BLOCK,
        evidence=evidence(),
    )

    assert finding.simulated_action is FindingAction.WOULD_BLOCK
    with pytest.raises(ProductContractError, match="unauthorized evidence"):
        EvidenceReference(
            evidence_id="private-incident",
            source_kind="incident",
            locator="knowledge://incident/1",
            authorized=False,
        )

    with pytest.raises(ProductContractError, match="unqualified context"):
        PRFinding(
            finding_id="pr:acme/payments:42:unqualified",
            repository="acme/payments",
            pr_number=42,
            head_sha="deadbeef",
            severity="high",
            summary="Unqualified context cannot propose a control.",
            correlation_id="corr-43",
            policy_version="pr-policy-2026-08",
            context_version="world-model:v1:unqualified",
            context_qualified=False,
            simulated_action=FindingAction.WOULD_BLOCK,
            evidence=EvidenceBundle(
                basis=EvidenceBasis.DERIVED,
                references=(),
                limitations=("No qualified context was available.",),
            ),
        )


def test_missing_evidence_is_explicit_and_not_reviewed_is_not_feedback():
    missing = EvidenceBundle(
        basis=EvidenceBasis.DERIVED,
        references=(),
        limitations=("No authorized historical regression evidence was available.",),
    )
    outcome = FindingOutcome(
        finding_id="pr:acme/payments:42:tests",
        reviewer_risk=ReviewerRiskDisposition.NOT_REVIEWED,
        reviewer_utility=ReviewerUtilityDisposition.NOT_REVIEWED,
    )

    assert missing.references == ()
    assert outcome.is_explicit_reviewer_feedback is False


def test_evaluation_is_bound_to_a_versioned_dataset_policy_and_stable_finding_set():
    run = EvaluationRun(
        evaluation_id="pr-guardian-golden-2026-08-26",
        dataset_version="golden-prs-2026-08",
        policy_version="pr-policy-2026-08",
        finding_ids=("finding-1", "finding-2"),
        methodology="Deterministic replay with ACL and evidence assertions.",
    )

    assert run.finding_ids == ("finding-1", "finding-2")
    with pytest.raises(ProductContractError, match="finding_ids"):
        EvaluationRun(
            evaluation_id="duplicate",
            dataset_version="golden-prs-2026-08",
            policy_version="pr-policy-2026-08",
            finding_ids=("finding-1", "finding-1"),
            methodology="Invalid duplicate finding set.",
        )
