"""Source-manifest reconciliation for repairing webhook and index drift."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .catalog import SourceCatalog, SourceScope
from .models import ACL, ChangeType, FileChange
from .pipeline import IngestionPipeline


@dataclass(frozen=True)
class ReconciliationResult:
    scope: SourceScope
    unchanged: int
    upserted: int
    deleted: int
    chunks: int


@dataclass
class SourceReconciler:
    """Reconcile one complete, authorized source manifest against the catalog."""

    pipeline: IngestionPipeline
    catalog: SourceCatalog

    def __post_init__(self) -> None:
        if self.pipeline.catalog is not self.catalog:
            raise ValueError("reconciliation pipeline must use the same authoritative source catalog")

    def reconcile(self, scope: SourceScope, manifest: Iterable[FileChange]) -> ReconciliationResult:
        observed: dict[str, FileChange] = {}
        candidates: list[FileChange] = []
        unchanged = 0
        for change in manifest:
            if change.change_type is not ChangeType.UPSERT:
                raise ValueError("a reconciliation manifest must contain complete upsert records only")
            source = change.source
            if (source.provider, source.repository, source.branch) != (
                scope.provider,
                scope.repository,
                scope.branch,
            ):
                raise ValueError("a reconciliation manifest cannot cross source scope")
            document_id = source.document_id
            if document_id in observed:
                raise ValueError("a reconciliation manifest cannot contain duplicate document IDs")
            observed[document_id] = change
            index_missing = bool((change.content or "").strip()) and not self.pipeline.index.has_document(document_id)
            if self.catalog.needs_upsert(change) or index_missing:
                candidates.append(change)
            else:
                unchanged += 1

        for record in self.catalog.active_in_scope(scope):
            if record.source.document_id not in observed:
                candidates.append(
                    FileChange(
                        source=record.source,
                        change_type=ChangeType.DELETE,
                        acl=ACL(),
                    )
                )

        result = self.pipeline.apply_changes(tuple(candidates), event_id=None)
        return ReconciliationResult(
            scope=scope,
            unchanged=unchanged,
            upserted=int(result["upserted"]),
            deleted=int(result["deleted"]),
            chunks=int(result["chunks"]),
        )
