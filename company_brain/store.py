"""Tenant-isolated durable reference store for Company Brain records.

The Company Brain model deliberately retains compact facts and evidence pointers,
not source document bodies.  This SQLite implementation is for local/reference
operation only.  It makes the system-of-record contract explicit so a managed
implementation can preserve tenant isolation, compare-and-swap versions,
provenance, retention and tombstones without relying on an index as authority.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

from control_plane.runtime import require_reference_storage

from .model import BrainEntity, BrainEvidence, BrainRelationship, CompanyBrain, EntityKind, RelationshipKind
from .serialization import (
    payload_from_json,
    provenance_fields,
    provenance_payload as _provenance_payload,
    relationship_from_payload as _relationship_from_payload,
    relationship_payload as _relationship_payload,
    required_text,
    text_pairs,
    text_sequence,
)
from .sqlite import SqliteReferenceDatabase


class CompanyBrainStoreError(RuntimeError):
    """Raised when a durable Company Brain operation violates its contract."""


class CompanyBrainVersionConflict(CompanyBrainStoreError):
    """Raised when a conditional write observes a different record version."""


class CompanyBrainRetentionError(CompanyBrainStoreError):
    """Raised when a lifecycle request conflicts with a legal retention hold."""


def _required(value: str, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise CompanyBrainStoreError(f"{label} is invalid")
    return value


def _timestamp(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CompanyBrainStoreError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return _timestamp(value, "timestamp").isoformat()


def _parse_timestamp(value: str) -> datetime:
    return _timestamp(datetime.fromisoformat(value), "stored timestamp")


@dataclass(frozen=True)
class BrainProvenance:
    """The source revision that made a Company Brain record eligible to exist."""

    source_system: str
    source_record_id: str
    source_revision: str
    observed_at: datetime
    event_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.source_system, "provenance source_system", maximum=100)
        _required(self.source_record_id, "provenance source_record_id")
        _required(self.source_revision, "provenance source_revision", maximum=200)
        _timestamp(self.observed_at, "provenance observed_at")
        if self.event_id is not None:
            _required(self.event_id, "provenance event_id", maximum=200)


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention metadata; reference storage never performs irreversible purge."""

    retain_until: datetime | None = None
    legal_hold: bool = False

    def __post_init__(self) -> None:
        if self.retain_until is not None:
            _timestamp(self.retain_until, "retain_until")


@dataclass(frozen=True)
class StoredEntity:
    tenant_id: str
    entity: BrainEntity
    version: int
    provenance: BrainProvenance
    retention: RetentionPolicy
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deletion_reason: str | None = None

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id", maximum=200)
        if self.version < 1:
            raise CompanyBrainStoreError("record version must be positive")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.updated_at, "updated_at")
        if self.deleted_at is not None:
            _timestamp(self.deleted_at, "deleted_at")
            _required(self.deletion_reason or "", "deletion_reason", maximum=500)
        elif self.deletion_reason is not None:
            raise CompanyBrainStoreError("deletion_reason requires deleted_at")


@dataclass(frozen=True)
class StoredEvidence:
    tenant_id: str
    evidence: BrainEvidence
    version: int
    provenance: BrainProvenance
    retention: RetentionPolicy
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deletion_reason: str | None = None

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id", maximum=200)
        if self.version < 1:
            raise CompanyBrainStoreError("record version must be positive")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.updated_at, "updated_at")
        if self.deleted_at is not None:
            _timestamp(self.deleted_at, "deleted_at")
            _required(self.deletion_reason or "", "deletion_reason", maximum=500)
        elif self.deletion_reason is not None:
            raise CompanyBrainStoreError("deletion_reason requires deleted_at")


@dataclass(frozen=True)
class StoredRelationship:
    tenant_id: str
    relationship: BrainRelationship
    version: int
    provenance: BrainProvenance
    retention: RetentionPolicy
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deletion_reason: str | None = None

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id", maximum=200)
        if self.version < 1:
            raise CompanyBrainStoreError("record version must be positive")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.updated_at, "updated_at")
        if self.deleted_at is not None:
            _timestamp(self.deleted_at, "deleted_at")
            _required(self.deletion_reason or "", "deletion_reason", maximum=500)
        elif self.deletion_reason is not None:
            raise CompanyBrainStoreError("deletion_reason requires deleted_at")


@dataclass(frozen=True)
class BrainAuditEvent:
    sequence: int
    tenant_id: str
    record_type: str
    record_key: str
    operation: str
    version: int
    occurred_at: datetime
    provenance: BrainProvenance
    deletion_reason: str | None = None


class CompanyBrainStore(Protocol):
    """The persistence boundary used by durable Company Brain projections."""

    def get_entity(
        self, tenant_id: str, entity_id: str, *, include_deleted: bool = False
    ) -> StoredEntity | None: ...

    def put_entity(
        self,
        tenant_id: str,
        entity: BrainEntity,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredEntity: ...

    def get_evidence(
        self, tenant_id: str, evidence_id: str, *, include_deleted: bool = False
    ) -> StoredEvidence | None: ...

    def put_evidence(
        self,
        tenant_id: str,
        evidence: BrainEvidence,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredEvidence: ...

    def put_relationship(
        self,
        tenant_id: str,
        relationship: BrainRelationship,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredRelationship: ...

    def delete_entity(
        self, tenant_id: str, entity_id: str, *, expected_version: int, reason: str
    ) -> StoredEntity: ...

    def delete_evidence(
        self, tenant_id: str, evidence_id: str, *, expected_version: int, reason: str
    ) -> StoredEvidence: ...

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


class SqliteCompanyBrainStore(SqliteReferenceDatabase):
    """SQLite reference backend with tenant-scoped CAS and tombstone semantics.

    SQLite is intentionally not a production fallback.  Every lookup has a
    mandatory tenant scope, writes are compare-and-swap protected, and a delete
    keeps the source provenance and lifecycle event for audit/reconciliation.
    """

    def __init__(self, path: str | Path = "company-brain.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        self._read_only = False
        self._init_schema()

    @classmethod
    def open_read_only(cls, path: str | Path) -> "SqliteCompanyBrainStore":
        """Open an existing reference database without schema setup or write access.

        Maintenance and reporting paths use this constructor so merely reading
        Company Brain memory cannot create a database, run DDL, or change a
        source-of-record row.
        """

        require_reference_storage(cls.__name__)
        database_path = Path(path)
        if not database_path.is_file():
            raise CompanyBrainStoreError("read-only Company Brain database does not exist")
        store = object.__new__(cls)
        store.path = str(database_path.resolve())
        store._read_only = True
        return store

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_brain_entities (
                    tenant_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    provenance TEXT NOT NULL,
                    retain_until TEXT,
                    legal_hold INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    deletion_reason TEXT,
                    PRIMARY KEY (tenant_id, entity_id)
                );
                CREATE TABLE IF NOT EXISTS company_brain_evidence (
                    tenant_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    provenance TEXT NOT NULL,
                    retain_until TEXT,
                    legal_hold INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    deletion_reason TEXT,
                    PRIMARY KEY (tenant_id, evidence_id)
                );
                CREATE TABLE IF NOT EXISTS company_brain_relationships (
                    tenant_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    provenance TEXT NOT NULL,
                    retain_until TEXT,
                    legal_hold INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    deletion_reason TEXT,
                    PRIMARY KEY (tenant_id, source_id, target_id, relationship_kind)
                );
                CREATE TABLE IF NOT EXISTS company_brain_audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    deletion_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS company_brain_audit_events_tenant_record
                    ON company_brain_audit_events(tenant_id, record_type, record_key, sequence);
                """
            )

    def get_entity(
        self, tenant_id: str, entity_id: str, *, include_deleted: bool = False
    ) -> StoredEntity | None:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        key = _required(entity_id, "entity_id")
        row = self._get_row("company_brain_entities", "entity_id", tenant, key, include_deleted)
        return self._entity_from_row(row) if row else None

    def list_entities(self, tenant_id: str, *, include_deleted: bool = False) -> tuple[StoredEntity, ...]:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        query = "SELECT * FROM company_brain_entities WHERE tenant_id=?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += " ORDER BY entity_id"
        with self._connect() as db:
            rows = db.execute(query, (tenant,)).fetchall()
        return tuple(self._entity_from_row(row) for row in rows)

    def put_entity(
        self,
        tenant_id: str,
        entity: BrainEntity,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredEntity:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        with self._connect() as db, self._immediate(db):
            stored = self._put_entity(
                db, tenant, entity, provenance, retention, expected_version=expected_version
            )
        return stored

    def get_evidence(
        self, tenant_id: str, evidence_id: str, *, include_deleted: bool = False
    ) -> StoredEvidence | None:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        key = _required(evidence_id, "evidence_id")
        row = self._get_row("company_brain_evidence", "evidence_id", tenant, key, include_deleted)
        return self._evidence_from_row(row) if row else None

    def list_evidence(self, tenant_id: str, *, include_deleted: bool = False) -> tuple[StoredEvidence, ...]:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        query = "SELECT * FROM company_brain_evidence WHERE tenant_id=?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += " ORDER BY evidence_id"
        with self._connect() as db:
            rows = db.execute(query, (tenant,)).fetchall()
        return tuple(self._evidence_from_row(row) for row in rows)

    def put_evidence(
        self,
        tenant_id: str,
        evidence: BrainEvidence,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredEvidence:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        with self._connect() as db, self._immediate(db):
            stored = self._put_evidence(
                db, tenant, evidence, provenance, retention, expected_version=expected_version
            )
            evidence_entity = BrainEntity(
                entity_id=evidence.evidence_id,
                kind=EntityKind.EVIDENCE,
                label=evidence.citation,
                attributes=(("revision", evidence.revision), ("source_kind", evidence.source_kind)),
            )
            current_entity = db.execute(
                "SELECT version FROM company_brain_entities WHERE tenant_id=? AND entity_id=?",
                (tenant, evidence.evidence_id),
            ).fetchone()
            self._put_entity(
                db,
                tenant,
                evidence_entity,
                provenance,
                retention,
                expected_version=int(current_entity["version"]) if current_entity else None,
            )
        return stored

    def get_relationship(
        self,
        tenant_id: str,
        *,
        source_id: str,
        target_id: str,
        kind: RelationshipKind,
        include_deleted: bool = False,
    ) -> StoredRelationship | None:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        source = _required(source_id, "relationship source_id")
        target = _required(target_id, "relationship target_id")
        with self._connect() as db:
            row = db.execute(
                """SELECT * FROM company_brain_relationships
                   WHERE tenant_id=? AND source_id=? AND target_id=? AND relationship_kind=?
                   """ + ("" if include_deleted else " AND deleted_at IS NULL"),
                (tenant, source, target, kind.value),
            ).fetchone()
        return self._relationship_from_row(row) if row else None

    def list_relationships(
        self, tenant_id: str, *, include_deleted: bool = False
    ) -> tuple[StoredRelationship, ...]:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        query = """
            SELECT relation.* FROM company_brain_relationships AS relation
            JOIN company_brain_entities AS source
              ON source.tenant_id=relation.tenant_id AND source.entity_id=relation.source_id
            JOIN company_brain_entities AS target
              ON target.tenant_id=relation.tenant_id AND target.entity_id=relation.target_id
            WHERE relation.tenant_id=?
        """
        if not include_deleted:
            query += " AND relation.deleted_at IS NULL AND source.deleted_at IS NULL AND target.deleted_at IS NULL"
        query += " ORDER BY relation.source_id, relation.relationship_kind, relation.target_id"
        with self._connect() as db:
            rows = db.execute(query, (tenant,)).fetchall()
        return tuple(self._relationship_from_row(row) for row in rows)

    def put_relationship(
        self,
        tenant_id: str,
        relationship: BrainRelationship,
        *,
        provenance: BrainProvenance,
        retention: RetentionPolicy = RetentionPolicy(),
        expected_version: int | None = None,
    ) -> StoredRelationship:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        with self._connect() as db, self._immediate(db):
            self._assert_active_entity(db, tenant, relationship.source_id)
            self._assert_active_entity(db, tenant, relationship.target_id)
            for evidence_id in relationship.evidence_ids:
                self._assert_active_evidence(db, tenant, evidence_id)
            stored = self._put_relationship(
                db, tenant, relationship, provenance, retention, expected_version=expected_version
            )
        return stored

    def delete_entity(
        self,
        tenant_id: str,
        entity_id: str,
        *,
        expected_version: int,
        reason: str,
        deleted_at: datetime | None = None,
    ) -> StoredEntity:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        key = _required(entity_id, "entity_id")
        delete_reason = _required(reason, "deletion reason", maximum=500)
        when = _timestamp(deleted_at or datetime.now(timezone.utc), "deleted_at")
        with self._connect() as db, self._immediate(db):
            row = db.execute(
                "SELECT * FROM company_brain_entities WHERE tenant_id=? AND entity_id=?", (tenant, key)
            ).fetchone()
            if row is None:
                raise CompanyBrainStoreError("entity does not exist")
            current = self._entity_from_row(row)
            self._assert_expected(current.version, expected_version)
            if current.deleted_at is not None:
                raise CompanyBrainStoreError("entity is already deleted")
            if current.entity.kind is EntityKind.EVIDENCE:
                raise CompanyBrainStoreError("evidence entities must be deleted through delete_evidence")
            if current.retention.legal_hold:
                raise CompanyBrainRetentionError("entity is under legal hold and cannot be tombstoned")
            stored = StoredEntity(
                tenant_id=tenant,
                entity=current.entity,
                version=current.version + 1,
                provenance=current.provenance,
                retention=current.retention,
                created_at=current.created_at,
                updated_at=when,
                deleted_at=when,
                deletion_reason=delete_reason,
            )
            self._write_entity(db, stored)
            self._append_event(
                db, tenant, "entity", key, "tombstoned", stored.version, when, current.provenance, delete_reason
            )
        return stored

    def delete_evidence(
        self,
        tenant_id: str,
        evidence_id: str,
        *,
        expected_version: int,
        reason: str,
        deleted_at: datetime | None = None,
    ) -> StoredEvidence:
        """Tombstone evidence and its structural evidence entity atomically."""
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        key = _required(evidence_id, "evidence_id")
        delete_reason = _required(reason, "deletion reason", maximum=500)
        when = _timestamp(deleted_at or datetime.now(timezone.utc), "deleted_at")
        with self._connect() as db, self._immediate(db):
            evidence_row = db.execute(
                "SELECT * FROM company_brain_evidence WHERE tenant_id=? AND evidence_id=?", (tenant, key)
            ).fetchone()
            if evidence_row is None:
                raise CompanyBrainStoreError("evidence does not exist")
            current = self._evidence_from_row(evidence_row)
            self._assert_expected(current.version, expected_version)
            if current.deleted_at is not None:
                raise CompanyBrainStoreError("evidence is already deleted")
            if current.retention.legal_hold:
                raise CompanyBrainRetentionError("evidence is under legal hold and cannot be tombstoned")

            entity_row = db.execute(
                "SELECT * FROM company_brain_entities WHERE tenant_id=? AND entity_id=?", (tenant, key)
            ).fetchone()
            if entity_row is None:
                raise CompanyBrainStoreError("evidence is missing its structural entity")
            structural_entity = self._entity_from_row(entity_row)
            if structural_entity.entity.kind is not EntityKind.EVIDENCE:
                raise CompanyBrainStoreError("evidence structural entity has an invalid kind")
            if structural_entity.deleted_at is not None:
                raise CompanyBrainStoreError("evidence structural entity is already deleted")
            if structural_entity.retention.legal_hold:
                raise CompanyBrainRetentionError("evidence entity is under legal hold and cannot be tombstoned")

            stored = StoredEvidence(
                tenant_id=tenant,
                evidence=current.evidence,
                version=current.version + 1,
                provenance=current.provenance,
                retention=current.retention,
                created_at=current.created_at,
                updated_at=when,
                deleted_at=when,
                deletion_reason=delete_reason,
            )
            self._write_evidence(db, stored)
            self._append_event(
                db, tenant, "evidence", key, "tombstoned", stored.version, when, current.provenance, delete_reason
            )
            tombstoned_entity = StoredEntity(
                tenant_id=tenant,
                entity=structural_entity.entity,
                version=structural_entity.version + 1,
                provenance=structural_entity.provenance,
                retention=structural_entity.retention,
                created_at=structural_entity.created_at,
                updated_at=when,
                deleted_at=when,
                deletion_reason=delete_reason,
            )
            self._write_entity(db, tombstoned_entity)
            self._append_event(
                db,
                tenant,
                "entity",
                key,
                "tombstoned",
                tombstoned_entity.version,
                when,
                structural_entity.provenance,
                delete_reason,
            )
        return stored

    def delete_relationship(
        self,
        tenant_id: str,
        *,
        source_id: str,
        target_id: str,
        kind: RelationshipKind,
        expected_version: int,
        reason: str,
        deleted_at: datetime | None = None,
    ) -> StoredRelationship:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        source = _required(source_id, "relationship source_id")
        target = _required(target_id, "relationship target_id")
        delete_reason = _required(reason, "deletion reason", maximum=500)
        when = _timestamp(deleted_at or datetime.now(timezone.utc), "deleted_at")
        with self._connect() as db, self._immediate(db):
            row = db.execute(
                """SELECT * FROM company_brain_relationships
                   WHERE tenant_id=? AND source_id=? AND target_id=? AND relationship_kind=?""",
                (tenant, source, target, kind.value),
            ).fetchone()
            if row is None:
                raise CompanyBrainStoreError("relationship does not exist")
            current = self._relationship_from_row(row)
            self._assert_expected(current.version, expected_version)
            if current.deleted_at is not None:
                raise CompanyBrainStoreError("relationship is already deleted")
            if current.retention.legal_hold:
                raise CompanyBrainRetentionError("relationship is under legal hold and cannot be tombstoned")
            stored = StoredRelationship(
                tenant_id=tenant,
                relationship=current.relationship,
                version=current.version + 1,
                provenance=current.provenance,
                retention=current.retention,
                created_at=current.created_at,
                updated_at=when,
                deleted_at=when,
                deletion_reason=delete_reason,
            )
            self._write_relationship(db, stored)
            self._append_event(
                db,
                tenant,
                "relationship",
                self._relationship_key(current.relationship),
                "tombstoned",
                stored.version,
                when,
                current.provenance,
                delete_reason,
            )
        return stored

    def audit_events(
        self, tenant_id: str, *, record_type: str | None = None, record_key: str | None = None
    ) -> tuple[BrainAuditEvent, ...]:
        tenant = _required(tenant_id, "tenant_id", maximum=200)
        query = "SELECT * FROM company_brain_audit_events WHERE tenant_id=?"
        values: list[str] = [tenant]
        if record_type is not None:
            query += " AND record_type=?"
            values.append(_required(record_type, "record_type", maximum=50))
        if record_key is not None:
            query += " AND record_key=?"
            values.append(_required(record_key, "record_key"))
        query += " ORDER BY sequence"
        with self._connect() as db:
            rows = db.execute(query, values).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def snapshot(self, tenant_id: str) -> CompanyBrain:
        """Rebuild an active model snapshot for read-only product context assembly."""
        brain = CompanyBrain()
        for stored_entity in self.list_entities(tenant_id):
            brain.upsert_entity(stored_entity.entity)
        for stored_evidence in self.list_evidence(tenant_id):
            brain.evidence[stored_evidence.evidence.evidence_id] = stored_evidence.evidence
        for stored_relationship in self.list_relationships(tenant_id):
            brain.relate(
                source_id=stored_relationship.relationship.source_id,
                target_id=stored_relationship.relationship.target_id,
                kind=stored_relationship.relationship.kind,
                evidence_ids=stored_relationship.relationship.evidence_ids,
            )
        return brain

    def _get_row(
        self, table: str, id_column: str, tenant_id: str, record_id: str, include_deleted: bool
    ) -> sqlite3.Row | None:
        query = f"SELECT * FROM {table} WHERE tenant_id=? AND {id_column}=?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with self._connect() as db:
            return db.execute(query, (tenant_id, record_id)).fetchone()

    def _put_entity(
        self,
        db: sqlite3.Connection,
        tenant_id: str,
        entity: BrainEntity,
        provenance: BrainProvenance,
        retention: RetentionPolicy,
        *,
        expected_version: int | None,
    ) -> StoredEntity:
        row = db.execute(
            "SELECT * FROM company_brain_entities WHERE tenant_id=? AND entity_id=?",
            (tenant_id, entity.entity_id),
        ).fetchone()
        current = self._entity_from_row(row) if row else None
        self._assert_expected(current.version if current else None, expected_version)
        self._assert_mutable(current, retention)
        when = datetime.now(timezone.utc)
        stored = StoredEntity(
            tenant_id=tenant_id,
            entity=entity,
            version=1 if current is None else current.version + 1,
            provenance=provenance,
            retention=retention,
            created_at=current.created_at if current else when,
            updated_at=when,
        )
        self._write_entity(db, stored)
        self._append_event(
            db,
            tenant_id,
            "entity",
            entity.entity_id,
            "created" if current is None else "updated",
            stored.version,
            when,
            provenance,
        )
        return stored

    def _put_evidence(
        self,
        db: sqlite3.Connection,
        tenant_id: str,
        evidence: BrainEvidence,
        provenance: BrainProvenance,
        retention: RetentionPolicy,
        *,
        expected_version: int | None,
    ) -> StoredEvidence:
        row = db.execute(
            "SELECT * FROM company_brain_evidence WHERE tenant_id=? AND evidence_id=?",
            (tenant_id, evidence.evidence_id),
        ).fetchone()
        current = self._evidence_from_row(row) if row else None
        self._assert_expected(current.version if current else None, expected_version)
        self._assert_mutable(current, retention)
        when = datetime.now(timezone.utc)
        stored = StoredEvidence(
            tenant_id=tenant_id,
            evidence=evidence,
            version=1 if current is None else current.version + 1,
            provenance=provenance,
            retention=retention,
            created_at=current.created_at if current else when,
            updated_at=when,
        )
        self._write_evidence(db, stored)
        self._append_event(
            db,
            tenant_id,
            "evidence",
            evidence.evidence_id,
            "created" if current is None else "updated",
            stored.version,
            when,
            provenance,
        )
        return stored

    def _put_relationship(
        self,
        db: sqlite3.Connection,
        tenant_id: str,
        relationship: BrainRelationship,
        provenance: BrainProvenance,
        retention: RetentionPolicy,
        *,
        expected_version: int | None,
    ) -> StoredRelationship:
        row = db.execute(
            """SELECT * FROM company_brain_relationships
               WHERE tenant_id=? AND source_id=? AND target_id=? AND relationship_kind=?""",
            (tenant_id, relationship.source_id, relationship.target_id, relationship.kind.value),
        ).fetchone()
        current = self._relationship_from_row(row) if row else None
        self._assert_expected(current.version if current else None, expected_version)
        self._assert_mutable(current, retention)
        when = datetime.now(timezone.utc)
        stored = StoredRelationship(
            tenant_id=tenant_id,
            relationship=relationship,
            version=1 if current is None else current.version + 1,
            provenance=provenance,
            retention=retention,
            created_at=current.created_at if current else when,
            updated_at=when,
        )
        self._write_relationship(db, stored)
        self._append_event(
            db,
            tenant_id,
            "relationship",
            self._relationship_key(relationship),
            "created" if current is None else "updated",
            stored.version,
            when,
            provenance,
        )
        return stored

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise CompanyBrainVersionConflict(f"expected version {expected}, current version is {current}")

    @staticmethod
    def _assert_mutable(
        current: StoredEntity | StoredEvidence | StoredRelationship | None,
        requested_retention: RetentionPolicy,
    ) -> None:
        if current is None:
            return
        if current.deleted_at is not None:
            raise CompanyBrainStoreError("tombstoned records cannot be silently recreated")
        existing = current.retention
        if existing.legal_hold and not requested_retention.legal_hold:
            raise CompanyBrainRetentionError("legal hold cannot be removed by an ordinary update")
        if existing.retain_until is not None and (
            requested_retention.retain_until is None
            or requested_retention.retain_until < existing.retain_until
        ):
            raise CompanyBrainRetentionError("retention cannot be shortened by an ordinary update")

    @staticmethod
    def _assert_active_entity(db: sqlite3.Connection, tenant_id: str, entity_id: str) -> None:
        row = db.execute(
            "SELECT deleted_at FROM company_brain_entities WHERE tenant_id=? AND entity_id=?",
            (tenant_id, entity_id),
        ).fetchone()
        if row is None:
            raise CompanyBrainStoreError("relationship endpoints must exist in the same tenant")
        if row["deleted_at"] is not None:
            raise CompanyBrainStoreError("relationship endpoints must be active")

    @staticmethod
    def _assert_active_evidence(db: sqlite3.Connection, tenant_id: str, evidence_id: str) -> None:
        row = db.execute(
            "SELECT deleted_at FROM company_brain_evidence WHERE tenant_id=? AND evidence_id=?",
            (tenant_id, evidence_id),
        ).fetchone()
        if row is None:
            raise CompanyBrainStoreError("relationship evidence must exist in the same tenant")
        if row["deleted_at"] is not None:
            raise CompanyBrainStoreError("relationship evidence must be active")

    def _write_entity(self, db: sqlite3.Connection, record: StoredEntity) -> None:
        db.execute(
            """INSERT INTO company_brain_entities(
                   tenant_id, entity_id, payload, version, provenance, retain_until, legal_hold,
                   created_at, updated_at, deleted_at, deletion_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, entity_id) DO UPDATE SET
                   payload=excluded.payload, version=excluded.version, provenance=excluded.provenance,
                   retain_until=excluded.retain_until, legal_hold=excluded.legal_hold,
                   created_at=excluded.created_at, updated_at=excluded.updated_at,
                   deleted_at=excluded.deleted_at, deletion_reason=excluded.deletion_reason""",
            self._entity_values(record),
        )

    def _write_evidence(self, db: sqlite3.Connection, record: StoredEvidence) -> None:
        db.execute(
            """INSERT INTO company_brain_evidence(
                   tenant_id, evidence_id, payload, version, provenance, retain_until, legal_hold,
                   created_at, updated_at, deleted_at, deletion_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, evidence_id) DO UPDATE SET
                   payload=excluded.payload, version=excluded.version, provenance=excluded.provenance,
                   retain_until=excluded.retain_until, legal_hold=excluded.legal_hold,
                   created_at=excluded.created_at, updated_at=excluded.updated_at,
                   deleted_at=excluded.deleted_at, deletion_reason=excluded.deletion_reason""",
            self._evidence_values(record),
        )

    def _write_relationship(self, db: sqlite3.Connection, record: StoredRelationship) -> None:
        db.execute(
            """INSERT INTO company_brain_relationships(
                   tenant_id, source_id, target_id, relationship_kind, payload, version, provenance,
                   retain_until, legal_hold, created_at, updated_at, deleted_at, deletion_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, source_id, target_id, relationship_kind) DO UPDATE SET
                   payload=excluded.payload, version=excluded.version, provenance=excluded.provenance,
                   retain_until=excluded.retain_until, legal_hold=excluded.legal_hold,
                   created_at=excluded.created_at, updated_at=excluded.updated_at,
                   deleted_at=excluded.deleted_at, deletion_reason=excluded.deletion_reason""",
            self._relationship_values(record),
        )

    @staticmethod
    def _entity_values(record: StoredEntity) -> tuple[object, ...]:
        return (
            record.tenant_id,
            record.entity.entity_id,
            json.dumps(_entity_payload(record.entity), sort_keys=True),
            record.version,
            json.dumps(_provenance_payload(record.provenance), sort_keys=True),
            _timestamp_text(record.retention.retain_until) if record.retention.retain_until else None,
            int(record.retention.legal_hold),
            _timestamp_text(record.created_at),
            _timestamp_text(record.updated_at),
            _timestamp_text(record.deleted_at) if record.deleted_at else None,
            record.deletion_reason,
        )

    @staticmethod
    def _evidence_values(record: StoredEvidence) -> tuple[object, ...]:
        return (
            record.tenant_id,
            record.evidence.evidence_id,
            json.dumps(_evidence_payload(record.evidence), sort_keys=True),
            record.version,
            json.dumps(_provenance_payload(record.provenance), sort_keys=True),
            _timestamp_text(record.retention.retain_until) if record.retention.retain_until else None,
            int(record.retention.legal_hold),
            _timestamp_text(record.created_at),
            _timestamp_text(record.updated_at),
            _timestamp_text(record.deleted_at) if record.deleted_at else None,
            record.deletion_reason,
        )

    @staticmethod
    def _relationship_values(record: StoredRelationship) -> tuple[object, ...]:
        relationship = record.relationship
        return (
            record.tenant_id,
            relationship.source_id,
            relationship.target_id,
            relationship.kind.value,
            json.dumps(_relationship_payload(relationship), sort_keys=True),
            record.version,
            json.dumps(_provenance_payload(record.provenance), sort_keys=True),
            _timestamp_text(record.retention.retain_until) if record.retention.retain_until else None,
            int(record.retention.legal_hold),
            _timestamp_text(record.created_at),
            _timestamp_text(record.updated_at),
            _timestamp_text(record.deleted_at) if record.deleted_at else None,
            record.deletion_reason,
        )

    @staticmethod
    def _relationship_key(relationship: BrainRelationship) -> str:
        return f"{relationship.source_id}|{relationship.kind.value}|{relationship.target_id}"

    def _append_event(
        self,
        db: sqlite3.Connection,
        tenant_id: str,
        record_type: str,
        record_key: str,
        operation: str,
        version: int,
        occurred_at: datetime,
        provenance: BrainProvenance,
        deletion_reason: str | None = None,
    ) -> None:
        db.execute(
            """INSERT INTO company_brain_audit_events(
                   tenant_id, record_type, record_key, operation, version, occurred_at, provenance, deletion_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tenant_id,
                record_type,
                record_key,
                operation,
                version,
                _timestamp_text(occurred_at),
                json.dumps(_provenance_payload(provenance), sort_keys=True),
                deletion_reason,
            ),
        )

    @staticmethod
    def _entity_from_row(row: sqlite3.Row) -> StoredEntity:
        return StoredEntity(
            tenant_id=str(row["tenant_id"]),
            entity=_entity_from_payload(payload_from_json(str(row["payload"]), label="stored entity")),
            version=int(row["version"]),
            provenance=_provenance_from_payload(
                payload_from_json(str(row["provenance"]), label="stored entity provenance")
            ),
            retention=RetentionPolicy(
                retain_until=_parse_timestamp(row["retain_until"]) if row["retain_until"] else None,
                legal_hold=bool(row["legal_hold"]),
            ),
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            deleted_at=_parse_timestamp(row["deleted_at"]) if row["deleted_at"] else None,
            deletion_reason=row["deletion_reason"],
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> StoredEvidence:
        return StoredEvidence(
            tenant_id=str(row["tenant_id"]),
            evidence=_evidence_from_payload(payload_from_json(str(row["payload"]), label="stored evidence")),
            version=int(row["version"]),
            provenance=_provenance_from_payload(
                payload_from_json(str(row["provenance"]), label="stored evidence provenance")
            ),
            retention=RetentionPolicy(
                retain_until=_parse_timestamp(row["retain_until"]) if row["retain_until"] else None,
                legal_hold=bool(row["legal_hold"]),
            ),
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            deleted_at=_parse_timestamp(row["deleted_at"]) if row["deleted_at"] else None,
            deletion_reason=row["deletion_reason"],
        )

    @staticmethod
    def _relationship_from_row(row: sqlite3.Row) -> StoredRelationship:
        return StoredRelationship(
            tenant_id=str(row["tenant_id"]),
            relationship=_relationship_from_payload(
                payload_from_json(str(row["payload"]), label="stored relationship")
            ),
            version=int(row["version"]),
            provenance=_provenance_from_payload(
                payload_from_json(str(row["provenance"]), label="stored relationship provenance")
            ),
            retention=RetentionPolicy(
                retain_until=_parse_timestamp(row["retain_until"]) if row["retain_until"] else None,
                legal_hold=bool(row["legal_hold"]),
            ),
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            deleted_at=_parse_timestamp(row["deleted_at"]) if row["deleted_at"] else None,
            deletion_reason=row["deletion_reason"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> BrainAuditEvent:
        return BrainAuditEvent(
            sequence=int(row["sequence"]),
            tenant_id=str(row["tenant_id"]),
            record_type=str(row["record_type"]),
            record_key=str(row["record_key"]),
            operation=str(row["operation"]),
            version=int(row["version"]),
            occurred_at=_parse_timestamp(row["occurred_at"]),
            provenance=_provenance_from_payload(
                payload_from_json(str(row["provenance"]), label="stored audit provenance")
            ),
            deletion_reason=row["deletion_reason"],
        )


def _entity_payload(entity: BrainEntity) -> dict[str, object]:
    return {
        "entity_id": entity.entity_id,
        "kind": entity.kind.value,
        "label": entity.label,
        "attributes": list(entity.attributes),
    }


def _entity_from_payload(payload: Mapping[str, object]) -> BrainEntity:
    return BrainEntity(
        entity_id=required_text(payload, "entity_id", label="entity"),
        kind=EntityKind(required_text(payload, "kind", label="entity")),
        label=required_text(payload, "label", label="entity"),
        attributes=text_pairs(payload, "attributes", label="entity"),
    )


def _evidence_payload(evidence: BrainEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_kind": evidence.source_kind,
        "citation": evidence.citation,
        "revision": evidence.revision,
        "acl_groups": list(evidence.acl_groups),
        "acl_users": list(evidence.acl_users),
    }


def _evidence_from_payload(payload: Mapping[str, object]) -> BrainEvidence:
    return BrainEvidence(
        evidence_id=required_text(payload, "evidence_id", label="evidence"),
        source_kind=required_text(payload, "source_kind", label="evidence"),
        citation=required_text(payload, "citation", label="evidence"),
        revision=required_text(payload, "revision", label="evidence"),
        acl_groups=text_sequence(payload, "acl_groups", label="evidence"),
        acl_users=text_sequence(payload, "acl_users", label="evidence"),
    )


def _provenance_from_payload(payload: Mapping[str, object]) -> BrainProvenance:
    fields = provenance_fields(payload)
    return BrainProvenance(
        source_system=fields.source_system,
        source_record_id=fields.source_record_id,
        source_revision=fields.source_revision,
        observed_at=fields.observed_at,
        event_id=fields.event_id,
    )
