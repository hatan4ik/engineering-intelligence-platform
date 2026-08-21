from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import ACL, FileChange


class ACLResolver(Protocol):
    def resolve(self, provider: str, repository: str) -> ACL: ...


class StaticACLResolver:
    """Deterministic resolver used for local tests and bootstrap environments."""

    def __init__(self, mapping: dict[str, ACL] | None = None) -> None:
        self.mapping = mapping or {}

    def resolve(self, provider: str, repository: str) -> ACL:
        key = f"{provider}:{repository}"
        return self.mapping.get(key, ACL(groups=(f"repo:{repository}:read",)))


def apply_resolved_acl(change: FileChange, resolver: ACLResolver) -> FileChange:
    return replace(change, acl=resolver.resolve(change.source.provider, change.source.repository))
