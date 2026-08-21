from datetime import datetime, timezone

from ingestion.documents import KnowledgeChange, KnowledgeSourceType
from ingestion.knowledge_normalizers import azure_devops_work_item, deployment_record, documentation_page
from ingestion.knowledge_pipeline import InMemoryKnowledgeIndex, KnowledgePipeline, chunk_document
from ingestion.models import ACL, ChangeType


def test_work_item_preserves_provenance_acl_and_revision():
    doc = azure_devops_work_item(
        {
            "id": 42,
            "rev": 7,
            "url": "https://dev.azure.com/acme/project/_apis/wit/workItems/42",
            "fields": {
                "System.Title": "JWT rotation failure",
                "System.State": "Active",
                "System.Description": "Rotate signing key and update runbook.",
                "System.ChangedDate": "2026-08-22T00:00:00Z",
                "System.WorkItemType": "Bug",
                "Custom.Service": "identity",
            },
        },
        acl=ACL(groups=("identity-team",)),
    )
    chunk = chunk_document(doc)[0]
    assert doc.identity.document_id == "knowledge:azure-devops:work_item:42"
    assert chunk.revision == "7"
    assert chunk.acl_groups == ("identity-team",)
    assert chunk.service == "identity"


def test_pipeline_replaces_revision_and_deletes_document():
    index = InMemoryKnowledgeIndex()
    pipeline = KnowledgePipeline(index)
    base = documentation_page(
        provider="confluence",
        page_id="auth-runbook",
        title="Auth Runbook",
        body="# Recovery\nRestart only after verifying dependency health.",
        revision="10",
        updated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        acl=ACL(groups=("sre",)),
        source_type=KnowledgeSourceType.RUNBOOK,
    )
    result = pipeline.process(KnowledgeChange(ChangeType.UPSERT, base))
    assert result["status"] == "indexed"
    assert pipeline.process(KnowledgeChange(ChangeType.UPSERT, base))["status"] == "duplicate"

    newer = documentation_page(
        provider="confluence",
        page_id="auth-runbook",
        title="Auth Runbook",
        body="# Recovery\nVerify SLO, then execute the approved rollback.",
        revision="11",
        updated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        acl=ACL(groups=("sre",)),
        source_type=KnowledgeSourceType.RUNBOOK,
    )
    assert pipeline.process(KnowledgeChange(ChangeType.UPSERT, newer))["revision"] == "11"
    assert index.revisions[newer.identity.document_id] == "11"
    assert all(c.revision == "11" for c in index.chunks[newer.identity.document_id])

    deleted = pipeline.process(KnowledgeChange(ChangeType.DELETE, newer))
    assert deleted["status"] == "deleted"
    assert newer.identity.document_id not in index.chunks


def test_deployment_history_becomes_retrievable_organizational_evidence():
    doc = deployment_record(
        {
            "id": "deploy-991",
            "service": "payments",
            "environment": "prod",
            "commit_sha": "abc123",
            "status": "failed",
            "timestamp": "2026-08-22T00:05:00Z",
        },
        acl=ACL(groups=("payments", "sre")),
    )
    assert doc.identity.source_type is KnowledgeSourceType.DEPLOYMENT
    assert "abc123" in doc.body
    assert doc.metadata["environment"] == "prod"
