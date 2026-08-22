from __future__ import annotations

import os
from dataclasses import asdict, replace
from typing import Any, Protocol

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from state.models import ServiceRecord, WorkflowRecord, WorkflowStatus
from state.store import StateStore, VersionConflict


class ContainerLike(Protocol):
    def read_item(self, item: str, partition_key: str) -> dict[str, Any]: ...
    def create_item(self, body: dict[str, Any]) -> dict[str, Any]: ...
    def replace_item(self, item: str, body: dict[str, Any], *, etag: str, match_condition: Any) -> dict[str, Any]: ...


class CosmosStateStore(StateStore):
    """Production authoritative state adapter using Cosmos conditional writes.

    The model version remains an application CAS contract; Cosmos `_etag` adds a
    storage-level compare-and-swap guard so concurrent writers cannot silently
    overwrite each other.
    """

    def __init__(self, container: ContainerLike) -> None:
        self.container = container

    @classmethod
    def from_environment(cls) -> "CosmosStateStore":
        endpoint = os.environ["EIP_COSMOS_ENDPOINT"]
        database = os.environ["EIP_COSMOS_DATABASE"]
        container = os.environ["EIP_COSMOS_STATE_CONTAINER"]
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

    @staticmethod
    def _assert_expected(current: int | None, expected: int | None) -> None:
        if expected is not None and current != expected:
            raise VersionConflict(f"expected version {expected}, current version is {current}")
