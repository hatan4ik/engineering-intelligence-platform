import asyncio

import pytest

pytest.importorskip("temporalio")

from control_plane.runtime import TemporalControlPlaneSettings
from orchestration.temporal_worker import connect_temporal, temporal_tls_config
from orchestration.temporal_workflow import ControlPlaneEvidenceRequest


def settings(tmp_path):
    ca = tmp_path / "ca.crt"
    cert = tmp_path / "tls.crt"
    key = tmp_path / "tls.key"
    ca.write_text("-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----\n")
    cert.write_text("-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----\n")
    key.write_text("-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----\n")
    return TemporalControlPlaneSettings(
        temporal_endpoint="temporal-frontend.eip-system.svc:7233",
        temporal_namespace="eip",
        temporal_task_queue="eip-control-plane",
        temporal_tls_server_name="temporal-frontend.eip-system.svc",
        temporal_tls_ca_cert_path=str(ca),
        temporal_tls_client_cert_path=str(cert),
        temporal_tls_client_key_path=str(key),
        cosmos_endpoint="https://eip.documents.azure.com",
        cosmos_database="eip",
        cosmos_state_container="state",
        immutable_audit_evidence_uri="https://audit.example/eip",
    )


def test_temporal_worker_loads_mtls_only_from_mounted_files(tmp_path):
    tls = temporal_tls_config(settings(tmp_path))
    assert tls.domain == "temporal-frontend.eip-system.svc"
    assert tls.server_root_ca_cert.startswith(b"-----BEGIN CERTIFICATE-----")
    assert tls.client_private_key.startswith(b"-----BEGIN PRIVATE KEY-----")


def test_temporal_client_uses_namespace_mtls_and_fixed_identity(tmp_path):
    captured = {}

    async def connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "client"

    result = asyncio.run(connect_temporal(settings(tmp_path), connect=connect))
    assert result == "client"
    assert captured["args"] == ("temporal-frontend.eip-system.svc:7233",)
    assert captured["kwargs"]["namespace"] == "eip"
    assert captured["kwargs"]["identity"] == "eip-control-plane-worker"
    assert captured["kwargs"]["tls"].client_cert.startswith(b"-----BEGIN CERTIFICATE-----")


def test_evidence_workflow_request_is_bounded_and_non_consequential():
    request = ControlPlaneEvidenceRequest(request_id="proof:2026-08-26", correlation_id="corr-42")
    assert request.workflow_id == "eip-control-plane-evidence:proof:2026-08-26"
    with pytest.raises(ValueError, match="opaque identifier"):
        ControlPlaneEvidenceRequest(request_id="bad value", correlation_id="corr-42").validate()
