from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterator, Protocol

from .models import ServiceRecord, WorkflowRecord, WorkflowStatus


class VersionConflict(RuntimeError):
    pass


class StateStore(Protocol):
    def get_service(self, service_id: str) -> ServiceRecord | None: ...
    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord: ...
    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None: ...
    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord: ...


class SqliteStateStore:
    """Authoritative local state store with real compare-and-swap concurrency.

    Each ``put_*`` reads the current version and writes the next version inside a
    single ``BEGIN IMMEDIATE`` transaction, so two racing writers cannot both
    observe the same version and both succeed (lost update). The production
    adapter must preserve these compare-and-swap semantics; Azure AI Search must
    never be used as the system of record for these objects.
    """

    def __init__(self, path: str | Path = "eip-state.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None → autocommit, so we control transactions explicitly.
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @contextmanager
    def _immediate(self, db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

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

    @staticmethod
    def _row_to_service(row: sqlite3.Row) -> ServiceRecord:
        raw = json.loads(row["payload"])
        raw["repositories"] = tuple(raw.get("repositories", ()))
        raw["dependencies"] = tuple(raw.get("dependencies", ()))
        return ServiceRecord(**raw)

    @staticmethod
    def _row_to_workflow(row: sqlite3.Row) -> WorkflowRecord:
        raw = json.loads(row["payload"])
        raw["status"] = WorkflowStatus(raw["status"])
        return WorkflowRecord(**raw)

    def get_service(self, service_id: str) -> ServiceRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM services WHERE service_id=?", (service_id,)).fetchone()
        return self._row_to_service(row) if row else None

    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord:
        with self._connect() as db, self._immediate(db):
            row = db.execute(
                "SELECT version FROM services WHERE service_id=?", (record.service_id,)
            ).fetchone()
            current = int(row["version"]) if row else None
            self._assert_expected(current, expected_version)
            next_version = 1 if current is None else current + 1
            stored = replace(record, version=next_version)
            db.execute(
                """INSERT INTO services(service_id, payload, version) VALUES (?, ?, ?)
                   ON CONFLICT(service_id) DO UPDATE SET payload=excluded.payload, version=excluded.version""",
                (stored.service_id, json.dumps(asdict(stored), sort_keys=True), stored.version),
            )
        return stored

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        return self._row_to_workflow(row) if row else None

    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord:
        with self._connect() as db, self._immediate(db):
            row = db.execute(
                "SELECT version FROM workflows WHERE workflow_id=?", (record.workflow_id,)
            ).fetchone()
            current = int(row["version"]) if row else None
            self._assert_expected(current, expected_version)
            next_version = 1 if current is None else current + 1
            stored = replace(record, version=next_version)
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
