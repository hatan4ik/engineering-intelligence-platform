"""Durable source-lifecycle catalog for governed incremental ingestion."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .models import FileChange, SourceIdentity


@dataclass(frozen=True)
class SourceScope:
    provider: str
    repository: str
    branch: str


@dataclass(frozen=True)
class SourceRecord:
    source: SourceIdentity
    fingerprint: str
    state: str
    updated_at: str
    last_event_id: str | None = None


class SourceCatalog(Protocol):
    def get(self, document_id: str) -> SourceRecord | None: ...
    def needs_upsert(self, change: FileChange) -> bool: ...
    def record_upsert(self, change: FileChange, *, event_id: str | None = None) -> SourceRecord: ...
    def record_delete(self, change: FileChange, *, event_id: str | None = None) -> SourceRecord: ...
    def active_in_scope(self, scope: SourceScope) -> list[SourceRecord]: ...


def change_fingerprint(change: FileChange) -> str:
    """Hash every source attribute that changes indexed evidence or access."""
    payload = {
        "provider": change.source.provider,
        "repository": change.source.repository,
        "branch": change.source.branch,
        "commit_sha": change.source.commit_sha,
        "path": change.source.path,
        "content": change.content or "",
        "language": change.language,
        "owner": change.owner,
        "service": change.service,
        "acl_groups": sorted(set(change.acl.groups)),
        "acl_users": sorted(set(change.acl.users)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


class SqliteSourceCatalog:
    """Reference durable catalog; source state is separate from retrieval indexes."""

    def __init__(self, path: str | Path = "ingestion-sources.db") -> None:
        self.path = str(path)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS source_documents (
                    document_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    path TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_event_id TEXT
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS idx_source_documents_scope
                   ON source_documents(provider, repository, branch, state)"""
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def get(self, document_id: str) -> SourceRecord | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT document_id, provider, repository, branch, commit_sha, path,
                          fingerprint, state, updated_at, last_event_id
                   FROM source_documents WHERE document_id=?""",
                (document_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def needs_upsert(self, change: FileChange) -> bool:
        current = self.get(change.source.document_id)
        return current is None or current.state != "active" or current.fingerprint != change_fingerprint(change)

    def record_upsert(self, change: FileChange, *, event_id: str | None = None) -> SourceRecord:
        return self._record(change, fingerprint=change_fingerprint(change), state="active", event_id=event_id)

    def record_delete(self, change: FileChange, *, event_id: str | None = None) -> SourceRecord:
        return self._record(change, fingerprint=change_fingerprint(change), state="deleted", event_id=event_id)

    def active_in_scope(self, scope: SourceScope) -> list[SourceRecord]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT document_id, provider, repository, branch, commit_sha, path,
                          fingerprint, state, updated_at, last_event_id
                   FROM source_documents
                   WHERE provider=? AND repository=? AND branch=? AND state='active'
                   ORDER BY path""",
                (scope.provider, scope.repository, scope.branch),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _record(self, change: FileChange, *, fingerprint: str, state: str, event_id: str | None) -> SourceRecord:
        source = change.source
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO source_documents(
                       document_id, provider, repository, branch, commit_sha, path,
                       fingerprint, state, updated_at, last_event_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(document_id) DO UPDATE SET
                       provider=excluded.provider, repository=excluded.repository,
                       branch=excluded.branch, commit_sha=excluded.commit_sha,
                       path=excluded.path, fingerprint=excluded.fingerprint,
                       state=excluded.state, updated_at=excluded.updated_at,
                       last_event_id=excluded.last_event_id""",
                (
                    source.document_id,
                    source.provider,
                    source.repository,
                    source.branch,
                    source.commit_sha,
                    source.path,
                    fingerprint,
                    state,
                    updated_at,
                    event_id,
                ),
            )
        return SourceRecord(source, fingerprint, state, updated_at, event_id)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source=SourceIdentity(
                provider=str(row["provider"]),
                repository=str(row["repository"]),
                branch=str(row["branch"]),
                commit_sha=str(row["commit_sha"]),
                path=str(row["path"]),
            ),
            fingerprint=str(row["fingerprint"]),
            state=str(row["state"]),
            updated_at=str(row["updated_at"]),
            last_event_id=str(row["last_event_id"]) if row["last_event_id"] is not None else None,
        )
