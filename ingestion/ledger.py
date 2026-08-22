from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .events import NormalizedEvent


class SqliteEventLedger:
    """Durable idempotency ledger + DLQ for local/single-worker deployments."""

    def __init__(self, path: str | Path = "ingestion-ledger.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS dlq (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def seen(self, event_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT status FROM events WHERE event_id=?", (event_id,)).fetchone()
        return bool(row and row[0] == "completed")

    def start(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO events(event_id, status, attempts, updated_at)
                   VALUES (?, 'processing', 1, ?)
                   ON CONFLICT(event_id) DO UPDATE SET
                     status='processing', attempts=attempts+1, updated_at=excluded.updated_at""",
                (event_id, now),
            )

    def complete(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                "UPDATE events SET status='completed', updated_at=?, last_error=NULL WHERE event_id=?",
                (now, event_id),
            )
            db.execute("DELETE FROM dlq WHERE event_id=?", (event_id,))

    def fail(self, event: NormalizedEvent, error: Exception) -> None:
        now = datetime.now(timezone.utc).isoformat()
        message = f"{type(error).__name__}: {error}"
        payload = json.dumps(asdict(event), sort_keys=True, default=str)
        with self._connect() as db:
            db.execute(
                "UPDATE events SET status='failed', updated_at=?, last_error=? WHERE event_id=?",
                (now, message, event.event_id),
            )
            db.execute(
                """INSERT INTO dlq(event_id, payload, error, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(event_id) DO UPDATE SET
                     payload=excluded.payload, error=excluded.error, created_at=excluded.created_at""",
                (event.event_id, payload, message, now),
            )

    def dlq_events(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT event_id, payload, error, created_at FROM dlq ORDER BY created_at"
            ).fetchall()
        return [
            {"event_id": r[0], "payload": r[1], "error": r[2], "created_at": r[3]}
            for r in rows
        ]

    def remove_from_dlq(self, event_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM dlq WHERE event_id=?", (event_id,))
