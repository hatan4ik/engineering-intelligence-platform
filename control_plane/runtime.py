"""Runtime-profile guardrails for the control plane.

The repository keeps SQLite implementations for deterministic tests and local
reference exercises. They are intentionally not a production fallback: a
Temporal-backed runtime must be configured explicitly before it can start a
durable worker. Each worker declares only the dependencies it actually uses;
the future state/audit activity bridge will have its own configuration contract.
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
class TemporalWorkerSettings:
    """Configuration for the current non-consequential Temporal worker.

    This worker registers only the evidence workflow, so it requires Temporal
    scheduling and mTLS configuration only. Cosmos and immutable-audit
    configuration are deliberately reserved for the future activity bridge.
    """

    temporal_endpoint: str
    temporal_namespace: str
    temporal_task_queue: str
    temporal_tls_server_name: str
    temporal_tls_ca_cert_path: str
    temporal_tls_client_cert_path: str
    temporal_tls_client_key_path: str
    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "TemporalWorkerSettings":
        source = os.environ if environ is None else environ
        if control_plane_mode(source) != TEMPORAL_MODE:
            raise ControlPlaneConfigurationError(
                "Temporal worker settings require EIP_CONTROL_PLANE_MODE=temporal"
            )

        required = {
            "temporal_endpoint": "EIP_TEMPORAL_ENDPOINT",
            "temporal_namespace": "EIP_TEMPORAL_NAMESPACE",
            "temporal_task_queue": "EIP_TEMPORAL_TASK_QUEUE",
            "temporal_tls_server_name": "EIP_TEMPORAL_TLS_SERVER_NAME",
            "temporal_tls_ca_cert_path": "EIP_TEMPORAL_TLS_CA_CERT_PATH",
            "temporal_tls_client_cert_path": "EIP_TEMPORAL_TLS_CLIENT_CERT_PATH",
            "temporal_tls_client_key_path": "EIP_TEMPORAL_TLS_CLIENT_KEY_PATH",
        }
        values = {field: source.get(variable, "").strip() for field, variable in required.items()}
        missing = [variable for field, variable in required.items() if not values[field]]
        if missing:
            raise ControlPlaneConfigurationError(
                "Temporal worker is incomplete; required: " + ", ".join(missing)
            )
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
