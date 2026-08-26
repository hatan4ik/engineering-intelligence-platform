"""Client entrypoints for the explicitly non-consequential Temporal proof workflow."""

from __future__ import annotations

from typing import Mapping

from temporalio.client import Client

from control_plane.runtime import TemporalControlPlaneSettings
from orchestration.temporal_worker import connect_temporal
from orchestration.temporal_workflow import (
    ControlPlaneEvidenceRequest,
    ControlPlaneEvidenceResult,
    ControlPlaneEvidenceWorkflow,
)


async def run_evidence_workflow(
    settings: TemporalControlPlaneSettings,
    *,
    request_id: str,
    correlation_id: str,
    client: Client | None = None,
) -> ControlPlaneEvidenceResult:
    """Start and await the one workflow approved for integration proof.

    A request ID is caller-supplied and becomes the Temporal workflow ID, which
    makes the evidence run traceable and rejects accidental duplicate starts.
    """
    request = ControlPlaneEvidenceRequest(
        request_id=request_id,
        correlation_id=correlation_id,
    )
    workflow_id = request.workflow_id
    temporal_client = client or await connect_temporal(settings)
    handle = await temporal_client.start_workflow(
        ControlPlaneEvidenceWorkflow.run,
        request,
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    raw_result = await handle.result()
    result = _normalize_result(raw_result)
    if result.workflow_id != workflow_id or result.request_id != request_id:
        raise RuntimeError("Temporal evidence workflow result did not bind to the requested workflow")
    if (
        result.correlation_id != correlation_id
        or result.mutation_performed
        or result.capability != "temporal-control-plane-evidence"
    ):
        raise RuntimeError("Temporal evidence workflow violated its non-consequential contract")
    return result


def _normalize_result(value: object) -> ControlPlaneEvidenceResult:
    if isinstance(value, ControlPlaneEvidenceResult):
        return value
    if not isinstance(value, Mapping):
        raise RuntimeError("Temporal evidence workflow returned an unexpected result type")
    expected = {"workflow_id", "request_id", "correlation_id", "capability", "mutation_performed"}
    if set(value) != expected:
        raise RuntimeError("Temporal evidence workflow result has unexpected or missing fields")
    if not all(isinstance(value[field], str) and value[field] for field in expected - {"mutation_performed"}):
        raise RuntimeError("Temporal evidence workflow result has invalid identifiers")
    if type(value["mutation_performed"]) is not bool:
        raise RuntimeError("Temporal evidence workflow result has invalid mutation flag")
    return ControlPlaneEvidenceResult(
        workflow_id=str(value["workflow_id"]),
        request_id=str(value["request_id"]),
        correlation_id=str(value["correlation_id"]),
        capability=str(value["capability"]),
        mutation_performed=bool(value["mutation_performed"]),
    )
