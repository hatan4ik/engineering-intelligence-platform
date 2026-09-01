from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from .documents import KnowledgeDocument, KnowledgeIdentity, KnowledgeSourceType
from .models import ACL


def _timestamp(value: object) -> datetime:
    """Normalize a trusted timestamp or reject an unknown external shape."""

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    if value is None or value == "":
        return datetime.now(timezone.utc)
    raise ValueError("timestamp must be an ISO-8601 string, datetime, or null")


def azure_devops_work_item(raw: Mapping[str, object], *, acl: ACL) -> KnowledgeDocument:
    fields = raw.get("fields") or {}
    if not isinstance(fields, Mapping):
        raise ValueError("work item fields must be an object")
    item_id = str(raw.get("id") or "")
    if not item_id:
        raise ValueError("work item id is required")
    title = str(fields.get("System.Title") or f"Work item {item_id}")
    description = str(fields.get("System.Description") or "")
    state = str(fields.get("System.State") or "")
    body = f"Title: {title}\nState: {state}\n\n{description}".strip()
    revision = str(raw.get("rev") or "1")
    return KnowledgeDocument(
        identity=KnowledgeIdentity(
            "azure-devops", KnowledgeSourceType.WORK_ITEM, item_id
        ),
        title=title,
        body=body,
        revision=revision,
        updated_at=_timestamp(fields.get("System.ChangedDate")),
        source_url=str(raw.get("url") or "") or None,
        owner=str(fields.get("System.AssignedTo") or "") or None,
        service=str(fields.get("Custom.Service") or "") or None,
        acl=acl,
        metadata={
            "state": state,
            "work_item_type": str(fields.get("System.WorkItemType") or ""),
        },
    )


def documentation_page(
    *,
    provider: str,
    page_id: str,
    title: str,
    body: str,
    revision: str,
    updated_at: str | datetime,
    acl: ACL,
    source_url: str | None = None,
    owner: str | None = None,
    service: str | None = None,
    source_type: KnowledgeSourceType = KnowledgeSourceType.DOCUMENTATION,
) -> KnowledgeDocument:
    if not page_id or not title:
        raise ValueError("page_id and title are required")
    return KnowledgeDocument(
        identity=KnowledgeIdentity(provider, source_type, page_id),
        title=title,
        body=body,
        revision=revision,
        updated_at=_timestamp(updated_at),
        source_url=source_url,
        owner=owner,
        service=service,
        acl=acl,
    )


def deployment_record(raw: Mapping[str, object], *, acl: ACL) -> KnowledgeDocument:
    deployment_id = str(raw.get("id") or "")
    if not deployment_id:
        raise ValueError("deployment id is required")
    service = str(raw.get("service") or "") or None
    commit = str(raw.get("commit_sha") or "unknown")
    environment = str(raw.get("environment") or "unknown")
    status = str(raw.get("status") or "unknown")
    body = (
        f"Deployment {deployment_id}\nService: {service or 'unknown'}\n"
        f"Environment: {environment}\nCommit: {commit}\nStatus: {status}"
    )
    return KnowledgeDocument(
        identity=KnowledgeIdentity(
            "cicd", KnowledgeSourceType.DEPLOYMENT, deployment_id
        ),
        title=f"Deployment {deployment_id} — {service or 'unknown'}",
        body=body,
        revision=str(raw.get("revision") or commit),
        updated_at=_timestamp(raw.get("timestamp")),
        source_url=str(raw.get("url") or "") or None,
        service=service,
        acl=acl,
        metadata={"environment": environment, "commit_sha": commit, "status": status},
    )
