from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChangeType(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"


@dataclass(frozen=True)
class SourceIdentity:
    provider: str
    repository: str
    branch: str
    commit_sha: str
    path: str

    @property
    def document_id(self) -> str:
        return f"{self.provider}:{self.repository}:{self.branch}:{self.path}"


@dataclass(frozen=True)
class ACL:
    groups: tuple[str, ...] = ()
    users: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileChange:
    source: SourceIdentity
    change_type: ChangeType
    content: str | None = None
    language: str | None = None
    owner: str | None = None
    service: str | None = None
    acl: ACL = field(default_factory=ACL)


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    source: SourceIdentity
    content: str
    ordinal: int
    symbol: str | None = None
    language: str | None = None
    owner: str | None = None
    service: str | None = None
    acl: ACL = field(default_factory=ACL)
    embedding: tuple[float, ...] = ()
    content_hash: str | None = None

    def as_index_document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "provider": self.source.provider,
            "repository": self.source.repository,
            "branch": self.source.branch,
            "commit_sha": self.source.commit_sha,
            "path": self.source.path,
            "content": self.content,
            "ordinal": self.ordinal,
            "symbol": self.symbol,
            "language": self.language,
            "owner": self.owner,
            "service": self.service,
            "acl_groups": list(self.acl.groups),
            "acl_users": list(self.acl.users),
            "embedding": list(self.embedding),
            "content_hash": self.content_hash,
        }
