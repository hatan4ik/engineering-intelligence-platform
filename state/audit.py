from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

from control_plane.runtime import require_reference_storage
from .models import AuditEvent


def _canonical(event: AuditEvent) -> str:
    payload = asdict(event)
    payload["event_hash"] = None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event).encode()).hexdigest()


def _event_identity(event: AuditEvent) -> str:
    """Stable content used to make at-least-once audit export idempotent."""
    payload = asdict(event)
    payload["previous_hash"] = None
    payload["event_hash"] = None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class AuditConflict(RuntimeError):
    """An audit event ID was reused for different content."""


class AuditLog(Protocol):
    """Append-only, idempotent audit contract shared by reference and managed sinks."""

    def append(self, event: AuditEvent) -> AuditEvent: ...


class SqliteAuditLog:
    """Append-only hash-chained audit log for local/test use.

    The production sink should additionally use immutable/WORM storage, but the
    same event contract and chain verification remain useful end-to-end.
    """

    def __init__(self, path: str | Path = "eip-audit.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None → autocommit, so BEGIN IMMEDIATE controls the txn.
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def append(self, event: AuditEvent) -> AuditEvent:
        # Read the chain tip and append inside one write transaction so two
        # concurrent appenders cannot both link to the same predecessor and
        # fork the chain. The write lock is held from the tip read to commit.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                tip = db.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous = tip["event_hash"] if tip else None
                candidate = replace(event, previous_hash=previous, event_hash=None)
                finalized = replace(candidate, event_hash=compute_event_hash(candidate))
                db.execute(
                    "INSERT INTO audit_events(event_id, payload, event_hash) VALUES (?, ?, ?)",
                    (
                        finalized.event_id,
                        json.dumps(asdict(finalized), sort_keys=True, default=str),
                        finalized.event_hash,
                    ),
                )
                db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                db.execute("ROLLBACK")
                existing = db.execute(
                    "SELECT payload FROM audit_events WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if existing is None:
                    raise
                restored = AuditEvent(**json.loads(existing["payload"]))
                if _event_identity(restored) != _event_identity(event):
                    raise AuditConflict("audit event id has already been used for different content") from exc
                return restored
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return finalized

    def event_count(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COUNT(*) AS total FROM audit_events").fetchone()
        return int(row["total"])

    def last_hash(self) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        return row["event_hash"] if row else None

    def verify_chain(self) -> bool:
        previous: str | None = None
        with self._connect() as db:
            rows = db.execute("SELECT payload, event_hash FROM audit_events ORDER BY sequence").fetchall()
        try:
            for row in rows:
                raw = json.loads(row["payload"])
                event = AuditEvent(**raw)
                if event.previous_hash != previous:
                    return False
                if compute_event_hash(replace(event, event_hash=None)) != row["event_hash"]:
                    return False
                previous = row["event_hash"]
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return False
        return True
