from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping

from .models import ACL, ChangeType


class KnowledgeSourceType(StrEnum):
    WORK_ITEM = "work_item"
    DOCUMENTATION = "documentation"
    ADR = "adr"
    RUNBOOK = "runbook"
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class KnowledgeIdentity:
    provider: str
    source_type: KnowledgeSourceType
    source_id: str

    @property
    def document_id(self) -> str:
        return f"knowledge:{self.provider}:{self.source_type.value}:{self.source_id}"


@dataclass(frozen=True)
class KnowledgeDocument:
    identity: KnowledgeIdentity
    title: str
    body: str
    revision: str
    updated_at: datetime
    source_url: str | None = None
    owner: str | None = None
    service: str | None = None
    acl: ACL = field(default_factory=ACL)
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()

    @property
    def age_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        ts = self.updated_at if self.updated_at.tzinfo else self.updated_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts.astimezone(timezone.utc)).total_seconds())


@dataclass(frozen=True)
class KnowledgeChange:
    change_type: ChangeType
    document: KnowledgeDocument
