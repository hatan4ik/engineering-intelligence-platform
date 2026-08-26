"""The control-plane state/audit factory must be constructible in every valid mode."""
from __future__ import annotations

import pytest
from azure.cosmos import exceptions

from state.audit import SqliteAuditLog
from state.cosmos_audit import CosmosAuditLog
from state.cosmos_store import CosmosStateStore
from state.factory import (
    build_audit_log,
    build_state_store,
    missing_cosmos_configuration,
)
from state.store import SqliteStateStore


class FakeContainer:
    """Minimal in-memory stand-in for the Cosmos container protocol."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.etag = 0

    def read_item(self, item, partition_key):
        if item not in self.items:
            raise exceptions.CosmosResourceNotFoundError(status_code=404, message="missing")
        return dict(self.items[item])

    def create_item(self, body):
        self.etag += 1
        stored = {**body, "_etag": str(self.etag)}
        self.items[body["id"]] = stored
        return stored

    def replace_item(self, item, body, *, etag, match_condition):
        assert self.items[item]["_etag"] == etag
        self.etag += 1
        stored = {**body, "_etag": str(self.etag)}
        self.items[item] = stored
        return stored

    def execute_item_batch(self, batch_operations, partition_key):
        staged = dict(self.items)
        next_etag = self.etag
        for operation in batch_operations:
            name, args, *options = operation
            options = options[0] if options else {}
            if name == "create":
                body = args[0]
                if body["id"] in staged:
                    raise exceptions.CosmosResourceExistsError(status_code=409, message="exists")
                next_etag += 1
                staged[body["id"]] = {**body, "_etag": str(next_etag)}
            elif name == "replace":
                item, body = args
                if staged[item]["_etag"] != options["if_match_etag"]:
                    raise exceptions.CosmosAccessConditionFailedError(status_code=412, message="stale")
                next_etag += 1
                staged[item] = {**body, "_etag": str(next_etag)}
            else:
                raise AssertionError(f"unexpected batch operation: {name}")
        self.items = staged
        self.etag = next_etag
        return []


COSMOS_ENV = {
    "EIP_CONTROL_PLANE_MODE": "temporal",
    "EIP_COSMOS_ENDPOINT": "https://eip.documents.azure.invalid:443/",
    "EIP_COSMOS_DATABASE": "eip",
    "EIP_COSMOS_STATE_CONTAINER": "workflow-state",
    "EIP_COSMOS_AUDIT_CONTAINER": "workflow-audit",
}


def test_reference_mode_builds_the_sqlite_reference_backends(tmp_path):
    environ = {
        "EIP_CONTROL_PLANE_MODE": "reference",
        "EIP_STATE_DB_PATH": str(tmp_path / "state.db"),
        "EIP_AUDIT_DB_PATH": str(tmp_path / "audit.db"),
    }
    store = build_state_store(environ)
    audit = build_audit_log(environ)
    assert isinstance(store, SqliteStateStore)
    assert isinstance(audit, SqliteAuditLog)
    assert store.path == str(tmp_path / "state.db")
    assert audit.path == str(tmp_path / "audit.db")


def test_default_mode_is_reference(tmp_path):
    environ = {"EIP_STATE_DB_PATH": str(tmp_path / "state.db")}
    assert isinstance(build_state_store(environ), SqliteStateStore)


def test_disabled_mode_refuses_to_build_any_backend():
    environ = {"EIP_CONTROL_PLANE_MODE": "disabled"}
    with pytest.raises(RuntimeError, match="control plane disabled"):
        build_state_store(environ)
    with pytest.raises(RuntimeError, match="control plane disabled"):
        build_audit_log(environ)


def test_temporal_mode_lists_every_missing_cosmos_variable():
    environ = {"EIP_CONTROL_PLANE_MODE": "temporal"}
    assert missing_cosmos_configuration(environ) == (
        "EIP_COSMOS_ENDPOINT",
        "EIP_COSMOS_DATABASE",
        "EIP_COSMOS_STATE_CONTAINER",
        "EIP_COSMOS_AUDIT_CONTAINER",
    )
    with pytest.raises(RuntimeError) as excinfo:
        build_state_store(environ)
    message = str(excinfo.value)
    for name in ("EIP_COSMOS_ENDPOINT", "EIP_COSMOS_DATABASE", "EIP_COSMOS_STATE_CONTAINER"):
        assert name in message


def test_temporal_mode_reports_only_the_variables_that_are_absent():
    environ = dict(COSMOS_ENV)
    del environ["EIP_COSMOS_AUDIT_CONTAINER"]
    assert missing_cosmos_configuration(environ) == ("EIP_COSMOS_AUDIT_CONTAINER",)
    with pytest.raises(RuntimeError, match="EIP_COSMOS_AUDIT_CONTAINER"):
        build_audit_log(environ)


def test_temporal_mode_builds_cosmos_backed_state_and_audit():
    container = FakeContainer()
    store = build_state_store(COSMOS_ENV, cosmos_container=container)
    audit = build_audit_log(COSMOS_ENV, cosmos_container=container)
    assert isinstance(store, CosmosStateStore)
    assert isinstance(audit, CosmosAuditLog)


def test_temporal_mode_never_returns_a_sqlite_backend():
    container = FakeContainer()
    assert not isinstance(build_state_store(COSMOS_ENV, cosmos_container=container), SqliteStateStore)
    assert not isinstance(build_audit_log(COSMOS_ENV, cosmos_container=container), SqliteAuditLog)


def test_unknown_mode_is_rejected():
    with pytest.raises(RuntimeError):
        build_state_store({"EIP_CONTROL_PLANE_MODE": "production"})
