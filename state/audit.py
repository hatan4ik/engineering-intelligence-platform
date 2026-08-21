from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from .models import AuditEvent


def _canonical(event: AuditEvent) -> str:
    payload = asdict(event)
    payload["event_hash"] = None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event).encode()).hexdigest()


class SqliteAuditLog:
    """Append-only hash-chained audit log for local/test use.

    The production sink should additionally use immutable/WORM storage, but the
    same event contract and chain verification remain useful end-to-end.
    """

    def __init__(self, path: str | Path = "eip-audit.db") -> None:
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
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def append(self, event: AuditEvent) -> AuditEvent:
        previous = self.last_hash()
        candidate = replace(event, previous_hash=previous, event_hash=None)
        finalized = replace(candidate, event_hash=compute_event_hash(candidate))
        with self._connect() as db:
            db.execute(
                "INSERT INTO audit_events(event_id, payload, event_hash) VALUES (?, ?, ?)",
                (finalized.event_id, json.dumps(asdict(finalized), sort_keys=True, default=str), finalized.event_hash),
            )
        return finalized

    def last_hash(self) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        return row["event_hash"] if row else None

    def verify_chain(self) -> bool:
        previous: str | None = None
        with self._connect() as db:
            rows = db.execute("SELECT payload, event_hash FROM audit_events ORDER BY sequence").fetchall()
        for row in rows:
            raw = json.loads(row["payload"])
            event = AuditEvent(**raw)
            if event.previous_hash != previous:
                return False
            if compute_event_hash(replace(event, event_hash=None)) != row["event_hash"]:
                return False
            previous = row["event_hash"]
        return True
