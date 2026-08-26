from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterator, Protocol

from control_plane.runtime import require_reference_storage
from .lifecycle import LifecycleContractError, WorkflowLifecycleEvent, WorkflowTransitionResult
from .models import ServiceRecord, WorkflowRecord, WorkflowStatus


class VersionConflict(RuntimeError):
    pass


class StateStore(Protocol):
    def get_service(self, service_id: str) -> ServiceRecord | None: ...
    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord: ...
    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None: ...
    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord: ...
    def apply_workflow_event(self, event: WorkflowLifecycleEvent) -> WorkflowTransitionResult: ...


class SqliteStateStore:
    """Authoritative local state store with real compare-and-swap concurrency.

    Each ``put_*`` reads the current version and writes the next version inside a
    single ``BEGIN IMMEDIATE`` transaction, so two racing writers cannot both
    observe the same version and both succeed (lost update). The production
    adapter must preserve these compare-and-swap semantics; Azure AI Search must
    never be used as the system of record for these objects.
    """

    def __init__(self, path: str | Path = "eip-state.db") -> None:
        require_reference_storage(type(self).__name__)
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
                CREATE TABLE IF NOT EXISTS workflow_transition_receipts (
                    workflow_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_fingerprint TEXT NOT NULL,
                    workflow_payload TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, idempotency_key),
                    UNIQUE (workflow_id, event_id)
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
            self._write_workflow(db, stored)
        return stored

    def apply_workflow_event(self, event: WorkflowLifecycleEvent) -> WorkflowTransitionResult:
        """Atomically persist a transition and its durable idempotency receipt.

        A retry first resolves the receipt. This makes a state-success/audit-
        failure retry return the original record instead of incrementing its
        version again.
        """
        event.validate()
        with self._connect() as db, self._immediate(db):
            receipt = db.execute(
                """SELECT event_id, event_fingerprint, workflow_payload
                   FROM workflow_transition_receipts
                   WHERE workflow_id=? AND idempotency_key=?""",
                (event.workflow_id, event.idempotency_key),
            ).fetchone()
            if receipt is not None:
                return self._replayed_transition(event, receipt)

            same_event = db.execute(
                """SELECT idempotency_key FROM workflow_transition_receipts
                   WHERE workflow_id=? AND event_id=?""",
                (event.workflow_id, event.event_id),
            ).fetchone()
            if same_event is not None:
                raise VersionConflict("workflow event id has already been used with a different idempotency key")

            row = db.execute(
                "SELECT payload, version FROM workflows WHERE workflow_id=?", (event.workflow_id,)
            ).fetchone()
            current = self._row_to_workflow(row) if row else None
            self._assert_expected(current.version if current else None, event.expected_version)
            try:
                candidate = event.apply_to(current)
            except LifecycleContractError as exc:
                raise VersionConflict(str(exc)) from exc
            stored = replace(candidate, version=1 if current is None else current.version + 1)
            self._write_workflow(db, stored)
            db.execute(
                """INSERT INTO workflow_transition_receipts(
                       workflow_id, idempotency_key, event_id, event_fingerprint, workflow_payload
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    event.workflow_id,
                    event.idempotency_key,
                    event.event_id,
                    event.fingerprint,
                    json.dumps(asdict(stored), sort_keys=True),
                ),
            )
        return WorkflowTransitionResult(
            record=stored,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
        )

    @staticmethod
    def _write_workflow(db: sqlite3.Connection, record: WorkflowRecord) -> None:
        db.execute(
            """INSERT INTO workflows(workflow_id, payload, version) VALUES (?, ?, ?)
               ON CONFLICT(workflow_id) DO UPDATE SET payload=excluded.payload, version=excluded.version""",
            (record.workflow_id, json.dumps(asdict(record), sort_keys=True), record.version),
        )

    @classmethod
    def _replayed_transition(
        cls, event: WorkflowLifecycleEvent, receipt: sqlite3.Row
    ) -> WorkflowTransitionResult:
        if receipt["event_id"] != event.event_id or receipt["event_fingerprint"] != event.fingerprint:
            raise VersionConflict("idempotency key has already been used for a different workflow event")
        return WorkflowTransitionResult(
            record=cls._payload_to_workflow(str(receipt["workflow_payload"])),
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            replayed=True,
        )

    @staticmethod
    def _payload_to_workflow(payload: str) -> WorkflowRecord:
        raw = json.loads(payload)
        raw["status"] = WorkflowStatus(raw["status"])
        return WorkflowRecord(**raw)

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise VersionConflict(f"expected version {expected}, current version is {current}")
