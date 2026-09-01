from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from math import isfinite
from typing import Literal, Protocol, TypeAlias

from azure.core import MatchConditions
from azure.cosmos import ContainerProxy, CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from state.lifecycle import (
    LifecycleContractError,
    WorkflowLifecycleEvent,
    WorkflowTransitionResult,
)
from state.models import ServiceRecord, WorkflowRecord, WorkflowStatus
from state.store import StateStore, VersionConflict


CosmosItem = dict[str, object]
CosmosBatchOperation: TypeAlias = (
    tuple[Literal["create"], tuple[CosmosItem]]
    | tuple[Literal["replace"], tuple[str, CosmosItem], dict[str, str]]
)


class ContainerLike(Protocol):
    """The small Cosmos port needed by the authoritative state adapter."""

    def read_item(self, item: str, partition_key: str) -> CosmosItem: ...
    def create_item(self, body: CosmosItem) -> CosmosItem: ...
    def replace_item(
        self,
        item: str,
        body: CosmosItem,
        *,
        etag: str,
        match_condition: MatchConditions,
    ) -> CosmosItem: ...
    def execute_item_batch(
        self, batch_operations: Sequence[CosmosBatchOperation], partition_key: str
    ) -> object: ...


class AzureCosmosContainer:
    """Translate Azure's dynamically-shaped SDK boundary into the local port.

    The rest of the state package communicates only through ``ContainerLike``.
    This adapter is the one place where the Azure SDK's permissive payload
    types are narrowed to application-owned documents.
    """

    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    def read_item(self, item: str, partition_key: str) -> CosmosItem:
        return dict(self._container.read_item(item=item, partition_key=partition_key))

    def create_item(self, body: CosmosItem) -> CosmosItem:
        return dict(self._container.create_item(body=body))

    def replace_item(
        self,
        item: str,
        body: CosmosItem,
        *,
        etag: str,
        match_condition: MatchConditions,
    ) -> CosmosItem:
        return dict(
            self._container.replace_item(
                item=item,
                body=body,
                etag=etag,
                match_condition=match_condition,
            )
        )

    def execute_item_batch(
        self, batch_operations: Sequence[CosmosBatchOperation], partition_key: str
    ) -> object:
        return self._container.execute_item_batch(
            batch_operations=batch_operations,
            partition_key=partition_key,
        )


class CosmosStoredStateError(RuntimeError):
    """A Cosmos document cannot safely be restored into the state contract."""


def _mapping_field(payload: Mapping[str, object], field: str) -> CosmosItem:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise CosmosStoredStateError(f"Cosmos field {field!r} must be an object")
    return dict(value)


def _text_field(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be a non-blank string"
        )
    return value


def _optional_text_field(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be a non-blank string when set"
        )
    return value


def _integer_field(payload: Mapping[str, object], field: str, *, minimum: int) -> int:
    value = payload.get(field)
    if type(value) is not int or value < minimum:
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be an integer >= {minimum}"
        )
    return value


def _optional_float_field(payload: Mapping[str, object], field: str) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be a finite number when set"
        )
    result = float(value)
    if not isfinite(result):
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be a finite number when set"
        )
    return result


def _string_sequence_field(
    payload: Mapping[str, object], field: str
) -> tuple[str, ...]:
    value = payload.get(field, ())
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be a sequence of strings"
        )
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise CosmosStoredStateError(
                f"Cosmos field {field!r} must be a sequence of strings"
            )
        values.append(item)
    return tuple(values)


def _string_mapping_field(
    payload: Mapping[str, object], field: str
) -> Mapping[str, str]:
    value = payload.get(field, {})
    if not isinstance(value, Mapping):
        raise CosmosStoredStateError(
            f"Cosmos field {field!r} must be an object of strings"
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise CosmosStoredStateError(
                f"Cosmos field {field!r} must be an object of strings"
            )
        result[key] = item
    return result


def _service_from_payload(payload: Mapping[str, object]) -> ServiceRecord:
    return ServiceRecord(
        service_id=_text_field(payload, "service_id"),
        owner=_text_field(payload, "owner"),
        tier=_integer_field(payload, "tier", minimum=0),
        repositories=_string_sequence_field(payload, "repositories"),
        dependencies=_string_sequence_field(payload, "dependencies"),
        slo_target=_optional_float_field(payload, "slo_target"),
        autonomy_level=_integer_field(payload, "autonomy_level", minimum=0),
        metadata=_string_mapping_field(payload, "metadata"),
        version=_integer_field(payload, "version", minimum=1),
    )


def _workflow_from_payload(payload: Mapping[str, object]) -> WorkflowRecord:
    status = _text_field(payload, "status")
    try:
        workflow_status = WorkflowStatus(status)
    except ValueError as error:
        raise CosmosStoredStateError("Cosmos workflow status is invalid") from error
    return WorkflowRecord(
        workflow_id=_text_field(payload, "workflow_id"),
        service_id=_text_field(payload, "service_id"),
        environment=_text_field(payload, "environment"),
        kind=_text_field(payload, "kind"),
        status=workflow_status,
        correlation_id=_text_field(payload, "correlation_id"),
        plan_hash=_optional_text_field(payload, "plan_hash"),
        version=_integer_field(payload, "version", minimum=1),
        updated_at=_text_field(payload, "updated_at"),
        tenant_id=_text_field(payload, "tenant_id"),
    )


class CosmosStateStore(StateStore):
    """Production authoritative state adapter using Cosmos conditional writes.

    The model version remains an application CAS contract; Cosmos `_etag` adds a
    storage-level compare-and-swap guard so concurrent writers cannot silently
    overwrite each other.
    """

    def __init__(self, container: ContainerLike) -> None:
        self.container = container

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "CosmosStateStore":
        source = os.environ if environ is None else environ
        endpoint = source["EIP_COSMOS_ENDPOINT"]
        database = source["EIP_COSMOS_DATABASE"]
        container = source["EIP_COSMOS_STATE_CONTAINER"]
        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        raw_container = client.get_database_client(database).get_container_client(
            container
        )
        return cls(AzureCosmosContainer(raw_container))

    @staticmethod
    def _id(kind: str, key: str) -> str:
        return f"{kind}:{key}"

    def _read(self, kind: str, key: str) -> CosmosItem | None:
        item_id = self._id(kind, key)
        try:
            return dict(self.container.read_item(item=item_id, partition_key=item_id))
        except exceptions.CosmosResourceNotFoundError:
            return None

    def get_service(self, service_id: str) -> ServiceRecord | None:
        raw = self._read("service", service_id)
        if raw is None:
            return None
        return _service_from_payload(_mapping_field(raw, "payload"))

    def put_service(
        self, record: ServiceRecord, *, expected_version: int | None = None
    ) -> ServiceRecord:
        current = self._read("service", record.service_id)
        current_version = (
            None if current is None else _integer_field(current, "version", minimum=1)
        )
        self._assert_expected(current_version, expected_version)
        stored = replace(
            record, version=1 if current_version is None else current_version + 1
        )
        self._write(
            "service", record.service_id, asdict(stored), stored.version, current
        )
        return stored

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        raw = self._read("workflow", workflow_id)
        if raw is None:
            return None
        return _workflow_from_payload(_mapping_field(raw, "payload"))

    def put_workflow(
        self, record: WorkflowRecord, *, expected_version: int | None = None
    ) -> WorkflowRecord:
        current = self._read("workflow", record.workflow_id)
        current_version = (
            None if current is None else _integer_field(current, "version", minimum=1)
        )
        self._assert_expected(current_version, expected_version)
        stored = replace(
            record, version=1 if current_version is None else current_version + 1
        )
        self._write(
            "workflow", record.workflow_id, asdict(stored), stored.version, current
        )
        return stored

    def apply_workflow_event(
        self, event: WorkflowLifecycleEvent
    ) -> WorkflowTransitionResult:
        """Atomically store a workflow update and durable idempotency receipt.

        Both documents use the workflow item ID as their partition key, so a
        Cosmos transactional batch protects the compare-and-swap update and
        receipt creation from partial commits. A retry reads the receipt before
        considering the current workflow version.
        """

        event.validate()
        workflow_item_id = self._id("workflow", event.workflow_id)
        receipt_id = self._receipt_id(event.idempotency_key)
        receipt = self._read_item(receipt_id, workflow_item_id)
        if receipt is not None:
            return self._replayed_transition(event, receipt)

        current = self._read_item(workflow_item_id, workflow_item_id)
        current_record = self._workflow_from_raw(current) if current else None
        self._assert_expected(
            current_record.version if current_record else None, event.expected_version
        )
        try:
            candidate = event.apply_to(current_record)
        except LifecycleContractError as exc:
            raise VersionConflict(str(exc)) from exc
        stored = replace(
            candidate,
            version=1 if current_record is None else current_record.version + 1,
        )
        workflow_body: CosmosItem = {
            "id": workflow_item_id,
            "partition_key": workflow_item_id,
            "kind": "workflow",
            "version": stored.version,
            "payload": asdict(stored),
        }
        receipt_body: CosmosItem = {
            "id": receipt_id,
            "partition_key": workflow_item_id,
            "kind": "workflow-transition-receipt",
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "event_fingerprint": event.fingerprint,
            "workflow_payload": asdict(stored),
        }
        try:
            operations: list[CosmosBatchOperation]
            if current is None:
                operations = [
                    ("create", (workflow_body,)),
                    ("create", (receipt_body,)),
                ]
            else:
                operations = [
                    (
                        "replace",
                        (workflow_item_id, workflow_body),
                        {"if_match_etag": _text_field(current, "_etag")},
                    ),
                    ("create", (receipt_body,)),
                ]
            self.container.execute_item_batch(
                operations, partition_key=workflow_item_id
            )
        except (
            exceptions.CosmosBatchOperationError,
            exceptions.CosmosAccessConditionFailedError,
            exceptions.CosmosResourceExistsError,
        ) as exc:
            recovered = self._read_item(receipt_id, workflow_item_id)
            if recovered is not None:
                return self._replayed_transition(event, recovered)
            raise VersionConflict(
                "Cosmos lifecycle transition conditional write conflict"
            ) from exc
        return WorkflowTransitionResult(
            record=stored,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
        )

    def _write(
        self,
        kind: str,
        key: str,
        payload: Mapping[str, object],
        version: int,
        current: CosmosItem | None,
    ) -> None:
        item_id = self._id(kind, key)
        body: CosmosItem = {
            "id": item_id,
            "partition_key": item_id,
            "kind": kind,
            "version": version,
            "payload": dict(payload),
        }
        try:
            if current is None:
                self.container.create_item(body=body)
            else:
                self.container.replace_item(
                    item=item_id,
                    body=body,
                    etag=_text_field(current, "_etag"),
                    match_condition=MatchConditions.IfNotModified,
                )
        except (
            exceptions.CosmosAccessConditionFailedError,
            exceptions.CosmosResourceExistsError,
        ) as exc:
            raise VersionConflict("Cosmos conditional write conflict") from exc

    def _read_item(self, item_id: str, partition_key: str) -> CosmosItem | None:
        try:
            return dict(
                self.container.read_item(item=item_id, partition_key=partition_key)
            )
        except exceptions.CosmosResourceNotFoundError:
            return None

    @staticmethod
    def _receipt_id(idempotency_key: str) -> str:
        return (
            "workflow-transition:"
            + hashlib.sha256(idempotency_key.encode()).hexdigest()
        )

    @staticmethod
    def _workflow_from_raw(raw: CosmosItem) -> WorkflowRecord:
        return _workflow_from_payload(_mapping_field(raw, "payload"))

    @classmethod
    def _replayed_transition(
        cls, event: WorkflowLifecycleEvent, receipt: CosmosItem
    ) -> WorkflowTransitionResult:
        if (
            _text_field(receipt, "event_id") != event.event_id
            or _text_field(receipt, "event_fingerprint") != event.fingerprint
        ):
            raise VersionConflict(
                "idempotency key has already been used for a different workflow event"
            )
        return WorkflowTransitionResult(
            record=_workflow_from_payload(_mapping_field(receipt, "workflow_payload")),
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            replayed=True,
        )

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise VersionConflict(
                f"expected version {expected}, current version is {current}"
            )
