from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

from .models import ServiceRecord, WorkflowRecord, WorkflowStatus


class VersionConflict(RuntimeError):
    pass


class StateStore(Protocol):
    def get_service(self, service_id: str) -> ServiceRecord | None: ...
    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord: ...
    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None: ...
    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord: ...


class SqliteStateStore:
    """Authoritative local state store with optimistic concurrency.

    The production adapter must preserve the same compare-and-swap semantics.
    Azure AI Search must never be used as the system of record for these objects.
    """

    def __init__(self, path: str | Path = "eip-state.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS services (
                    service_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
                """
            )

    def get_service(self, service_id: str) -> ServiceRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM services WHERE service_id=?", (service_id,)).fetchone()
        if not row:
            return None
        raw = json.loads(row["payload"])
        raw["repositories"] = tuple(raw.get("repositories", ()))
        raw["dependencies"] = tuple(raw.get("dependencies", ()))
        return ServiceRecord(**raw)

    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord:
        current = self.get_service(record.service_id)
        self._assert_expected(current.version if current else None, expected_version)
        next_version = 1 if current is None else current.version + 1
        stored = replace(record, version=next_version)
        with self._connect() as db:
            db.execute(
                """INSERT INTO services(service_id, payload, version) VALUES (?, ?, ?)
                   ON CONFLICT(service_id) DO UPDATE SET payload=excluded.payload, version=excluded.version""",
                (stored.service_id, json.dumps(asdict(stored), sort_keys=True), stored.version),
            )
        return stored

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        if not row:
            return None
        raw = json.loads(row["payload"])
        raw["status"] = WorkflowStatus(raw["status"])
        return WorkflowRecord(**raw)

    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord:
        current = self.get_workflow(record.workflow_id)
        self._assert_expected(current.version if current else None, expected_version)
        next_version = 1 if current is None else current.version + 1
        stored = replace(record, version=next_version)
        with self._connect() as db:
            db.execute(
                """INSERT INTO workflows(workflow_id, payload, version) VALUES (?, ?, ?)
                   ON CONFLICT(workflow_id) DO UPDATE SET payload=excluded.payload, version=excluded.version""",
                (stored.workflow_id, json.dumps(asdict(stored), sort_keys=True), stored.version),
            )
        return stored

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise VersionConflict(f"expected version {expected}, current version is {current}")
