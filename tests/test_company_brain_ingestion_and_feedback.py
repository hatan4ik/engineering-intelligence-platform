import pytest

from company_brain.feedback import CompanyBrainFeedbackProjector
from company_brain.model import CompanyBrain, EntityKind, RelationshipKind
from company_brain.projector import CompanyBrainProjector, repository_id, service_id
from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline
from product.pr_guardian.contracts import (
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FindingAction,
    FindingOutcome,
    PRFinding,
    ReviewerRiskDisposition,
    ReviewerUtilityDisposition,
)


def change() -> FileChange:
    return FileChange(
        source=SourceIdentity("github", "acme/payments", "main", "deadbeef", "services/payments/app.py"),
        change_type=ChangeType.UPSERT,
        content="def pay(): pass",
        language="python",
        owner="team-payments",
        service="payments",
        acl=ACL(groups=("engineering",)),
    )


def finding() -> PRFinding:
    return PRFinding(
        finding_id="pr:acme/payments:42:dependency",
        repository="acme/payments",
        pr_number=42,
        head_sha="deadbeef",
        severity="high",
        summary="Payments dependency boundary changed.",
        correlation_id="corr-42",
        policy_version="pr-policy-2026-08",
        simulated_action=FindingAction.WOULD_BLOCK,
        evidence=EvidenceBundle(
            basis=EvidenceBasis.MEASURED,
            references=(
                EvidenceReference("adr-001", "adr", "knowledge://adr/001", authorized=True),
            ),
            limitations=(),
        ),
    )


def test_ingestion_pipeline_optionally_projects_authorized_changes_to_company_brain():
    brain = CompanyBrain()
    pipeline = IngestionPipeline(
        InMemoryIndex(),
        brain_projector=CompanyBrainProjector(brain),
    )
    event = NormalizedEvent("event-1", (change(),))

    result = pipeline.process(event)

    assert result["upserted"] == 1
    assert repository_id(provider="github", repository="acme/payments") in brain.entities
    assert service_id("payments") in brain.entities
    assert brain.evidence


def test_pr_finding_and_explicit_outcome_return_to_company_memory_without_copying_acl_less_evidence():
    brain = CompanyBrain()
    feedback = CompanyBrainFeedbackProjector(brain)
    finding_id = feedback.project_finding(finding())
    outcome_id = feedback.project_outcome(
        FindingOutcome(
            finding_id="pr:acme/payments:42:dependency",
            reviewer_risk=ReviewerRiskDisposition.CONFIRMED_RISK,
            reviewer_utility=ReviewerUtilityDisposition.USEFUL,
            post_merge_correlation_id="deployment:payments:2026-08-26",
        )
    )

    assert brain.entities[finding_id].kind is EntityKind.FINDING
    assert brain.entities[outcome_id].kind is EntityKind.OUTCOME
    assert brain.evidence == {}
    assert any(
        item.source_id == finding_id and item.target_id == outcome_id and item.kind is RelationshipKind.HAS_OUTCOME
        for item in brain.relationships
    )


def test_outcomes_cannot_exist_without_a_prior_finding():
    with pytest.raises(ValueError, match="finding must exist"):
        CompanyBrainFeedbackProjector(CompanyBrain()).project_outcome(
            FindingOutcome(
                finding_id="missing",
                reviewer_risk=ReviewerRiskDisposition.NOT_REVIEWED,
                reviewer_utility=ReviewerUtilityDisposition.NOT_REVIEWED,
            )
        )
