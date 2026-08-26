import asyncio
from dataclasses import dataclass

import pytest

pytest.importorskip("temporalio")

from control_plane.runtime import TemporalControlPlaneSettings
from orchestration.temporal_client import run_evidence_workflow
from orchestration.temporal_workflow import ControlPlaneEvidenceResult


def settings():
    return TemporalControlPlaneSettings(
        temporal_endpoint="temporal-frontend.eip-system.svc:7233",
        temporal_namespace="eip",
        temporal_task_queue="eip-control-plane",
        temporal_tls_server_name="temporal-frontend.eip-system.svc",
        temporal_tls_ca_cert_path="/tls/ca.crt",
        temporal_tls_client_cert_path="/tls/tls.crt",
        temporal_tls_client_key_path="/tls/tls.key",
        cosmos_endpoint="https://eip.documents.azure.com",
        cosmos_database="eip",
        cosmos_state_container="state",
        immutable_audit_evidence_uri="https://audit.example/eip",
    )


@dataclass
class Handle:
    result_value: object

    async def result(self):
        return self.result_value


class Client:
    def __init__(self, result):
        self.result_value = result
        self.calls = []

    async def start_workflow(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Handle(self.result_value)


def test_evidence_client_binds_request_task_queue_and_result():
    result = ControlPlaneEvidenceResult(
        workflow_id="eip-control-plane-evidence:proof-1",
        request_id="proof-1",
        correlation_id="corr-1",
    )
    client = Client(result)
    observed = asyncio.run(
        run_evidence_workflow(settings(), request_id="proof-1", correlation_id="corr-1", client=client)
    )
    assert observed == result
    assert client.calls[0][1]["id"] == "eip-control-plane-evidence:proof-1"
    assert client.calls[0][1]["task_queue"] == "eip-control-plane"


def test_evidence_client_rejects_a_result_that_claims_mutation():
    client = Client(ControlPlaneEvidenceResult(
        workflow_id="eip-control-plane-evidence:proof-1",
        request_id="proof-1",
        correlation_id="corr-1",
        mutation_performed=True,
    ))
    with pytest.raises(RuntimeError, match="non-consequential"):
        asyncio.run(run_evidence_workflow(settings(), request_id="proof-1", correlation_id="corr-1", client=client))


def test_evidence_client_accepts_the_sdk_json_object_form():
    client = Client({
        "workflow_id": "eip-control-plane-evidence:proof-1",
        "request_id": "proof-1",
        "correlation_id": "corr-1",
        "capability": "temporal-control-plane-evidence",
        "mutation_performed": False,
    })
    observed = asyncio.run(
        run_evidence_workflow(settings(), request_id="proof-1", correlation_id="corr-1", client=client)
    )
    assert observed.workflow_id == "eip-control-plane-evidence:proof-1"
