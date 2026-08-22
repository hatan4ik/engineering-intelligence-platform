from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Mapping


class FeedbackOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVERTED = "reverted"
    CORRECT = "correct"
    INCORRECT = "incorrect"


@dataclass(frozen=True)
class FeedbackEvent:
    event_id: str
    capability: str
    subject_id: str
    outcome: FeedbackOutcome
    service: str | None = None
    actor: str | None = None
    metadata: Mapping[str, str] | None = None
    occurred_at: str = ""

    def normalized(self) -> "FeedbackEvent":
        return FeedbackEvent(
            event_id=self.event_id,
            capability=self.capability,
            subject_id=self.subject_id,
            outcome=self.outcome,
            service=self.service,
            actor=self.actor,
            metadata=dict(self.metadata or {}),
            occurred_at=self.occurred_at or datetime.now(timezone.utc).isoformat(),
        )


class SqliteFeedbackStore:
    def __init__(self, path: str | Path = "eip-feedback.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS feedback_events (
                    event_id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    service TEXT,
                    actor TEXT,
                    metadata TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )"""
            )

    def append(self, event: FeedbackEvent) -> bool:
        event = event.normalized()
        with self._connect() as db:
            cur = db.execute(
                """INSERT OR IGNORE INTO feedback_events
                   (event_id, capability, subject_id, outcome, service, actor, metadata, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.capability,
                    event.subject_id,
                    event.outcome.value,
                    event.service,
                    event.actor,
                    json.dumps(dict(event.metadata or {}), sort_keys=True),
                    event.occurred_at,
                ),
            )
        return cur.rowcount == 1

    def events(self, *, capability: str | None = None, service: str | None = None) -> tuple[FeedbackEvent, ...]:
        clauses: list[str] = []
        args: list[str] = []
        if capability:
            clauses.append("capability=?")
            args.append(capability)
        if service:
            clauses.append("service=?")
            args.append(service)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM feedback_events" + where + " ORDER BY occurred_at, event_id",
                args,
            ).fetchall()
        return tuple(
            FeedbackEvent(
                event_id=row["event_id"],
                capability=row["capability"],
                subject_id=row["subject_id"],
                outcome=FeedbackOutcome(row["outcome"]),
                service=row["service"],
                actor=row["actor"],
                metadata=json.loads(row["metadata"]),
                occurred_at=row["occurred_at"],
            )
            for row in rows
        )


@dataclass(frozen=True)
class FeedbackMetrics:
    total: int
    accepted: int
    rejected: int
    reverted: int
    correct: int
    incorrect: int

    @property
    def acceptance_rate(self) -> float | None:
        denominator = self.accepted + self.rejected
        return self.accepted / denominator if denominator else None

    @property
    def precision(self) -> float | None:
        denominator = self.correct + self.incorrect
        return self.correct / denominator if denominator else None


def summarize_feedback(events: tuple[FeedbackEvent, ...]) -> FeedbackMetrics:
    counts = {outcome: 0 for outcome in FeedbackOutcome}
    for event in events:
        counts[event.outcome] += 1
    return FeedbackMetrics(
        total=len(events),
        accepted=counts[FeedbackOutcome.ACCEPTED],
        rejected=counts[FeedbackOutcome.REJECTED],
        reverted=counts[FeedbackOutcome.REVERTED],
        correct=counts[FeedbackOutcome.CORRECT],
        incorrect=counts[FeedbackOutcome.INCORRECT],
    )
