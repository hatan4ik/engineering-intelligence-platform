"""Runtime-profile guardrails for the control plane.

The repository keeps SQLite implementations for deterministic tests and local
reference exercises. They are intentionally not a production fallback: a
Temporal-backed runtime must be configured explicitly before it can start a
durable worker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class ControlPlaneConfigurationError(RuntimeError):
    """Raised when a control-plane runtime would be unsafe or ambiguous."""


REFERENCE_MODE = "reference"
TEMPORAL_MODE = "temporal"
DISABLED_MODE = "disabled"
_VALID_MODES = frozenset({REFERENCE_MODE, TEMPORAL_MODE, DISABLED_MODE})


def control_plane_mode(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    mode = source.get("EIP_CONTROL_PLANE_MODE", REFERENCE_MODE).strip().lower()
    if mode not in _VALID_MODES:
        raise ControlPlaneConfigurationError(
            "EIP_CONTROL_PLANE_MODE must be one of: disabled, reference, temporal"
        )
    return mode


def require_reference_storage(component: str, environ: Mapping[str, str] | None = None) -> None:
    """Prevent a local SQLite backend from being constructed for Temporal mode."""

    if control_plane_mode(environ) == TEMPORAL_MODE:
        raise ControlPlaneConfigurationError(
            f"{component} is a reference-only backend; Temporal mode requires managed durable dependencies"
        )


@dataclass(frozen=True)
class TemporalControlPlaneSettings:
    """Explicit production-worker configuration, with no local fallback values."""

    temporal_endpoint: str
    temporal_namespace: str
    temporal_task_queue: str
    temporal_tls_server_name: str
    temporal_tls_ca_cert_path: str
    temporal_tls_client_cert_path: str
    temporal_tls_client_key_path: str
    cosmos_endpoint: str
    cosmos_database: str
    cosmos_state_container: str
    immutable_audit_evidence_uri: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "TemporalControlPlaneSettings":
        source = os.environ if environ is None else environ
        if control_plane_mode(source) != TEMPORAL_MODE:
            raise ControlPlaneConfigurationError(
                "Temporal control-plane settings require EIP_CONTROL_PLANE_MODE=temporal"
            )

        required = {
            "temporal_endpoint": "EIP_TEMPORAL_ENDPOINT",
            "temporal_namespace": "EIP_TEMPORAL_NAMESPACE",
            "temporal_task_queue": "EIP_TEMPORAL_TASK_QUEUE",
            "temporal_tls_server_name": "EIP_TEMPORAL_TLS_SERVER_NAME",
            "temporal_tls_ca_cert_path": "EIP_TEMPORAL_TLS_CA_CERT_PATH",
            "temporal_tls_client_cert_path": "EIP_TEMPORAL_TLS_CLIENT_CERT_PATH",
            "temporal_tls_client_key_path": "EIP_TEMPORAL_TLS_CLIENT_KEY_PATH",
            "cosmos_endpoint": "EIP_COSMOS_ENDPOINT",
            "cosmos_database": "EIP_COSMOS_DATABASE",
            "cosmos_state_container": "EIP_COSMOS_STATE_CONTAINER",
            "immutable_audit_evidence_uri": "EIP_IMMUTABLE_AUDIT_EVIDENCE_URI",
        }
        values = {field: source.get(variable, "").strip() for field, variable in required.items()}
        missing = [variable for field, variable in required.items() if not values[field]]
        if missing:
            raise ControlPlaneConfigurationError(
                "Temporal control plane is incomplete; required: " + ", ".join(missing)
            )
        if values["immutable_audit_evidence_uri"].lower().startswith("file:"):
            raise ControlPlaneConfigurationError("immutable audit evidence must use an approved remote store, not file:")
        if "://" in values["temporal_endpoint"] or "/" in values["temporal_endpoint"]:
            raise ControlPlaneConfigurationError("EIP_TEMPORAL_ENDPOINT must be a host:port, not a URL")
        for key in (
            "temporal_tls_ca_cert_path",
            "temporal_tls_client_cert_path",
            "temporal_tls_client_key_path",
        ):
            if not values[key].startswith("/"):
                raise ControlPlaneConfigurationError(f"{required[key]} must be an absolute mounted-file path")
        return cls(**values)
