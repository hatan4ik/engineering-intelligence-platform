from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import SourceCatalog
from .chunkers import chunk_change
from .index import Index
from .models import ChangeType
from .events import NormalizedEvent


@dataclass
class IngestionPipeline:
    index: Index
    catalog: SourceCatalog | None = None
    # Backward-compatible local convenience only. Durable workers must use the
    # event ledger; this set cannot survive a process restart.
    processed_events: set[str] = field(default_factory=set)

    def process(self, event: NormalizedEvent) -> dict[str, int | bool]:
        if event.event_id in self.processed_events:
            return {"duplicate": True, "upserted": 0, "deleted": 0, "chunks": 0}

        result = self.apply_changes(event.changes, event_id=event.event_id)

        self.processed_events.add(event.event_id)
        return {"duplicate": False, **result}

    def apply_changes(
        self, changes: tuple[FileChange, ...], *, event_id: str | None
    ) -> dict[str, int]:
        """Apply already-authorized changes and update the source catalog after index success."""
        upserted = deleted = chunks_written = 0
        for change in changes:
            document_id = change.source.document_id
            if change.change_type == ChangeType.DELETE:
                self.index.delete_document(document_id)
                if self.catalog is not None:
                    self.catalog.record_delete(change, event_id=event_id)
                deleted += 1
                continue
            chunks = chunk_change(change)
            self.index.replace_document(document_id, chunks)
            if self.catalog is not None:
                self.catalog.record_upsert(change, event_id=event_id)
            upserted += 1
            chunks_written += len(chunks)
        return {"upserted": upserted, "deleted": deleted, "chunks": chunks_written}
