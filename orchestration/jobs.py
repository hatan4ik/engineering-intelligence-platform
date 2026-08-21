from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Job:
    job_id: str
    workflow_id: str
    kind: str
    payload: Mapping[str, object]
    status: str
    attempts: int
    max_attempts: int
    not_before: float
    lease_until: float | None
    last_error: str | None = None


class SqliteJobQueue:
    """Durable local/CI queue with lease-based claiming and DLQ semantics."""

    def __init__(self, path: str | Path = "eip-jobs.db") -> None:
        self.path = str(path)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    not_before REAL NOT NULL,
                    lease_until REAL,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_claim
                  ON jobs(status, not_before, lease_until);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def enqueue(
        self,
        *,
        job_id: str,
        workflow_id: str,
        kind: str,
        payload: Mapping[str, object],
        max_attempts: int = 5,
        not_before: float | None = None,
    ) -> bool:
        with self._connect() as db:
            cur = db.execute(
                """INSERT OR IGNORE INTO jobs(
                       job_id, workflow_id, kind, payload, status, attempts,
                       max_attempts, not_before, lease_until, last_error
                   ) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, NULL, NULL)""",
                (
                    job_id,
                    workflow_id,
                    kind,
                    json.dumps(dict(payload), sort_keys=True, default=str),
                    max_attempts,
                    time.time() if not_before is None else not_before,
                ),
            )
            return cur.rowcount == 1

    def claim(self, *, lease_seconds: int = 60, now: float | None = None) -> Job | None:
        current = time.time() if now is None else now
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM jobs
                   WHERE status IN ('queued', 'leased')
                     AND not_before <= ?
                     AND (status='queued' OR lease_until IS NULL OR lease_until <= ?)
                   ORDER BY not_before, job_id
                   LIMIT 1""",
                (current, current),
            ).fetchone()
            if row is None:
                db.commit()
                return None
            lease_until = current + lease_seconds
            attempts = int(row["attempts"]) + 1
            db.execute(
                """UPDATE jobs
                   SET status='leased', attempts=?, lease_until=?
                   WHERE job_id=?""",
                (attempts, lease_until, row["job_id"]),
            )
            db.commit()
        return self.get(str(row["job_id"]))

    def complete(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status='completed', lease_until=NULL, last_error=NULL WHERE job_id=?",
                (job_id,),
            )

    def fail(
        self,
        job_id: str,
        error: Exception,
        *,
        base_backoff_seconds: float = 5.0,
        now: float | None = None,
    ) -> Job:
        current = time.time() if now is None else now
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        message = f"{type(error).__name__}: {error}"
        if job.attempts >= job.max_attempts:
            status = "dead_letter"
            not_before = current
        else:
            status = "queued"
            not_before = current + base_backoff_seconds * (2 ** max(0, job.attempts - 1))
        with self._connect() as db:
            db.execute(
                """UPDATE jobs
                   SET status=?, not_before=?, lease_until=NULL, last_error=?
                   WHERE job_id=?""",
                (status, not_before, message, job_id),
            )
        updated = self.get(job_id)
        assert updated is not None
        return updated

    def get(self, job_id: str) -> Job | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return Job(
            job_id=str(row["job_id"]),
            workflow_id=str(row["workflow_id"]),
            kind=str(row["kind"]),
            payload=json.loads(row["payload"]),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            not_before=float(row["not_before"]),
            lease_until=float(row["lease_until"]) if row["lease_until"] is not None else None,
            last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        )
