"""Construct the authoritative state and audit backends for the active mode.

``EIP_CONTROL_PLANE_MODE`` selects the backend pair:

``reference``
    Local SQLite implementations. Deterministic, single-process, not a
    production control plane.
``temporal``
    Cosmos-backed implementations. The SQLite backends refuse construction in
    this mode (:func:`control_plane.runtime.require_reference_storage`), so
    without this factory ``ControlPlaneWorkflows`` could not be built at all.
``disabled``
    No backend exists; construction is an error.

Nothing here degrades silently. A ``temporal`` deployment missing Cosmos
configuration raises with every absent variable named, per the platform's
fail-closed configuration rule.

The ``environ`` argument exists for tests and for callers that build a runtime
from an explicit mapping. The SQLite backends independently consult the real
process environment through
:func:`control_plane.runtime.require_reference_storage`, so passing a
``reference`` mapping inside a ``temporal`` process still refuses to construct a
local backend. That asymmetry is deliberate: the process-wide mode wins.
"""
from __future__ import annotations

import os
from typing import Mapping

from control_plane.runtime import (
    DISABLED_MODE,
    REFERENCE_MODE,
    TEMPORAL_MODE,
    control_plane_mode,
)
from state.audit import AuditLog, SqliteAuditLog
from state.cosmos_audit import CosmosAuditLog
from state.cosmos_store import ContainerLike, CosmosStateStore
from state.store import SqliteStateStore, StateStore


COSMOS_STATE_VARIABLES: tuple[str, ...] = (
    "EIP_COSMOS_ENDPOINT",
    "EIP_COSMOS_DATABASE",
    "EIP_COSMOS_STATE_CONTAINER",
)
COSMOS_AUDIT_VARIABLES: tuple[str, ...] = (
    "EIP_COSMOS_ENDPOINT",
    "EIP_COSMOS_DATABASE",
    "EIP_COSMOS_AUDIT_CONTAINER",
)
COSMOS_VARIABLES: tuple[str, ...] = (
    "EIP_COSMOS_ENDPOINT",
    "EIP_COSMOS_DATABASE",
    "EIP_COSMOS_STATE_CONTAINER",
    "EIP_COSMOS_AUDIT_CONTAINER",
)

DEFAULT_STATE_DB_PATH = "eip-state.db"
DEFAULT_AUDIT_DB_PATH = "eip-audit.db"


def _source(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _missing(source: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if not str(source.get(name, "")).strip())


def missing_cosmos_configuration(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Cosmos variables required for Temporal mode that are absent or blank."""

    return _missing(_source(environ), COSMOS_VARIABLES)


def cosmos_backends_available(environ: Mapping[str, str] | None = None) -> bool:
    """True when Temporal mode is selected and Cosmos state and audit can be built."""

    source = _source(environ)
    return control_plane_mode(source) == TEMPORAL_MODE and not missing_cosmos_configuration(source)


def _require(source: Mapping[str, str], names: tuple[str, ...], component: str) -> None:
    missing = _missing(source, names)
    if missing:
        raise RuntimeError(
            f"{component} requires Cosmos configuration in Temporal mode; missing: "
            + ", ".join(missing)
        )


def build_state_store(
    environ: Mapping[str, str] | None = None,
    *,
    cosmos_container: ContainerLike | None = None,
) -> StateStore:
    """Return the authoritative state store for the configured mode."""

    source = _source(environ)
    mode = control_plane_mode(source)
    if mode == DISABLED_MODE:
        raise RuntimeError("control plane disabled")
    if mode == REFERENCE_MODE:
        return SqliteStateStore(source.get("EIP_STATE_DB_PATH") or DEFAULT_STATE_DB_PATH)
    _require(source, COSMOS_STATE_VARIABLES, "authoritative state store")
    if cosmos_container is not None:
        return CosmosStateStore(cosmos_container)
    return CosmosStateStore.from_environment(source)


def build_audit_log(
    environ: Mapping[str, str] | None = None,
    *,
    cosmos_container: ContainerLike | None = None,
) -> AuditLog:
    """Return the append-only audit log for the configured mode."""

    source = _source(environ)
    mode = control_plane_mode(source)
    if mode == DISABLED_MODE:
        raise RuntimeError("control plane disabled")
    if mode == REFERENCE_MODE:
        return SqliteAuditLog(source.get("EIP_AUDIT_DB_PATH") or DEFAULT_AUDIT_DB_PATH)
    _require(source, COSMOS_AUDIT_VARIABLES, "immutable audit log")
    if cosmos_container is not None:
        return CosmosAuditLog(
            cosmos_container,
            partition_key=str(source.get("EIP_COSMOS_AUDIT_PARTITION") or "eip-audit-chain"),
        )
    return CosmosAuditLog.from_environment(source)
