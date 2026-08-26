from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .documents import KnowledgeChange, KnowledgeDocument
from .models import ChangeType

if TYPE_CHECKING:
    from company_brain.memory import CompanyBrainMemoryProjector


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    document_id: str
    content: str
    ordinal: int
    title: str
    provider: str
    source_type: str
    revision: str
    updated_at: str
    source_url: str | None
    owner: str | None
    service: str | None
    acl_groups: tuple[str, ...]
    acl_users: tuple[str, ...]
    content_hash: str

    def as_index_document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": self.content,
            "ordinal": self.ordinal,
            "title": self.title,
            "provider": self.provider,
            "source_type": self.source_type,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "source_url": self.source_url,
            "owner": self.owner,
            "service": self.service,
            "acl_groups": list(self.acl_groups),
            "acl_users": list(self.acl_users),
            "content_hash": self.content_hash,
        }


class KnowledgeIndex(Protocol):
    def current_revision(self, document_id: str) -> str | None: ...
    def replace_document(self, document_id: str, revision: str, chunks: list[KnowledgeChunk]) -> None: ...
    def delete_document(self, document_id: str) -> None: ...


class InMemoryKnowledgeIndex:
    def __init__(self) -> None:
        self.revisions: dict[str, str] = {}
        self.chunks: dict[str, list[KnowledgeChunk]] = {}

    def current_revision(self, document_id: str) -> str | None:
        return self.revisions.get(document_id)

    def replace_document(self, document_id: str, revision: str, chunks: list[KnowledgeChunk]) -> None:
        self.revisions[document_id] = revision
        self.chunks[document_id] = list(chunks)

    def delete_document(self, document_id: str) -> None:
        self.revisions.pop(document_id, None)
        self.chunks.pop(document_id, None)


def chunk_document(document: KnowledgeDocument, *, max_chars: int = 1400) -> list[KnowledgeChunk]:
    sections = [s.strip() for s in re.split(r"\n(?=#{1,6}\s)|\n{2,}", document.body) if s.strip()]
    pieces: list[str] = []
    for section in sections or [document.body]:
        if len(section) <= max_chars:
            pieces.append(section)
            continue
        start = 0
        while start < len(section):
            pieces.append(section[start:start + max_chars].strip())
            start += max_chars
    document_id = document.identity.document_id
    chunks: list[KnowledgeChunk] = []
    for ordinal, piece in enumerate(p for p in pieces if p):
        chunks.append(
            KnowledgeChunk(
                id=f"{document_id}:{document.revision}:{ordinal}",
                document_id=document_id,
                content=piece,
                ordinal=ordinal,
                title=document.title,
                provider=document.identity.provider,
                source_type=document.identity.source_type.value,
                revision=document.revision,
                updated_at=document.updated_at.isoformat(),
                source_url=document.source_url,
                owner=document.owner,
                service=document.service,
                acl_groups=document.acl.groups,
                acl_users=document.acl.users,
                content_hash=document.content_hash,
            )
        )
    return chunks


@dataclass
class KnowledgePipeline:
    index: KnowledgeIndex
    brain_memory_projector: CompanyBrainMemoryProjector | None = None

    def process(self, change: KnowledgeChange, *, event_id: str | None = None) -> dict[str, object]:
        document = change.document
        document_id = document.identity.document_id
        if change.change_type is ChangeType.DELETE:
            self.index.delete_document(document_id)
            if self.brain_memory_projector is not None:
                self.brain_memory_projector.project_knowledge_change(change, event_id=event_id)
            return {"status": "deleted", "document_id": document_id, "chunks": 0}

        current = self.index.current_revision(document_id)
        if current == document.revision:
            if self.brain_memory_projector is not None:
                self.brain_memory_projector.project_knowledge_change(change, event_id=event_id)
            return {"status": "duplicate", "document_id": document_id, "chunks": 0}

        chunks = chunk_document(document)
        self.index.replace_document(document_id, document.revision, chunks)
        if self.brain_memory_projector is not None:
            self.brain_memory_projector.project_knowledge_change(change, event_id=event_id)
        return {"status": "indexed", "document_id": document_id, "revision": document.revision, "chunks": len(chunks)}
