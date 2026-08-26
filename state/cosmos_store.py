from __future__ import annotations

import os
from dataclasses import asdict, replace
import hashlib
from typing import Any, Mapping, Protocol

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from state.lifecycle import LifecycleContractError, WorkflowLifecycleEvent, WorkflowTransitionResult
from state.models import ServiceRecord, WorkflowRecord, WorkflowStatus
from state.store import StateStore, VersionConflict


class ContainerLike(Protocol):
    def read_item(self, item: str, partition_key: str) -> dict[str, Any]: ...
    def create_item(self, body: dict[str, Any]) -> dict[str, Any]: ...
    def replace_item(self, item: str, body: dict[str, Any], *, etag: str, match_condition: Any) -> dict[str, Any]: ...
    def execute_item_batch(self, batch_operations: list[tuple[Any, ...]], partition_key: str) -> Any: ...


class CosmosStateStore(StateStore):
    """Production authoritative state adapter using Cosmos conditional writes.

    The model version remains an application CAS contract; Cosmos `_etag` adds a
    storage-level compare-and-swap guard so concurrent writers cannot silently
    overwrite each other.
    """

    def __init__(self, container: ContainerLike) -> None:
        self.container = container

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "CosmosStateStore":
        source = os.environ if environ is None else environ
        endpoint = source["EIP_COSMOS_ENDPOINT"]
        database = source["EIP_COSMOS_DATABASE"]
        container = source["EIP_COSMOS_STATE_CONTAINER"]
        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        return cls(client.get_database_client(database).get_container_client(container))

    @staticmethod
    def _id(kind: str, key: str) -> str:
        return f"{kind}:{key}"

    def _read(self, kind: str, key: str) -> dict[str, Any] | None:
        item_id = self._id(kind, key)
        try:
            return self.container.read_item(item=item_id, partition_key=item_id)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def get_service(self, service_id: str) -> ServiceRecord | None:
        raw = self._read("service", service_id)
        if raw is None:
            return None
        payload = dict(raw["payload"])
        payload["repositories"] = tuple(payload.get("repositories", ()))
        payload["dependencies"] = tuple(payload.get("dependencies", ()))
        return ServiceRecord(**payload)

    def put_service(self, record: ServiceRecord, *, expected_version: int | None = None) -> ServiceRecord:
        current = self._read("service", record.service_id)
        current_version = int(current["version"]) if current else None
        self._assert_expected(current_version, expected_version)
        stored = replace(record, version=1 if current is None else current_version + 1)
        self._write("service", record.service_id, asdict(stored), stored.version, current)
        return stored

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        raw = self._read("workflow", workflow_id)
        if raw is None:
            return None
        payload = dict(raw["payload"])
        payload["status"] = WorkflowStatus(payload["status"])
        return WorkflowRecord(**payload)

    def put_workflow(self, record: WorkflowRecord, *, expected_version: int | None = None) -> WorkflowRecord:
        current = self._read("workflow", record.workflow_id)
        current_version = int(current["version"]) if current else None
        self._assert_expected(current_version, expected_version)
        stored = replace(record, version=1 if current is None else current_version + 1)
        self._write("workflow", record.workflow_id, asdict(stored), stored.version, current)
        return stored

    def apply_workflow_event(self, event: WorkflowLifecycleEvent) -> WorkflowTransitionResult:
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
        self._assert_expected(current_record.version if current_record else None, event.expected_version)
        try:
            candidate = event.apply_to(current_record)
        except LifecycleContractError as exc:
            raise VersionConflict(str(exc)) from exc
        stored = replace(candidate, version=1 if current_record is None else current_record.version + 1)
        workflow_body = {
            "id": workflow_item_id,
            "partition_key": workflow_item_id,
            "kind": "workflow",
            "version": stored.version,
            "payload": asdict(stored),
        }
        receipt_body = {
            "id": receipt_id,
            "partition_key": workflow_item_id,
            "kind": "workflow-transition-receipt",
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "event_fingerprint": event.fingerprint,
            "workflow_payload": asdict(stored),
        }
        try:
            if current is None:
                operations: list[tuple[Any, ...]] = [
                    ("create", (workflow_body,)),
                    ("create", (receipt_body,)),
                ]
            else:
                operations = [
                    ("replace", (workflow_item_id, workflow_body), {"if_match_etag": str(current["_etag"])}),
                    ("create", (receipt_body,)),
                ]
            self.container.execute_item_batch(operations, partition_key=workflow_item_id)
        except (
            exceptions.CosmosBatchOperationError,
            exceptions.CosmosAccessConditionFailedError,
            exceptions.CosmosResourceExistsError,
        ) as exc:
            recovered = self._read_item(receipt_id, workflow_item_id)
            if recovered is not None:
                return self._replayed_transition(event, recovered)
            raise VersionConflict("Cosmos lifecycle transition conditional write conflict") from exc
        return WorkflowTransitionResult(
            record=stored,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
        )

    def _write(self, kind: str, key: str, payload: dict[str, Any], version: int, current: dict[str, Any] | None) -> None:
        item_id = self._id(kind, key)
        body = {"id": item_id, "partition_key": item_id, "kind": kind, "version": version, "payload": payload}
        try:
            if current is None:
                self.container.create_item(body=body)
            else:
                self.container.replace_item(
                    item=item_id,
                    body=body,
                    etag=str(current["_etag"]),
                    match_condition=MatchConditions.IfNotModified,
                )
        except (exceptions.CosmosAccessConditionFailedError, exceptions.CosmosResourceExistsError) as exc:
            raise VersionConflict("Cosmos conditional write conflict") from exc

    def _read_item(self, item_id: str, partition_key: str) -> dict[str, Any] | None:
        try:
            return self.container.read_item(item=item_id, partition_key=partition_key)
        except exceptions.CosmosResourceNotFoundError:
            return None

    @staticmethod
    def _receipt_id(idempotency_key: str) -> str:
        return "workflow-transition:" + hashlib.sha256(idempotency_key.encode()).hexdigest()

    @staticmethod
    def _workflow_from_raw(raw: dict[str, Any]) -> WorkflowRecord:
        payload = dict(raw["payload"])
        payload["status"] = WorkflowStatus(payload["status"])
        return WorkflowRecord(**payload)

    @classmethod
    def _replayed_transition(
        cls, event: WorkflowLifecycleEvent, receipt: dict[str, Any]
    ) -> WorkflowTransitionResult:
        if receipt.get("event_id") != event.event_id or receipt.get("event_fingerprint") != event.fingerprint:
            raise VersionConflict("idempotency key has already been used for a different workflow event")
        payload = dict(receipt["workflow_payload"])
        payload["status"] = WorkflowStatus(payload["status"])
        return WorkflowTransitionResult(
            record=WorkflowRecord(**payload),
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            replayed=True,
        )

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise VersionConflict(f"expected version {expected}, current version is {current}")
