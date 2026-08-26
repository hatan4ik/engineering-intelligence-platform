"""The worker stays evidence-only unless remediation is explicitly enabled."""
from __future__ import annotations

import pytest

pytest.importorskip("temporalio")

from orchestration.remediation_workflow import RemediationWorkflow
from orchestration.temporal_worker import build_worker, worker_registration_plan
from orchestration.temporal_workflow import ControlPlaneEvidenceWorkflow


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


def test_building_a_registered_worker_without_activities_fails_closed(tmp_path):
    from tests.test_temporal_worker import settings

    with pytest.raises(RuntimeError, match="remediation activities"):
        build_worker(object(), settings(tmp_path), remediation=None, environ={**COSMOS, **ENABLED})
