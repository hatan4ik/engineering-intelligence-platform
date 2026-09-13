"""Durable product-artifact outbox for external side effects.

Products record a complete, source-safe artifact before attempting an external
publication. Each delivery is leased, acknowledged, or returned for retry
independently, so one failed side effect cannot erase its finding or replay a
different completed side effect. This SQLite adapter is reference-only; a
managed implementation must preserve the same idempotency and lease rules.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Protocol

from control_plane.runtime import require_reference_storage

from .product_contracts import ProductContractError
from .sqlite import SqliteReferenceDatabase


class ArtifactOutboxError(ProductContractError):
    """Raised when an artifact delivery cannot preserve durable side-effect rules."""


class ArtifactDeliveryChannel(StrEnum):
    GITHUB_CHECK = "github_check"
    GITHUB_COMMENT = "github_comment"


class ArtifactDeliveryState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DELIVERED = "delivered"


_MAXIMUM_ARTIFACT_PAYLOAD_BYTES = 64 * 1024
_MAXIMUM_ARTIFACT_DELIVERIES = 32


@dataclass(frozen=True)
class ArtifactDeliveryIntent:
    """One idempotent external delivery belonging to an immutable artifact."""

    delivery_key: str
    channel: ArtifactDeliveryChannel
    idempotency_key: str
    payload_json: str

    def __post_init__(self) -> None:
        _identifier(self.delivery_key, "artifact delivery_key")
        if not isinstance(self.channel, ArtifactDeliveryChannel):
            raise ArtifactOutboxError("artifact delivery channel is invalid")
        _identifier(self.idempotency_key, "artifact idempotency_key")
        if _canonical_payload(self.payload_json) != self.payload_json:
            raise ArtifactOutboxError("artifact payload_json must be canonical JSON")
        if len(self.payload_json.encode("utf-8")) > _MAXIMUM_ARTIFACT_PAYLOAD_BYTES:
            raise ArtifactOutboxError("artifact payload_json exceeds the maximum size")


@dataclass(frozen=True)
class ProductArtifact:
    """The immutable product result recorded before external publication begins."""

    artifact_id: str
    product: str
    scope_id: str
    correlation_id: str
    context_version: str
    deliveries: tuple[ArtifactDeliveryIntent, ...]

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "product artifact_id")
        _product(self.product)
        _identifier(self.scope_id, "product artifact scope_id")
        _identifier(self.correlation_id, "product artifact correlation_id")
        _text(self.context_version, "product artifact context_version", maximum=240)
        if not self.deliveries:
            raise ArtifactOutboxError("a product artifact requires at least one delivery")
        if len(self.deliveries) > _MAXIMUM_ARTIFACT_DELIVERIES:
            raise ArtifactOutboxError("a product artifact exceeds the delivery limit")
        if self.deliveries != tuple(sorted(self.deliveries, key=lambda item: item.delivery_key)):
            raise ArtifactOutboxError("artifact deliveries must be sorted")
        if len({item.delivery_key for item in self.deliveries}) != len(self.deliveries):
            raise ArtifactOutboxError("artifact delivery_keys must be unique")
        if len({item.idempotency_key for item in self.deliveries}) != len(self.deliveries):
            raise ArtifactOutboxError("artifact idempotency_keys must be unique")

    def payload(self) -> dict[str, object]:
        """Return the canonical artifact audit record without any source bodies."""

        return {
            "artifact_id": self.artifact_id,
            "product": self.product,
            "scope_id": self.scope_id,
            "correlation_id": self.correlation_id,
            "context_version": self.context_version,
            "deliveries": [
                {
                    "delivery_key": item.delivery_key,
                    "channel": item.channel.value,
                    "idempotency_key": item.idempotency_key,
                    "payload_json": item.payload_json,
                }
                for item in self.deliveries
            ],
        }


@dataclass(frozen=True)
class LeasedArtifactDelivery:
    """One delivery lease held by a dispatcher for exactly one external attempt."""

    artifact_id: str
    product: str
    scope_id: str
    correlation_id: str
    context_version: str
    intent: ArtifactDeliveryIntent
    attempt: int
    lease_token: str
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "leased artifact_id")
        _product(self.product)
        _identifier(self.scope_id, "leased scope_id")
        _identifier(self.correlation_id, "leased correlation_id")
        _text(self.context_version, "leased context_version", maximum=240)
        if type(self.attempt) is not int or self.attempt < 1:
            raise ArtifactOutboxError("leased artifact attempt is invalid")
        _identifier(self.lease_token, "leased artifact lease_token")
        _utc(self.lease_expires_at, "leased artifact lease_expires_at")


@dataclass(frozen=True)
class ArtifactDeliveryStatus:
    """Durable delivery state returned for recovery and operational reporting."""

    artifact_id: str
    delivery_key: str
    state: ArtifactDeliveryState
    attempts: int
    available_at: datetime
    last_error: str | None
    delivered_at: datetime | None

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "artifact status artifact_id")
        _identifier(self.delivery_key, "artifact status delivery_key")
        if not isinstance(self.state, ArtifactDeliveryState):
            raise ArtifactOutboxError("artifact status state is invalid")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ArtifactOutboxError("artifact status attempts is invalid")
        _utc(self.available_at, "artifact status available_at")
        if self.last_error is not None:
            _text(self.last_error, "artifact status last_error", maximum=500)
        if self.delivered_at is not None:
            _utc(self.delivered_at, "artifact status delivered_at")


class ArtifactOutbox(Protocol):
    """Transactional artifact persistence and independently recoverable deliveries."""

    def record(self, artifact: ProductArtifact, *, recorded_at: datetime | None = None) -> bool: ...

    def claim_next(
        self,
        *,
        now: datetime | None = None,
        lease_duration: timedelta = timedelta(minutes=1),
        artifact_id: str | None = None,
    ) -> LeasedArtifactDelivery | None: ...

    def acknowledge(self, delivery: LeasedArtifactDelivery, *, delivered_at: datetime | None = None) -> None: ...

    def retry(
        self,
        delivery: LeasedArtifactDelivery,
        *,
        error: str,
        retry_at: datetime,
    ) -> None: ...

    def statuses(self, artifact_id: str) -> tuple[ArtifactDeliveryStatus, ...]: ...


class SqliteArtifactOutbox(SqliteReferenceDatabase):
    """Reference implementation of an atomic artifact-plus-delivery outbox."""

    def __init__(self, path: str | Path = "company-brain-artifact-outbox.db") -> None:
        require_reference_storage(type(self).__name__)
        self.path = str(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_brain_product_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    product TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    context_version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS company_brain_artifact_deliveries (
                    artifact_id TEXT NOT NULL,
                    delivery_key TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    available_at TEXT NOT NULL,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    delivered_at TEXT,
                    PRIMARY KEY (artifact_id, delivery_key),
                    UNIQUE (idempotency_key),
                    FOREIGN KEY (artifact_id) REFERENCES company_brain_product_artifacts(artifact_id)
                );
                CREATE INDEX IF NOT EXISTS idx_company_brain_artifact_delivery_ready
                    ON company_brain_artifact_deliveries(state, available_at, artifact_id, delivery_key);
                """
            )

    def record(self, artifact: ProductArtifact, *, recorded_at: datetime | None = None) -> bool:
        """Persist every planned delivery in the same transaction as its artifact."""

        payload = _canonical(artifact.payload())
        now = _utc(recorded_at or datetime.now(timezone.utc), "artifact recorded_at").isoformat()
        with self._connect() as database, self._immediate(database):
            row = database.execute(
                "SELECT payload FROM company_brain_product_artifacts WHERE artifact_id=?", (artifact.artifact_id,)
            ).fetchone()
            if row is not None:
                if str(row["payload"]) != payload:
                    raise ArtifactOutboxError("product artifact_id conflicts with retained history")
                return False
            database.execute(
                """INSERT INTO company_brain_product_artifacts(
                       artifact_id, product, scope_id, correlation_id, context_version, payload, recorded_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact.artifact_id,
                    artifact.product,
                    artifact.scope_id,
                    artifact.correlation_id,
                    artifact.context_version,
                    payload,
                    now,
                ),
            )
            for intent in artifact.deliveries:
                database.execute(
                    """INSERT INTO company_brain_artifact_deliveries(
                           artifact_id, delivery_key, channel, idempotency_key, payload_json, state,
                           attempts, available_at, lease_token, lease_expires_at, last_error, delivered_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                    (
                        artifact.artifact_id,
                        intent.delivery_key,
                        intent.channel.value,
                        intent.idempotency_key,
                        intent.payload_json,
                        ArtifactDeliveryState.PENDING.value,
                        0,
                        now,
                    ),
                )
        return True

    def claim_next(
        self,
        *,
        now: datetime | None = None,
        lease_duration: timedelta = timedelta(minutes=1),
        artifact_id: str | None = None,
    ) -> LeasedArtifactDelivery | None:
        """Lease one due delivery, recovering safely from an expired prior lease."""

        if (
            not isinstance(lease_duration, timedelta)
            or lease_duration <= timedelta(0)
            or lease_duration > timedelta(minutes=5)
        ):
            raise ArtifactOutboxError("artifact lease_duration is invalid")
        if artifact_id is not None:
            _identifier(artifact_id, "artifact_id")
        current = _utc(now or datetime.now(timezone.utc), "artifact claim time")
        current_text = current.isoformat()
        filter_sql = " AND delivery.artifact_id=?" if artifact_id is not None else ""
        query_parameters: tuple[object, ...] = (
            ArtifactDeliveryState.PENDING.value,
            current_text,
            ArtifactDeliveryState.LEASED.value,
            current_text,
            *((artifact_id,) if artifact_id is not None else ()),
        )
        with self._connect() as database, self._immediate(database):
            row = database.execute(
                f"""SELECT artifact.artifact_id, artifact.product, artifact.scope_id, artifact.correlation_id,
                           artifact.context_version, delivery.delivery_key, delivery.channel,
                           delivery.idempotency_key, delivery.payload_json, delivery.attempts
                    FROM company_brain_artifact_deliveries AS delivery
                    JOIN company_brain_product_artifacts AS artifact ON artifact.artifact_id=delivery.artifact_id
                    WHERE (
                        (delivery.state=? AND delivery.available_at<=?)
                        OR (delivery.state=? AND delivery.lease_expires_at<=?)
                    ){filter_sql}
                    ORDER BY delivery.available_at, delivery.artifact_id, delivery.delivery_key
                    LIMIT 1""",
                query_parameters,
            ).fetchone()
            if row is None:
                return None
            lease_token = "lease:" + uuid.uuid4().hex
            lease_expires_at = current + lease_duration
            attempt = int(row["attempts"]) + 1
            database.execute(
                """UPDATE company_brain_artifact_deliveries
                   SET state=?, attempts=?, lease_token=?, lease_expires_at=?, last_error=NULL
                   WHERE artifact_id=? AND delivery_key=?""",
                (
                    ArtifactDeliveryState.LEASED.value,
                    attempt,
                    lease_token,
                    lease_expires_at.isoformat(),
                    str(row["artifact_id"]),
                    str(row["delivery_key"]),
                ),
            )
        return LeasedArtifactDelivery(
            artifact_id=str(row["artifact_id"]),
            product=str(row["product"]),
            scope_id=str(row["scope_id"]),
            correlation_id=str(row["correlation_id"]),
            context_version=str(row["context_version"]),
            intent=ArtifactDeliveryIntent(
                delivery_key=str(row["delivery_key"]),
                channel=ArtifactDeliveryChannel(str(row["channel"])),
                idempotency_key=str(row["idempotency_key"]),
                payload_json=str(row["payload_json"]),
            ),
            attempt=attempt,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
        )

    def acknowledge(self, delivery: LeasedArtifactDelivery, *, delivered_at: datetime | None = None) -> None:
        """Mark one exact delivery lease complete after its external call returns."""

        timestamp = _utc(delivered_at or datetime.now(timezone.utc), "artifact delivered_at")
        with self._connect() as database, self._immediate(database):
            self._require_lease(database, delivery)
            database.execute(
                """UPDATE company_brain_artifact_deliveries
                   SET state=?, delivered_at=?, lease_token=NULL, lease_expires_at=NULL, last_error=NULL
                   WHERE artifact_id=? AND delivery_key=?""",
                (
                    ArtifactDeliveryState.DELIVERED.value,
                    timestamp.isoformat(),
                    delivery.artifact_id,
                    delivery.intent.delivery_key,
                ),
            )

    def retry(self, delivery: LeasedArtifactDelivery, *, error: str, retry_at: datetime) -> None:
        """Return an exact lease to the queue without losing its failure evidence."""

        _text(error, "artifact delivery error", maximum=500)
        retry_timestamp = _utc(retry_at, "artifact retry_at")
        with self._connect() as database, self._immediate(database):
            self._require_lease(database, delivery)
            database.execute(
                """UPDATE company_brain_artifact_deliveries
                   SET state=?, available_at=?, lease_token=NULL, lease_expires_at=NULL, last_error=?
                   WHERE artifact_id=? AND delivery_key=?""",
                (
                    ArtifactDeliveryState.PENDING.value,
                    retry_timestamp.isoformat(),
                    error,
                    delivery.artifact_id,
                    delivery.intent.delivery_key,
                ),
            )

    def statuses(self, artifact_id: str) -> tuple[ArtifactDeliveryStatus, ...]:
        """Read durable delivery state without leasing or retrying any work."""

        _identifier(artifact_id, "artifact_id")
        with self._connect() as database:
            rows = database.execute(
                """SELECT artifact_id, delivery_key, state, attempts, available_at, last_error, delivered_at
                   FROM company_brain_artifact_deliveries WHERE artifact_id=? ORDER BY delivery_key""",
                (artifact_id,),
            ).fetchall()
        return tuple(
            ArtifactDeliveryStatus(
                artifact_id=str(row["artifact_id"]),
                delivery_key=str(row["delivery_key"]),
                state=ArtifactDeliveryState(str(row["state"])),
                attempts=int(row["attempts"]),
                available_at=_parse_timestamp(str(row["available_at"]), "artifact status available_at"),
                last_error=str(row["last_error"]) if row["last_error"] is not None else None,
                delivered_at=(
                    _parse_timestamp(str(row["delivered_at"]), "artifact status delivered_at")
                    if row["delivered_at"] is not None
                    else None
                ),
            )
            for row in rows
        )

    @staticmethod
    def _require_lease(database: sqlite3.Connection, delivery: LeasedArtifactDelivery) -> None:
        row = database.execute(
            """SELECT state, lease_token FROM company_brain_artifact_deliveries
               WHERE artifact_id=? AND delivery_key=?""",
            (delivery.artifact_id, delivery.intent.delivery_key),
        ).fetchone()
        if row is None or row["state"] != ArtifactDeliveryState.LEASED.value:
            raise ArtifactOutboxError("artifact delivery is not currently leased")
        if str(row["lease_token"] or "") != delivery.lease_token:
            raise ArtifactOutboxError("artifact delivery lease token does not match")


def canonical_payload_json(payload: Mapping[str, object]) -> str:
    """Encode a product-owned, source-safe external payload deterministically."""

    return _canonical(payload)


def _canonical_payload(value: str) -> str:
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError as error:
        raise ArtifactOutboxError("artifact payload_json is not valid JSON") from error
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise ArtifactOutboxError("artifact payload_json must encode a JSON object")
    return _canonical(parsed)


def _canonical(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}", value):
        raise ArtifactOutboxError(f"{label} is invalid")
    return value


def _product(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value):
        raise ArtifactOutboxError("product artifact product is invalid")
    return value


def _text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\n" in value:
        raise ArtifactOutboxError(f"{label} is invalid")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ArtifactOutboxError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ArtifactOutboxError(f"{label} is invalid") from error
    return _utc(parsed, label)
