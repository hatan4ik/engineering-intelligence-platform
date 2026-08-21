from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .ledger import SqliteEventLedger
from .models import IngestionEvent
from .pipeline import IngestionProcessor


class EventLedger(Protocol):
    def seen(self, event_id: str) -> bool: ...
    def start(self, event_id: str) -> None: ...
    def complete(self, event_id: str) -> None: ...
    def fail(self, event: IngestionEvent, error: Exception) -> None: ...


@dataclass
class IngestionWorker:
    processor: IngestionProcessor
    ledger: EventLedger

    def handle(self, event: IngestionEvent) -> str:
        if self.ledger.seen(event.event_id):
            return "duplicate"
        self.ledger.start(event.event_id)
        try:
            result = self.processor.process(event)
        except Exception as exc:
            self.ledger.fail(event, exc)
            raise
        self.ledger.complete(event.event_id)
        return result


def sqlite_worker(processor: IngestionProcessor, path: str = "ingestion-ledger.db") -> IngestionWorker:
    return IngestionWorker(processor=processor, ledger=SqliteEventLedger(path))
