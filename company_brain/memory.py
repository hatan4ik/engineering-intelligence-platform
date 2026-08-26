"""Write governed ingestion changes through the durable Company Brain contract.

This module is the bridge between source lifecycle/reconciliation and the
Company Brain system of record. It preserves source-specific projection
memberships so an ACL update, replay, or deletion changes only the facts and
edges contributed by that source.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterator, Protocol

from control_plane.runtime import require_reference_storage
from ingestion.catalog import change_fingerprint
from ingestion.documents import KnowledgeChange, KnowledgeDocument
from ingestion.models import ChangeType, FileChange

from .model import BrainEntity, BrainEvidence, BrainRelationship, CompanyBrain, EntityKind, RelationshipKind
from .projector import CompanyBrainProjector
from .store import BrainProvenance, StoredEntity, StoredEvidence, StoredRelationship


class CompanyBrainMemoryError(RuntimeError):
    """Raised when a governed source change cannot be projected safely."""


class ProjectionState(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


def _required(value: str, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise CompanyBrainMemoryError(f"{label} is invalid")
    return value


@dataclass(frozen=True)
class BrainSourceProjection:
    """One source's currently materialized contribution to Company Brain."""

    tenant_id: str
    source_key: str
    source_kind: str
    state: ProjectionState
    fingerprint: str
    provenance: BrainProvenance
    entity_ids: tuple[str, ...] = ()
    owned_entity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    relationships: tuple[BrainRelationship, ...] = ()
    updated_at: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id", maximum=200)
        _required(self.source_key, "source_key")
        _required(self.source_kind, "source_kind", maximum=100)
        _required(self.fingerprint, "fingerprint")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise CompanyBrainMemoryError("projection updated_at must include a timezone")
        for values, label in (
            (self.entity_ids, "entity_ids"),
            (self.owned_entity_ids, "owned_entity_ids"),
            (self.evidence_ids, "evidence_ids"),
        ):
            if values != tuple(sorted(set(values))):
                raise CompanyBrainMemoryError(f"{label} must be sorted and unique")
            for value in values:
                _required(value, label)
        if not set(self.owned_entity_ids).issubset(self.entity_ids):
            raise CompanyBrainMemoryError("owned entities must be included in entity_ids")
        keys = tuple(_relationship_key(item) for item in self.relationships)
        if keys != tuple(sorted(set(keys))):
            raise CompanyBrainMemoryError("relationships must be sorted and unique")


@dataclass(frozen=True)
class ProjectionReceipt:
    source_key: str
    state: ProjectionState
    changed: bool
    duplicate: bool = False
    entity_count: int = 0
    evidence_count: int = 0
    relationship_count: int = 0


class BrainProjectionJournal(Protocol):
    def get(self, tenant_id: str, source_key: str) -> BrainSourceProjection | None: ...
    def active(self, tenant_id: str) -> tuple[BrainSourceProjection, ...]: ...
    def put(self, projection: BrainSourceProjection) -> None: ...


class CompanyBrainProjectionStore(Protocol):
    """The subset of the durable store required by governed ingestion."""

    def snapshot(self, tenant_id: str) -> CompanyBrain: ...

    def get_entity(
        self, tenant_id: str, entity_id: str, *, include_deleted: bool = False
    ) -> StoredEntity | None: ...

    def put_entity(self, tenant_id: str, entity: BrainEntity, *, provenance: BrainProvenance) -> StoredEntity: ...

    def delete_entity(
        self, tenant_id: str, entity_id: str, *, expected_version: int, reason: str
    ) -> StoredEntity: ...

    def get_evidence(
        self, tenant_id: str, evidence_id: str, *, include_deleted: bool = False
    ) -> StoredEvidence | None: ...

    def put_evidence(
        self, tenant_id: str, evidence: BrainEvidence, *, provenance: BrainProvenance) -> StoredEvidence: ...

    def delete_evidence(
        self, tenant_id: str, evidence_id: str, *, expected_version: int, reason: str
    ) -> StoredEvidence: ...

    def get_relationship(
        self,
        tenant_id: str,
        *,
        source_id: str,
        target_id: str,
        kind: RelationshipKind,
        include_deleted: bool = False,
    ) -> StoredRelationship | None: ...

    def put_relationship(
        self, tenant_id: str, relationship: BrainRelationship, *, provenance: BrainProvenance
    ) -> StoredRelationship: ...

    def delete_relationship(
        self,
        tenant_id: str,
        *,
        source_id: str,
        target_id: str,
        kind: RelationshipKind,
        expected_version: int,
        reason: str,
    ) -> StoredRelationship: ...


class SqliteBrainProjectionJournal:
    """Local durable projection membership journal.

    The journal contains identifiers, fingerprints, and provenance only. It
    never duplicates indexed source content or bypasses the Company Brain ACL
    model.
    """

    def __init__(self, path: str | Path = "company-brain-projections.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @contextmanager
    def _immediate(self, db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS company_brain_source_projections (
                    tenant_id TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, source_key)
                )"""
            )

    def get(self, tenant_id: str, source_key: str) -> BrainSourceProjection | None:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        key = _required(source_key, "source_key")
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM company_brain_source_projections WHERE tenant_id=? AND source_key=?", (tenant, key)
            ).fetchone()
        return self._from_row(row) if row else None

    def active(self, tenant_id: str) -> tuple[BrainSourceProjection, ...]:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM company_brain_source_projections
                   WHERE tenant_id=? AND state=? ORDER BY source_key""",
                (tenant, ProjectionState.ACTIVE.value),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def put(self, projection: BrainSourceProjection) -> None:
        with self._connect() as db, self._immediate(db):
            db.execute(
                """INSERT INTO company_brain_source_projections(
                       tenant_id, source_key, source_kind, state, fingerprint, provenance, payload, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(tenant_id, source_key) DO UPDATE SET
                       source_kind=excluded.source_kind, state=excluded.state, fingerprint=excluded.fingerprint,
                       provenance=excluded.provenance, payload=excluded.payload, updated_at=excluded.updated_at""",
                (
                    projection.tenant_id,
                    projection.source_key,
                    projection.source_kind,
                    projection.state.value,
                    projection.fingerprint,
                    json.dumps(_provenance_payload(projection.provenance), sort_keys=True),
                    json.dumps(_projection_payload(projection), sort_keys=True),
                    projection.updated_at.astimezone(timezone.utc).isoformat(),
                ),
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> BrainSourceProjection:
        raw = json.loads(row["payload"])
        return BrainSourceProjection(
            tenant_id=str(row["tenant_id"]),
            source_key=str(row["source_key"]),
            source_kind=str(row["source_kind"]),
            state=ProjectionState(str(row["state"])),
            fingerprint=str(row["fingerprint"]),
            provenance=_provenance_from_payload(json.loads(row["provenance"])),
            entity_ids=tuple(str(item) for item in raw["entity_ids"]),
            owned_entity_ids=tuple(str(item) for item in raw["owned_entity_ids"]),
            evidence_ids=tuple(str(item) for item in raw["evidence_ids"]),
            relationships=tuple(_relationship_from_payload(item) for item in raw["relationships"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])).astimezone(timezone.utc),
        )


@dataclass
class CompanyBrainMemoryProjector:
    """Project governed source changes into a tenant-scoped durable Company Brain."""

    store: CompanyBrainProjectionStore
    journal: BrainProjectionJournal
    tenant_id: str

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id", maximum=200)

    def project_file_change(self, change: FileChange, *, event_id: str | None = None) -> ProjectionReceipt:
        source = change.source
        source_key = f"file:{source.document_id}"
        provenance = BrainProvenance(
            source_system=source.provider,
            source_record_id=source.document_id,
            source_revision=source.commit_sha,
            observed_at=datetime.now(timezone.utc),
            event_id=event_id,
        )
        if change.change_type is ChangeType.DELETE:
            return self._delete(
                source_key=source_key,
                source_kind="file",
                fingerprint=f"deleted:{source.document_id}",
                provenance=provenance,
            )
        return self._upsert_file(change, source_key=source_key, provenance=provenance)

    def project_knowledge_change(
        self, change: KnowledgeChange, *, event_id: str | None = None
    ) -> ProjectionReceipt:
        document = change.document
        source_key = f"knowledge:{document.identity.document_id}"
        provenance = BrainProvenance(
            source_system=document.identity.provider,
            source_record_id=document.identity.document_id,
            source_revision=document.revision,
            observed_at=datetime.now(timezone.utc),
            event_id=event_id,
        )
        if change.change_type is ChangeType.DELETE:
            return self._delete(
                source_key=source_key,
                source_kind="knowledge",
                fingerprint=f"deleted:{document.identity.document_id}",
                provenance=provenance,
            )
        return self._upsert_knowledge(document, source_key=source_key, provenance=provenance)

    def _upsert_file(
        self, change: FileChange, *, source_key: str, provenance: BrainProvenance
    ) -> ProjectionReceipt:
        fingerprint = change_fingerprint(change)
        previous = self._assert_not_conflicting_replay(source_key, fingerprint, ProjectionState.ACTIVE, provenance)
        if previous and previous.state is ProjectionState.ACTIVE and previous.fingerprint == fingerprint:
            return self._receipt(previous, changed=False, duplicate=True)
        model = self.store.snapshot(self.tenant_id)
        result = CompanyBrainProjector(model).project_file_change(change)
        return self._materialize(
            previous=previous,
            source_key=source_key,
            source_kind="file",
            fingerprint=fingerprint,
            provenance=provenance,
            model=model,
            entity_ids=result.entity_ids,
            evidence_id=result.evidence_id,
        )

    def _upsert_knowledge(
        self, document: KnowledgeDocument, *, source_key: str, provenance: BrainProvenance
    ) -> ProjectionReceipt:
        fingerprint = _knowledge_fingerprint(document)
        previous = self._assert_not_conflicting_replay(source_key, fingerprint, ProjectionState.ACTIVE, provenance)
        if previous and previous.state is ProjectionState.ACTIVE and previous.fingerprint == fingerprint:
            return self._receipt(previous, changed=False, duplicate=True)
        model = self.store.snapshot(self.tenant_id)
        result = CompanyBrainProjector(model).project_knowledge_document(document)
        return self._materialize(
            previous=previous,
            source_key=source_key,
            source_kind="knowledge",
            fingerprint=fingerprint,
            provenance=provenance,
            model=model,
            entity_ids=result.entity_ids,
            evidence_id=result.evidence_id,
        )

    def _materialize(
        self,
        *,
        previous: BrainSourceProjection | None,
        source_key: str,
        source_kind: str,
        fingerprint: str,
        provenance: BrainProvenance,
        model: CompanyBrain,
        entity_ids: tuple[str, ...],
        evidence_id: str,
    ) -> ProjectionReceipt:
        entities = tuple(
            model.entities[entity_id]
            for entity_id in sorted(set(entity_ids))
            if model.entities[entity_id].kind is not EntityKind.EVIDENCE
        )
        relationships = tuple(
            sorted(
                (
                    BrainRelationship(
                        source_id=item.source_id,
                        target_id=item.target_id,
                        kind=item.kind,
                        evidence_ids=(evidence_id,),
                    )
                    for item in model.relationships
                    if evidence_id in item.evidence_ids
                ),
                key=_relationship_key,
            )
        )
        projection = BrainSourceProjection(
            tenant_id=self.tenant_id,
            source_key=source_key,
            source_kind=source_kind,
            state=ProjectionState.ACTIVE,
            fingerprint=fingerprint,
            provenance=provenance,
            entity_ids=tuple(sorted(item.entity_id for item in entities)),
            owned_entity_ids=tuple(
                sorted(item.entity_id for item in entities if _is_source_owned(item))
            ),
            evidence_ids=(evidence_id,),
            relationships=relationships,
            updated_at=datetime.now(timezone.utc),
        )
        for entity in entities:
            self._put_entity_if_changed(entity, provenance)
        self._put_evidence_if_changed(model.evidence[evidence_id], provenance)
        candidates = self._active_candidates(previous, projection)
        self._reconcile_relationships(previous, projection, candidates)
        self._retire_unreferenced(previous, candidates)
        self.journal.put(projection)
        return self._receipt(projection, changed=True)

    def _delete(
        self,
        *,
        source_key: str,
        source_kind: str,
        fingerprint: str,
        provenance: BrainProvenance,
    ) -> ProjectionReceipt:
        previous = self._assert_not_conflicting_replay(source_key, fingerprint, ProjectionState.DELETED, provenance)
        if previous is None:
            projection = BrainSourceProjection(
                tenant_id=self.tenant_id,
                source_key=source_key,
                source_kind=source_kind,
                state=ProjectionState.DELETED,
                fingerprint=fingerprint,
                provenance=provenance,
                updated_at=datetime.now(timezone.utc),
            )
            self.journal.put(projection)
            return self._receipt(projection, changed=False, duplicate=True)
        if previous.state is ProjectionState.DELETED:
            return self._receipt(previous, changed=False, duplicate=True)
        candidates = tuple(item for item in self.journal.active(self.tenant_id) if item.source_key != source_key)
        self._reconcile_relationships(previous, None, candidates)
        self._retire_unreferenced(previous, candidates)
        tombstone = BrainSourceProjection(
            tenant_id=self.tenant_id,
            source_key=source_key,
            source_kind=source_kind,
            state=ProjectionState.DELETED,
            fingerprint=fingerprint,
            provenance=provenance,
            entity_ids=previous.entity_ids,
            owned_entity_ids=previous.owned_entity_ids,
            evidence_ids=previous.evidence_ids,
            relationships=previous.relationships,
            updated_at=datetime.now(timezone.utc),
        )
        self.journal.put(tombstone)
        return self._receipt(tombstone, changed=True)

    def _assert_not_conflicting_replay(
        self,
        source_key: str,
        fingerprint: str,
        target_state: ProjectionState,
        provenance: BrainProvenance,
    ) -> BrainSourceProjection | None:
        previous = self.journal.get(self.tenant_id, source_key)
        if (
            previous
            and provenance.event_id
            and previous.provenance.event_id == provenance.event_id
            and (previous.state is not target_state or previous.fingerprint != fingerprint)
        ):
            raise CompanyBrainMemoryError("a source event ID cannot project different state or content")
        return previous

    def _active_candidates(
        self,
        previous: BrainSourceProjection | None,
        projection: BrainSourceProjection,
    ) -> tuple[BrainSourceProjection, ...]:
        return tuple(
            sorted(
                (
                    *(
                        item
                        for item in self.journal.active(self.tenant_id)
                        if item.source_key != (previous.source_key if previous else projection.source_key)
                    ),
                    projection,
                ),
                key=lambda item: item.source_key,
            )
        )

    def _put_entity_if_changed(self, entity: BrainEntity, provenance: BrainProvenance) -> None:
        current = self.store.get_entity(self.tenant_id, entity.entity_id)
        if current is None or current.entity != entity:
            self.store.put_entity(self.tenant_id, entity, provenance=provenance)

    def _put_evidence_if_changed(self, evidence: BrainEvidence, provenance: BrainProvenance) -> None:
        current = self.store.get_evidence(self.tenant_id, evidence.evidence_id)
        if current is None or current.evidence != evidence:
            self.store.put_evidence(self.tenant_id, evidence, provenance=provenance)

    def _reconcile_relationships(
        self,
        previous: BrainSourceProjection | None,
        projection: BrainSourceProjection | None,
        candidates: tuple[BrainSourceProjection, ...],
    ) -> None:
        desired = _relationship_memberships(candidates)
        affected = {
            _relationship_key(item)
            for record in (previous, projection)
            if record is not None
            for item in record.relationships
        }
        for key in sorted(affected):
            source_id, kind, target_id = key
            current = self.store.get_relationship(
                self.tenant_id, source_id=source_id, target_id=target_id, kind=kind
            )
            evidence_ids = desired.get(key, ())
            if not evidence_ids:
                if current is not None:
                    self.store.delete_relationship(
                        self.tenant_id,
                        source_id=source_id,
                        target_id=target_id,
                        kind=kind,
                        expected_version=current.version,
                        reason="source projection no longer contributes this relationship",
                    )
                continue
            candidate = next(
                record
                for record in candidates
                if any(_relationship_key(item) == key for item in record.relationships)
            )
            relationship = BrainRelationship(
                source_id=source_id,
                target_id=target_id,
                kind=kind,
                evidence_ids=evidence_ids,
            )
            if current is None or current.relationship != relationship:
                self.store.put_relationship(self.tenant_id, relationship, provenance=candidate.provenance)

    def _retire_unreferenced(
        self,
        previous: BrainSourceProjection | None,
        candidates: tuple[BrainSourceProjection, ...],
    ) -> None:
        if previous is None:
            return
        active_evidence = {item for record in candidates for item in record.evidence_ids}
        active_owned_entities = {item for record in candidates for item in record.owned_entity_ids}
        for evidence_id in previous.evidence_ids:
            if evidence_id not in active_evidence:
                current = self.store.get_evidence(self.tenant_id, evidence_id)
                if current is not None:
                    self.store.delete_evidence(
                        self.tenant_id,
                        evidence_id,
                        expected_version=current.version,
                        reason="source projection is superseded or deleted",
                    )
        for entity_id in previous.owned_entity_ids:
            if entity_id not in active_owned_entities:
                current = self.store.get_entity(self.tenant_id, entity_id)
                if current is not None:
                    self.store.delete_entity(
                        self.tenant_id,
                        entity_id,
                        expected_version=current.version,
                        reason="source projection is superseded or deleted",
                    )

    @staticmethod
    def _receipt(
        projection: BrainSourceProjection, *, changed: bool, duplicate: bool = False
    ) -> ProjectionReceipt:
        return ProjectionReceipt(
            source_key=projection.source_key,
            state=projection.state,
            changed=changed,
            duplicate=duplicate,
            entity_count=len(projection.entity_ids),
            evidence_count=len(projection.evidence_ids),
            relationship_count=len(projection.relationships),
        )


def _is_source_owned(entity: BrainEntity) -> bool:
    return entity.kind not in {EntityKind.REPOSITORY, EntityKind.SERVICE, EntityKind.TEAM, EntityKind.OWNER}


def _relationship_key(relationship: BrainRelationship) -> tuple[str, RelationshipKind, str]:
    return relationship.source_id, relationship.kind, relationship.target_id


def _relationship_memberships(
    projections: tuple[BrainSourceProjection, ...],
) -> dict[tuple[str, RelationshipKind, str], tuple[str, ...]]:
    memberships: dict[tuple[str, RelationshipKind, str], set[str]] = {}
    for projection in projections:
        for relationship in projection.relationships:
            memberships.setdefault(_relationship_key(relationship), set()).update(relationship.evidence_ids)
    return {key: tuple(sorted(value)) for key, value in memberships.items()}


def _projection_payload(projection: BrainSourceProjection) -> dict[str, object]:
    return {
        "entity_ids": list(projection.entity_ids),
        "owned_entity_ids": list(projection.owned_entity_ids),
        "evidence_ids": list(projection.evidence_ids),
        "relationships": [_relationship_payload(item) for item in projection.relationships],
    }


def _relationship_payload(relationship: BrainRelationship) -> dict[str, object]:
    return {
        "source_id": relationship.source_id,
        "target_id": relationship.target_id,
        "kind": relationship.kind.value,
        "evidence_ids": list(relationship.evidence_ids),
    }


def _relationship_from_payload(payload: dict[str, object]) -> BrainRelationship:
    return BrainRelationship(
        source_id=str(payload["source_id"]),
        target_id=str(payload["target_id"]),
        kind=RelationshipKind(str(payload["kind"])),
        evidence_ids=tuple(str(item) for item in payload["evidence_ids"]),
    )


def _provenance_payload(provenance: BrainProvenance) -> dict[str, object]:
    return {
        "source_system": provenance.source_system,
        "source_record_id": provenance.source_record_id,
        "source_revision": provenance.source_revision,
        "observed_at": provenance.observed_at.astimezone(timezone.utc).isoformat(),
        "event_id": provenance.event_id,
    }


def _provenance_from_payload(payload: dict[str, object]) -> BrainProvenance:
    return BrainProvenance(
        source_system=str(payload["source_system"]),
        source_record_id=str(payload["source_record_id"]),
        source_revision=str(payload["source_revision"]),
        observed_at=datetime.fromisoformat(str(payload["observed_at"])).astimezone(timezone.utc),
        event_id=str(payload["event_id"]) if payload.get("event_id") is not None else None,
    )


def _knowledge_fingerprint(document: KnowledgeDocument) -> str:
    payload = {
        "document_id": document.identity.document_id,
        "title": document.title,
        "revision": document.revision,
        "content_hash": document.content_hash,
        "updated_at": document.updated_at.astimezone(timezone.utc).isoformat(),
        "source_url": document.source_url,
        "owner": document.owner,
        "service": document.service,
        "acl_groups": sorted(set(document.acl.groups)),
        "acl_users": sorted(set(document.acl.users)),
        "metadata": sorted(document.metadata.items()),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
