from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
import re
from typing import Iterable, Mapping, Protocol

from .documents import KnowledgeDocument, KnowledgeIdentity, KnowledgeSourceType
from .knowledge_normalizers import _timestamp, azure_devops_work_item, documentation_page
from .models import ACL


class JsonTransport(Protocol):
    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class SourcePage:
    documents: tuple[KnowledgeDocument, ...]
    next_url: str | None = None


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class AzureDevOpsBoardsAdapter:
    transport: JsonTransport
    organization_url: str
    project: str
    acl: ACL

    def fetch_work_items(self, ids: Iterable[int]) -> SourcePage:
        ids_csv = ",".join(str(i) for i in ids)
        if not ids_csv:
            return SourcePage(())
        url = (
            f"{self.organization_url.rstrip('/')}/{self.project}/_apis/wit/workitems"
            f"?ids={ids_csv}&$expand=relations&api-version=7.1"
        )
        payload = self.transport.get_json(url)
        raw_items = payload.get("value") or []
        docs = tuple(
            azure_devops_work_item(item, acl=self.acl)
            for item in raw_items
            if isinstance(item, Mapping)
        )
        return SourcePage(docs)


@dataclass
class JiraAdapter:
    transport: JsonTransport
    base_url: str
    acl: ACL

    def search(self, *, jql: str, next_page_token: str | None = None, max_results: int = 100) -> SourcePage:
        params = f"jql={jql}&maxResults={max_results}"
        if next_page_token:
            params += f"&nextPageToken={next_page_token}"
        url = f"{self.base_url.rstrip('/')}/rest/api/3/search/jql?{params}"
        payload = self.transport.get_json(url)
        docs: list[KnowledgeDocument] = []
        for issue in payload.get("issues") or []:
            if not isinstance(issue, Mapping):
                continue
            fields = issue.get("fields") or {}
            if not isinstance(fields, Mapping):
                continue
            key = str(issue.get("key") or issue.get("id") or "")
            if not key:
                continue
            summary = str(fields.get("summary") or key)
            description = fields.get("description")
            if isinstance(description, Mapping):
                description_text = _extract_atlassian_text(description)
            else:
                description_text = str(description or "")
            assignee = fields.get("assignee") or {}
            assignee_name = str(assignee.get("displayName") or "") if isinstance(assignee, Mapping) else ""
            project = fields.get("project") or {}
            project_key = str(project.get("key") or "") if isinstance(project, Mapping) else ""
            status = fields.get("status") or {}
            status_name = str(status.get("name") or "") if isinstance(status, Mapping) else ""
            body = f"Title: {summary}\nStatus: {status_name}\nProject: {project_key}\n\n{description_text}".strip()
            docs.append(KnowledgeDocument(
                identity=KnowledgeIdentity("jira", KnowledgeSourceType.WORK_ITEM, key),
                title=summary,
                body=body,
                revision=str(fields.get("updated") or issue.get("id") or "1"),
                updated_at=_timestamp(fields.get("updated")),
                source_url=f"{self.base_url.rstrip('/')}/browse/{key}",
                owner=assignee_name or None,
                service=_label_value(fields.get("labels"), "service:"),
                acl=self.acl,
                metadata={"status": status_name, "project": project_key},
            ))
        next_token = payload.get("nextPageToken")
        next_url = str(next_token) if next_token else None
        return SourcePage(tuple(docs), next_url)


@dataclass
class ConfluenceAdapter:
    transport: JsonTransport
    base_url: str
    acl: ACL

    def pages(self, *, space_id: str, cursor: str | None = None, limit: int = 100) -> SourcePage:
        url = f"{self.base_url.rstrip('/')}/wiki/api/v2/spaces/{space_id}/pages?limit={limit}&body-format=storage"
        if cursor:
            url += f"&cursor={cursor}"
        payload = self.transport.get_json(url)
        docs: list[KnowledgeDocument] = []
        for page in payload.get("results") or []:
            if not isinstance(page, Mapping):
                continue
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            body = page.get("body") or {}
            storage = body.get("storage") or {} if isinstance(body, Mapping) else {}
            value = str(storage.get("value") or "") if isinstance(storage, Mapping) else ""
            version = page.get("version") or {}
            updated_at = version.get("createdAt") if isinstance(version, Mapping) else None
            docs.append(documentation_page(
                provider="confluence",
                page_id=page_id,
                title=str(page.get("title") or page_id),
                body=_strip_html(value),
                revision=str(version.get("number") or "1") if isinstance(version, Mapping) else "1",
                updated_at=updated_at or datetime.utcnow().isoformat(),
                acl=self.acl,
                source_url=f"{self.base_url.rstrip('/')}/wiki/spaces/{space_id}/pages/{page_id}",
                source_type=_confluence_source_type(str(page.get("title") or "")),
            ))
        links = payload.get("_links") or {}
        next_link = str(links.get("next") or "") if isinstance(links, Mapping) else ""
        return SourcePage(tuple(docs), next_link or None)


@dataclass(frozen=True)
class ConversationIngestionPolicy:
    allowed_channels: tuple[str, ...]
    require_explicit_knowledge_marker: bool = True
    marker: str = "#decision"

    def allows(self, *, channel: str, text: str) -> bool:
        if channel not in self.allowed_channels:
            return False
        return not self.require_explicit_knowledge_marker or self.marker.lower() in text.lower()


def governed_conversation_document(
    *,
    provider: str,
    conversation_id: str,
    channel: str,
    author: str,
    text: str,
    updated_at: str | datetime,
    revision: str,
    acl: ACL,
    policy: ConversationIngestionPolicy,
    source_url: str | None = None,
) -> KnowledgeDocument | None:
    if not policy.allows(channel=channel, text=text):
        return None
    return KnowledgeDocument(
        identity=KnowledgeIdentity(provider, KnowledgeSourceType.CONVERSATION, conversation_id),
        title=f"Decision in {channel}",
        body=text.strip(),
        revision=revision,
        updated_at=_timestamp(updated_at),
        source_url=source_url,
        owner=author or None,
        acl=acl,
        metadata={"channel": channel, "governance": "explicit-marker"},
    )


def _extract_atlassian_text(node: object) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, Mapping):
        own = str(node.get("text") or "")
        children = node.get("content") or []
        return " ".join(p for p in [own, *(_extract_atlassian_text(c) for c in children)] if p).strip()
    if isinstance(node, list):
        return " ".join(_extract_atlassian_text(c) for c in node).strip()
    return ""


def _label_value(raw: object, prefix: str) -> str | None:
    if not isinstance(raw, list):
        return None
    for value in raw:
        text = str(value)
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):] or None
    return None


def _confluence_source_type(title: str) -> KnowledgeSourceType:
    lowered = title.lower()
    if lowered.startswith("adr-") or lowered.startswith("adr "):
        return KnowledgeSourceType.ADR
    if "runbook" in lowered:
        return KnowledgeSourceType.RUNBOOK
    if "incident" in lowered or "postmortem" in lowered:
        return KnowledgeSourceType.INCIDENT
    return KnowledgeSourceType.DOCUMENTATION
