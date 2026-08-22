from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .events import NormalizedEvent
from .ledger import SqliteEventLedger
from .pipeline import IngestionPipeline


class EventLedger(Protocol):
    def seen(self, event_id: str) -> bool: ...
    def start(self, event_id: str) -> None: ...
    def complete(self, event_id: str) -> None: ...
    def fail(self, event: NormalizedEvent, error: Exception) -> None: ...


@dataclass
class IngestionWorker:
    pipeline: IngestionPipeline
    ledger: EventLedger

    def handle(self, event: NormalizedEvent) -> dict[str, int | bool]:
        if self.ledger.seen(event.event_id):
            return {"duplicate": True, "upserted": 0, "deleted": 0, "chunks": 0}
        self.ledger.start(event.event_id)
        try:
            result = self.pipeline.process(event)
        except Exception as exc:
            self.ledger.fail(event, exc)
            raise
        self.ledger.complete(event.event_id)
        return result


def sqlite_worker(pipeline: IngestionPipeline, path: str = "ingestion-ledger.db") -> IngestionWorker:
    return IngestionWorker(pipeline=pipeline, ledger=SqliteEventLedger(path))
