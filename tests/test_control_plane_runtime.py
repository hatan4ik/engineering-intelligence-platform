import pytest

from control_plane.runtime import ControlPlaneConfigurationError, TemporalControlPlaneSettings
from orchestration.jobs import SqliteJobQueue
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


def test_temporal_mode_requires_every_managed_dependency(monkeypatch):
    monkeypatch.setenv("EIP_CONTROL_PLANE_MODE", "temporal")

    with pytest.raises(ControlPlaneConfigurationError, match="EIP_TEMPORAL_ENDPOINT"):
        TemporalControlPlaneSettings.from_environment()


def test_temporal_mode_accepts_only_explicit_managed_configuration(monkeypatch):
    monkeypatch.setenv("EIP_CONTROL_PLANE_MODE", "temporal")
    monkeypatch.setenv("EIP_TEMPORAL_ENDPOINT", "temporal-frontend.eip-system.svc:7233")
    monkeypatch.setenv("EIP_TEMPORAL_NAMESPACE", "eip")
    monkeypatch.setenv("EIP_TEMPORAL_TASK_QUEUE", "remediation")
    monkeypatch.setenv("EIP_TEMPORAL_TLS_SERVER_NAME", "temporal-frontend.eip-system.svc")
    monkeypatch.setenv("EIP_TEMPORAL_TLS_CA_CERT_PATH", "/var/run/eip/temporal-tls/ca.crt")
    monkeypatch.setenv("EIP_TEMPORAL_TLS_CLIENT_CERT_PATH", "/var/run/eip/temporal-tls/tls.crt")
    monkeypatch.setenv("EIP_TEMPORAL_TLS_CLIENT_KEY_PATH", "/var/run/eip/temporal-tls/tls.key")
    monkeypatch.setenv("EIP_COSMOS_ENDPOINT", "https://eip.documents.azure.com")
    monkeypatch.setenv("EIP_COSMOS_DATABASE", "eip")
    monkeypatch.setenv("EIP_COSMOS_STATE_CONTAINER", "state")
    monkeypatch.setenv("EIP_IMMUTABLE_AUDIT_EVIDENCE_URI", "https://audit.example/eip")

    settings = TemporalControlPlaneSettings.from_environment()

    assert settings.temporal_task_queue == "remediation"
    assert settings.cosmos_state_container == "state"
    assert settings.temporal_tls_ca_cert_path == "/var/run/eip/temporal-tls/ca.crt"


def test_temporal_mode_rejects_url_endpoint_or_non_mounted_tls_path(monkeypatch):
    values = {
        "EIP_CONTROL_PLANE_MODE": "temporal",
        "EIP_TEMPORAL_ENDPOINT": "https://temporal.example:7233",
        "EIP_TEMPORAL_NAMESPACE": "eip",
        "EIP_TEMPORAL_TASK_QUEUE": "control-plane",
        "EIP_TEMPORAL_TLS_SERVER_NAME": "temporal.example",
        "EIP_TEMPORAL_TLS_CA_CERT_PATH": "ca.crt",
        "EIP_TEMPORAL_TLS_CLIENT_CERT_PATH": "/tls/tls.crt",
        "EIP_TEMPORAL_TLS_CLIENT_KEY_PATH": "/tls/tls.key",
        "EIP_COSMOS_ENDPOINT": "https://eip.documents.azure.com",
        "EIP_COSMOS_DATABASE": "eip",
        "EIP_COSMOS_STATE_CONTAINER": "state",
        "EIP_IMMUTABLE_AUDIT_EVIDENCE_URI": "https://audit.example/eip",
    }
    with pytest.raises(ControlPlaneConfigurationError, match="host:port"):
        TemporalControlPlaneSettings.from_environment(values)
    values["EIP_TEMPORAL_ENDPOINT"] = "temporal.example:7233"
    with pytest.raises(ControlPlaneConfigurationError, match="absolute mounted-file path"):
        TemporalControlPlaneSettings.from_environment(values)


@pytest.mark.parametrize("factory", (SqliteStateStore, SqliteAuditLog, SqliteJobQueue))
def test_temporal_mode_rejects_sqlite_fallback(monkeypatch, tmp_path, factory):
    monkeypatch.setenv("EIP_CONTROL_PLANE_MODE", "temporal")

    with pytest.raises(ControlPlaneConfigurationError, match="reference-only"):
        factory(tmp_path / "reference.db")
