"""Cosmos-backed append-only audit log with SQLite-identical hash-chain semantics.

The reference :class:`state.audit.SqliteAuditLog` serialises appends with a
write transaction so two appenders cannot link to the same predecessor. Cosmos
has no equivalent table lock, so the chain tip is itself a document in the same
logical partition as the events, and every append is a transactional batch that
writes the new event and conditionally replaces the tip on its ``_etag``. A
racing appender therefore loses the conditional replace and retries against the
new tip instead of forking the chain.

Hash computation and idempotent-replay identity are imported from
:mod:`state.audit` rather than reimplemented, so the two sinks cannot drift.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, replace
from typing import Any, Mapping

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from state.audit import AuditConflict, AuditLog, compute_event_hash
# Private on purpose: it is the canonical replay identity of an audit event and
# must stay byte-identical between the reference and managed sinks.
from state.audit import _event_identity
from state.cosmos_store import ContainerLike
from state.models import AuditEvent


AUDIT_PARTITION_KEY = "eip-audit-chain"
_TIP_ID = "audit-chain:tip"
_MAX_TIP_ATTEMPTS = 8


class CosmosAuditLog(AuditLog):
    """Append-only hash-chained audit log stored in a single Cosmos partition."""

    def __init__(self, container: ContainerLike, *, partition_key: str = AUDIT_PARTITION_KEY) -> None:
        self.container = container
        self.partition_key = partition_key

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "CosmosAuditLog":
        source = os.environ if environ is None else environ
        required = ("EIP_COSMOS_ENDPOINT", "EIP_COSMOS_DATABASE", "EIP_COSMOS_AUDIT_CONTAINER")
        missing = [name for name in required if not str(source.get(name, "")).strip()]
        if missing:
            raise RuntimeError(
                "Cosmos audit log is not configured; required: " + ", ".join(missing)
            )
        client = CosmosClient(source["EIP_COSMOS_ENDPOINT"], credential=DefaultAzureCredential())
        container = (
            client.get_database_client(source["EIP_COSMOS_DATABASE"])
            .get_container_client(source["EIP_COSMOS_AUDIT_CONTAINER"])
        )
        return cls(container, partition_key=str(source.get("EIP_COSMOS_AUDIT_PARTITION") or AUDIT_PARTITION_KEY))

    @staticmethod
    def _event_item_id(event_id: str) -> str:
        return "audit-event:" + hashlib.sha256(event_id.encode()).hexdigest()

    def _read(self, item_id: str) -> dict[str, Any] | None:
        try:
            return self.container.read_item(item=item_id, partition_key=self.partition_key)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def append(self, event: AuditEvent) -> AuditEvent:
        item_id = self._event_item_id(event.event_id)
        for _ in range(_MAX_TIP_ATTEMPTS):
            tip = self._read(_TIP_ID)
            previous = str(tip["event_hash"]) if tip else None
            sequence = int(tip["sequence"]) + 1 if tip else 1
            candidate = replace(event, previous_hash=previous, event_hash=None)
            finalized = replace(candidate, event_hash=compute_event_hash(candidate))
            operations: list[tuple[Any, ...]] = [
                (
                    "create",
                    (
                        {
                            "id": item_id,
                            "partition_key": self.partition_key,
                            "kind": "audit-event",
                            "sequence": sequence,
                            "event_id": finalized.event_id,
                            "event_hash": finalized.event_hash,
                            "payload": asdict(finalized),
                        },
                    ),
                )
            ]
            tip_body = {
                "id": _TIP_ID,
                "partition_key": self.partition_key,
                "kind": "audit-chain-tip",
                "sequence": sequence,
                "event_id": finalized.event_id,
                "event_hash": finalized.event_hash,
            }
            if tip is None:
                operations.append(("create", (tip_body,)))
            else:
                operations.append(("replace", (_TIP_ID, tip_body), {"if_match_etag": str(tip["_etag"])}))
            try:
                self.container.execute_item_batch(operations, partition_key=self.partition_key)
            except (
                exceptions.CosmosBatchOperationError,
                exceptions.CosmosAccessConditionFailedError,
                exceptions.CosmosResourceExistsError,
            ) as exc:
                stored = self._read(item_id)
                if stored is not None:
                    return self._replayed(event, stored, exc)
                continue
            return finalized
        raise RuntimeError("audit chain tip could not be advanced; refusing to append without a linked predecessor")

    @staticmethod
    def _replayed(event: AuditEvent, stored: Mapping[str, Any], cause: Exception) -> AuditEvent:
        restored = AuditEvent(**dict(stored["payload"]))
        if _event_identity(restored) != _event_identity(event):
            raise AuditConflict(
                "audit event id has already been used for different content"
            ) from cause
        return restored

    def last_hash(self) -> str | None:
        tip = self._read(_TIP_ID)
        return str(tip["event_hash"]) if tip else None

    def event_count(self) -> int:
        tip = self._read(_TIP_ID)
        return int(tip["sequence"]) if tip else 0
