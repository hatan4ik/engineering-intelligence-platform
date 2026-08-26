"""The worker stays evidence-only unless remediation is explicitly enabled."""
from __future__ import annotations

import pytest

pytest.importorskip("temporalio")

from orchestration.remediation_workflow import RemediationWorkflow, remediation_registration
from orchestration.temporal_worker import build_worker, worker_registration_plan
from orchestration.temporal_workflow import ControlPlaneEvidenceWorkflow
from state.audit import SqliteAuditLog
from state.factory import build_audit_log, build_state_store
from state.store import SqliteStateStore


COSMOS = {
    "EIP_CONTROL_PLANE_MODE": "temporal",
    "EIP_COSMOS_ENDPOINT": "https://eip.documents.azure.invalid:443/",
    "EIP_COSMOS_DATABASE": "eip",
    "EIP_COSMOS_STATE_CONTAINER": "workflow-state",
    "EIP_COSMOS_AUDIT_CONTAINER": "workflow-audit",
}
ENABLED = {"EIP_TEMPORAL_REMEDIATION_WORKFLOWS": "enabled"}


class FakeActivities:
    def activity_functions(self):
        return ["activity-a", "activity-b"]


def test_default_worker_registers_only_the_evidence_workflow():
    plan = worker_registration_plan(environ={"EIP_CONTROL_PLANE_MODE": "temporal"})
    assert plan.workflows == (ControlPlaneEvidenceWorkflow,)
    assert plan.registration.registered is False


def test_the_flag_alone_does_not_register_the_remediation_workflow():
    plan = worker_registration_plan(environ={"EIP_CONTROL_PLANE_MODE": "temporal", **ENABLED})
    assert plan.workflows == (ControlPlaneEvidenceWorkflow,)
    assert "EIP_COSMOS_STATE_CONTAINER" in plan.registration.missing_configuration


def test_the_flag_with_cosmos_registers_the_remediation_workflow():
    plan = worker_registration_plan(environ={**COSMOS, **ENABLED})
    assert plan.workflows == (ControlPlaneEvidenceWorkflow, RemediationWorkflow)
    assert plan.registration.registered is True


def test_cosmos_variables_do_not_register_remediation_in_reference_mode(tmp_path):
    """The gate is which backend the factory builds, not which variables are set.

    Reference mode returns the SQLite backends no matter how much Cosmos
    configuration is present, and a durable remediation workflow must never run
    on them.
    """
    environ = {
        **COSMOS,
        **ENABLED,
        "EIP_CONTROL_PLANE_MODE": "reference",
        "EIP_STATE_DB_PATH": str(tmp_path / "state.db"),
        "EIP_AUDIT_DB_PATH": str(tmp_path / "audit.db"),
    }
    # What the factory actually builds for this mapping:
    assert isinstance(build_state_store(environ), SqliteStateStore)
    assert isinstance(build_audit_log(environ), SqliteAuditLog)

    registration = remediation_registration(environ)
    assert registration.registered is False
    assert registration.flag_enabled is True
    assert "reference" in registration.reason
    assert "temporal" in registration.reason
    assert worker_registration_plan(environ=environ).workflows == (ControlPlaneEvidenceWorkflow,)


def test_a_disabled_control_plane_never_registers_remediation():
    registration = remediation_registration({"EIP_CONTROL_PLANE_MODE": "disabled", **ENABLED})
    assert registration.registered is False
    assert "disabled" in registration.reason


def test_building_a_registered_worker_without_activities_fails_closed(tmp_path):
    from tests.test_temporal_worker import settings

    with pytest.raises(RuntimeError, match="remediation activities"):
        build_worker(object(), settings(tmp_path), remediation=None, environ={**COSMOS, **ENABLED})
