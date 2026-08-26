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
    monkeypatch.setenv("EIP_COSMOS_ENDPOINT", "https://eip.documents.azure.com")
    monkeypatch.setenv("EIP_COSMOS_DATABASE", "eip")
    monkeypatch.setenv("EIP_COSMOS_STATE_CONTAINER", "state")
    monkeypatch.setenv("EIP_IMMUTABLE_AUDIT_EVIDENCE_URI", "https://audit.example/eip")

    settings = TemporalControlPlaneSettings.from_environment()

    assert settings.temporal_task_queue == "remediation"
    assert settings.cosmos_state_container == "state"


@pytest.mark.parametrize("factory", (SqliteStateStore, SqliteAuditLog, SqliteJobQueue))
def test_temporal_mode_rejects_sqlite_fallback(monkeypatch, tmp_path, factory):
    monkeypatch.setenv("EIP_CONTROL_PLANE_MODE", "temporal")

    with pytest.raises(ControlPlaneConfigurationError, match="reference-only"):
        factory(tmp_path / "reference.db")
