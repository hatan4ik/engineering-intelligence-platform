from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .catalog import SourceCatalog
from .chunkers import chunk_change
from .index import Index
from .models import ChangeType, FileChange
from .events import NormalizedEvent

if TYPE_CHECKING:
    from company_brain.memory import CompanyBrainMemoryProjector
    from company_brain.projector import CompanyBrainProjector


@dataclass
class IngestionPipeline:
    index: Index
    catalog: SourceCatalog | None = None
    brain_projector: CompanyBrainProjector | None = None
    brain_memory_projector: CompanyBrainMemoryProjector | None = None
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
        """Apply authorized changes, then project them before source-catalog advancement.

        The durable Company Brain projection runs only after the retrieval-index
        write succeeds. It runs before the source catalog advances so a failed
        projection remains replayable through the existing worker/ledger and
        reconciliation paths rather than being silently marked complete.
        """
        upserted = deleted = chunks_written = 0
        for change in changes:
            document_id = change.source.document_id
            if change.change_type == ChangeType.DELETE:
                self.index.delete_document(document_id)
                if self.brain_memory_projector is not None:
                    self.brain_memory_projector.project_file_change(change, event_id=event_id)
                if self.brain_projector is not None:
                    self.brain_projector.project_file_change(change)
                if self.catalog is not None:
                    self.catalog.record_delete(change, event_id=event_id)
                deleted += 1
                continue
            chunks = chunk_change(change)
            self.index.replace_document(document_id, chunks)
            if self.brain_memory_projector is not None:
                self.brain_memory_projector.project_file_change(change, event_id=event_id)
            if self.brain_projector is not None:
                self.brain_projector.project_file_change(change)
            if self.catalog is not None:
                self.catalog.record_upsert(change, event_id=event_id)
            upserted += 1
            chunks_written += len(chunks)
        return {"upserted": upserted, "deleted": deleted, "chunks": chunks_written}
