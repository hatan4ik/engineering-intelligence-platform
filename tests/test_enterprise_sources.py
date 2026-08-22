from ingestion.enterprise_sources import (
    AzureDevOpsBoardsAdapter,
    ConfluenceAdapter,
    ConversationIngestionPolicy,
    JiraAdapter,
    governed_conversation_document,
)
from ingestion.documents import KnowledgeSourceType
from ingestion.models import ACL


class Transport:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get_json(self, url, *, headers=None):
        self.urls.append(url)
        return self.payload


def acl():
    return ACL(groups=("engineering",), users=())


def test_ado_boards_maps_work_item_with_provenance():
    transport = Transport({"value": [{
        "id": 42,
        "rev": 3,
        "url": "https://dev.azure.com/acme/_apis/wit/workItems/42",
        "fields": {
            "System.Title": "Rotate signing key",
            "System.Description": "Use managed rotation",
            "System.State": "Active",
            "System.ChangedDate": "2026-08-22T10:00:00Z",
            "System.WorkItemType": "Task",
            "Custom.Service": "payments",
        },
    }]})
    page = AzureDevOpsBoardsAdapter(transport, "https://dev.azure.com/acme", "Platform", acl()).fetch_work_items([42])
    doc = page.documents[0]
    assert doc.identity.provider == "azure-devops"
    assert doc.identity.source_type is KnowledgeSourceType.WORK_ITEM
    assert doc.revision == "3"
    assert doc.service == "payments"
    assert doc.acl.groups == ("engineering",)


def test_jira_adf_and_service_label_are_normalized():
    transport = Transport({
        "issues": [{
            "id": "1001",
            "key": "PLAT-7",
            "fields": {
                "summary": "Checkout retries",
                "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Retry only idempotent calls"}]}]},
                "updated": "2026-08-22T10:00:00Z",
                "labels": ["service:checkout", "platform"],
                "status": {"name": "In Progress"},
                "project": {"key": "PLAT"},
                "assignee": {"displayName": "Owner"},
            },
        }],
        "nextPageToken": "next-1",
    })
    page = JiraAdapter(transport, "https://acme.atlassian.net", acl()).search(jql="project=PLAT")
    doc = page.documents[0]
    assert "Retry only idempotent calls" in doc.body
    assert doc.service == "checkout"
    assert page.next_url == "next-1"


def test_confluence_classifies_adr_and_strips_storage_html():
    transport = Transport({
        "results": [{
            "id": "123",
            "title": "ADR-004 Use managed identity",
            "body": {"storage": {"value": "<p>Secrets must not be embedded.</p>"}},
            "version": {"number": 5, "createdAt": "2026-08-22T10:00:00Z"},
        }],
        "_links": {"next": "/wiki/api/v2/pages?cursor=x"},
    })
    page = ConfluenceAdapter(transport, "https://acme.atlassian.net", acl()).pages(space_id="SPACE")
    doc = page.documents[0]
    assert doc.identity.source_type is KnowledgeSourceType.ADR
    assert doc.body == "Secrets must not be embedded."
    assert doc.revision == "5"
    assert page.next_url.endswith("cursor=x")


def test_conversation_ingestion_is_explicitly_governed():
    policy = ConversationIngestionPolicy(("platform-decisions",), require_explicit_knowledge_marker=True)
    denied = governed_conversation_document(
        provider="teams", conversation_id="1", channel="random", author="a",
        text="#decision use Redis", updated_at="2026-08-22T10:00:00Z", revision="1",
        acl=acl(), policy=policy,
    )
    unmarked = governed_conversation_document(
        provider="teams", conversation_id="2", channel="platform-decisions", author="a",
        text="use Redis", updated_at="2026-08-22T10:00:00Z", revision="1",
        acl=acl(), policy=policy,
    )
    accepted = governed_conversation_document(
        provider="teams", conversation_id="3", channel="platform-decisions", author="a",
        text="#decision use Redis for ephemeral locks", updated_at="2026-08-22T10:00:00Z", revision="1",
        acl=acl(), policy=policy,
    )
    assert denied is None
    assert unmarked is None
    assert accepted is not None
    assert accepted.identity.source_type is KnowledgeSourceType.CONVERSATION
    assert accepted.metadata["governance"] == "explicit-marker"
