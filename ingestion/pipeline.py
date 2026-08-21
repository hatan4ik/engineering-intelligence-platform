from __future__ import annotations

from dataclasses import dataclass, field

from .chunkers import chunk_change
from .index import Index
from .models import ChangeType
from .events import NormalizedEvent


@dataclass
class IngestionPipeline:
    index: Index
    processed_events: set[str] = field(default_factory=set)

    def process(self, event: NormalizedEvent) -> dict[str, int | bool]:
        if event.event_id in self.processed_events:
            return {"duplicate": True, "upserted": 0, "deleted": 0, "chunks": 0}

        upserted = deleted = chunks_written = 0
        for change in event.changes:
            document_id = change.source.document_id
            if change.change_type == ChangeType.DELETE:
                self.index.delete_document(document_id)
                deleted += 1
                continue
            chunks = chunk_change(change)
            self.index.replace_document(document_id, chunks)
            upserted += 1
            chunks_written += len(chunks)

        self.processed_events.add(event.event_id)
        return {"duplicate": False, "upserted": upserted, "deleted": deleted, "chunks": chunks_written}
