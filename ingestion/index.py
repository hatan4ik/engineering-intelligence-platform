from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import Chunk


class Index(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
    def search(self, query: str, groups: list[str], users: list[str] | None = None) -> list[dict[str, object]]: ...


@dataclass
class InMemoryIndex:
    documents: dict[str, list[Chunk]] = field(default_factory=dict)

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        self.documents[document_id] = list(chunks)

    def delete_document(self, document_id: str) -> None:
        self.documents.pop(document_id, None)

    def search(self, query: str, groups: list[str], users: list[str] | None = None) -> list[dict[str, object]]:
        users = users or []
        q = query.lower()
        out: list[dict[str, object]] = []
        for chunks in self.documents.values():
            for chunk in chunks:
                if chunk.acl.groups and not set(groups).intersection(chunk.acl.groups):
                    continue
                if chunk.acl.users and not set(users).intersection(chunk.acl.users):
                    continue
                if q in chunk.content.lower() or any(token in chunk.content.lower() for token in q.split()):
                    out.append(chunk.as_index_document())
        return out
