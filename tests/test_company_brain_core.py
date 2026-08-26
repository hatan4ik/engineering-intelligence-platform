from datetime import datetime, timezone

import pytest

from company_brain.model import (
    BrainEvidence,
    BrainPrincipal,
    CompanyBrain,
    CompanyBrainError,
    EntityKind,
    RelationshipKind,
)
from company_brain.projector import CompanyBrainProjector, repository_id, service_id
from ingestion.documents import KnowledgeDocument, KnowledgeIdentity, KnowledgeSourceType
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from product.pr_guardian.company_brain import PRGuardianCompanyBrainAdapter


def change(*, service: str, owner: str, path: str, sha: str = "deadbeef") -> FileChange:
    return FileChange(
        source=SourceIdentity(
            provider="github",
            repository="acme/payments",
            branch="main",
            commit_sha=sha,
            path=path,
        ),
        change_type=ChangeType.UPSERT,
        content="apiVersion: v1",
        language="yaml",
        service=service,
        owner=owner,
        acl=ACL(groups=("engineering",)),
    )


def test_governed_change_becomes_repository_service_owner_and_authorized_evidence():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    result = projector.project_file_change(
        change(service="payments", owner="team-payments", path="services/payments/deployment.yaml")
    )
    repo = repository_id(provider="github", repository="acme/payments")
    service = service_id("payments")

    allowed = brain.context_for_change(
        repository_id=repo,
        changed_services=(service,),
        principal=BrainPrincipal(groups=("engineering",)),
    )
    denied = brain.context_for_change(
        repository_id=repo,
        changed_services=(service,),
        principal=BrainPrincipal(groups=("finance",)),
    )

    assert result.evidence_id in brain.evidence
    assert allowed.changed_services == (service,)
    assert allowed.owner_ids == ("owner:team-payments",)
    assert [item.evidence_id for item in allowed.evidence] == [result.evidence_id]
    assert denied.evidence == ()
    assert denied.limitations == ("No authorized evidence was available for the requested company context.",)


def test_dependency_blast_radius_is_graph_based_and_repository_scoped():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    projector.project_file_change(change(service="payments", owner="team-payments", path="services/payments/app.yaml"))
    projector.project_file_change(change(service="orders", owner="team-orders", path="services/orders/app.yaml"))
    repo = repository_id(provider="github", repository="acme/payments")
    payments = service_id("payments")
    orders = service_id("orders")
    brain.relate(source_id=orders, target_id=payments, kind=RelationshipKind.DEPENDS_ON)

    context = brain.context_for_change(
        repository_id=repo,
        changed_services=(payments,),
        principal=BrainPrincipal(groups=("engineering",)),
    )

    assert context.blast_radius == (orders, payments)
    assert context.owner_ids == ("owner:team-orders", "owner:team-payments")


def test_knowledge_documents_add_governance_and_only_explicit_causal_edges():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    projector.project_file_change(change(service="payments", owner="team-payments", path="services/payments/app.yaml"))
    runbook = projector.project_knowledge_document(
        KnowledgeDocument(
            identity=KnowledgeIdentity("confluence", KnowledgeSourceType.RUNBOOK, "restart-payments"),
            title="Restart payments",
            body="Runbook body",
            revision="7",
            updated_at=datetime.now(timezone.utc),
            service="payments",
            acl=ACL(groups=("engineering",)),
        )
    )
    change_id = "change:github:acme/payments:main:deadbeef:services/payments/app.yaml"
    incident = projector.project_knowledge_document(
        KnowledgeDocument(
            identity=KnowledgeIdentity("confluence", KnowledgeSourceType.INCIDENT, "inc-123"),
            title="Payments incident",
            body="Incident body",
            revision="2",
            updated_at=datetime.now(timezone.utc),
            service="payments",
            acl=ACL(groups=("engineering",)),
            metadata={"caused_by": change_id, "resolved_by": "runbook:confluence:restart-payments"},
        )
    )

    assert runbook.unresolved_relationships == ()
    assert incident.unresolved_relationships == ()
    kinds = {(item.source_id, item.target_id, item.kind) for item in brain.relationships}
    assert (change_id, "incident:confluence:inc-123", RelationshipKind.CAUSED) in kinds
    assert ("incident:confluence:inc-123", "runbook:confluence:restart-payments", RelationshipKind.RESOLVED_BY) in kinds


def test_pr_guardian_adapter_returns_only_authorized_company_context_and_neutral_contracts():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    projector.project_file_change(change(service="payments", owner="team-payments", path="services/payments/app.yaml"))
    projector.project_file_change(change(service="orders", owner="team-orders", path="services/orders/app.yaml"))
    brain.relate(
        source_id=service_id("orders"),
        target_id=service_id("payments"),
        kind=RelationshipKind.DEPENDS_ON,
    )
    adapter = PRGuardianCompanyBrainAdapter(brain)

    context = adapter.context_for(
        repository="acme/payments",
        changed_services=("payments",),
        principal=BrainPrincipal(groups=("engineering",)),
    )

    assert context.changed_services == ("payments",)
    assert context.blast_radius == ("orders", "payments")
    assert set(context.graph.nodes) == {"orders", "payments"}
    assert context.graph.nodes["orders"].dependencies == ("payments",)
    assert context.evidence.references

    denied = adapter.context_for(
        repository="acme/payments",
        changed_services=("payments",),
        principal=BrainPrincipal(groups=("finance",)),
    )
    assert denied.evidence.references == ()
    assert denied.evidence.limitations


def test_relationships_reject_unknown_evidence_and_empty_principals_fail_closed():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    projector.project_file_change(change(service="payments", owner="team-payments", path="services/payments/app.yaml"))
    service = service_id("payments")
    repo = repository_id(provider="github", repository="acme/payments")

    with pytest.raises(CompanyBrainError, match="unknown evidence"):
        brain.relate(
            source_id=service,
            target_id=repo,
            kind=RelationshipKind.BELONGS_TO,
            evidence_ids=("evidence:missing",),
        )
    with pytest.raises(CompanyBrainError, match="principal requires"):
        BrainPrincipal()
    assert not BrainEvidence(
        evidence_id="evidence:unscoped",
        source_kind="test",
        citation="test://unscoped",
        revision="1",
    ).visible_to(BrainPrincipal(groups=("engineering",)))


def test_in_memory_projector_removes_prior_file_revisions_when_a_source_is_deleted():
    brain = CompanyBrain()
    projector = CompanyBrainProjector(brain)
    projector.project_file_change(change(service="payments", owner="team-payments", path="services/payments/app.yaml"))
    deleting_change = FileChange(
        source=SourceIdentity(
            provider="github",
            repository="acme/payments",
            branch="main",
            commit_sha="new-delete-commit",
            path="services/payments/app.yaml",
        ),
        change_type=ChangeType.DELETE,
        acl=ACL(groups=("engineering",)),
    )

    result = projector.project_file_change(deleting_change)

    assert result.deleted_entity_ids
    assert not brain.evidence
    assert not [item for item in brain.entities.values() if item.kind is EntityKind.CHANGE]
    assert service_id("payments") in brain.entities
