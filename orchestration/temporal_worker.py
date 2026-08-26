"""Temporal worker entrypoint for the control-plane slice.

By default this worker is still the non-consequential evidence worker of
ADR-001. It additionally registers the opt-in remediation workflow, but only
when ``EIP_TEMPORAL_REMEDIATION_WORKFLOWS=enabled`` *and* the state factory can
build Cosmos state and audit. Anything less leaves the worker exactly as it was.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Mapping

from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from control_plane.runtime import TemporalWorkerSettings
from orchestration.remediation_workflow import (
    RemediationActivityProvider,
    RemediationRegistration,
    RemediationWorkflow,
    remediation_registration,
)
from orchestration.temporal_workflow import ControlPlaneEvidenceWorkflow


def temporal_tls_config(settings: TemporalWorkerSettings) -> TLSConfig:
    """Load mTLS material from mounted files; never accept PEM through env vars."""
    return TLSConfig(
        server_root_ca_cert=_read_pem(settings.temporal_tls_ca_cert_path, "Temporal CA certificate"),
        client_cert=_read_pem(settings.temporal_tls_client_cert_path, "Temporal client certificate"),
        client_private_key=_read_private_key(settings.temporal_tls_client_key_path),
        domain=settings.temporal_tls_server_name,
    )


async def connect_temporal(
    settings: TemporalWorkerSettings,
    *,
    connect: Callable[..., Awaitable[Client]] = Client.connect,
) -> Client:
    return await connect(
        settings.temporal_endpoint,
        namespace=settings.temporal_namespace,
        tls=temporal_tls_config(settings),
        identity="eip-control-plane-worker",
    )


@dataclass(frozen=True)
class WorkerRegistrationPlan:
    """What this worker will register, and why."""

    workflows: tuple[type, ...]
    registration: RemediationRegistration


def worker_registration_plan(environ: Mapping[str, str] | None = None) -> WorkerRegistrationPlan:
    registration = remediation_registration(environ)
    workflows: tuple[type, ...] = (ControlPlaneEvidenceWorkflow,)
    if registration.registered:
        workflows = (*workflows, RemediationWorkflow)
    return WorkerRegistrationPlan(workflows=workflows, registration=registration)


def build_worker(
    client: Client,
    settings: TemporalWorkerSettings,
    *,
    remediation: RemediationActivityProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> Worker:
    plan = worker_registration_plan(environ)
    activities: list[object] = []
    if plan.registration.registered:
        if remediation is None:
            raise RuntimeError(
                "EIP_TEMPORAL_REMEDIATION_WORKFLOWS=enabled requires remediation activities; "
                "refusing to register eip.remediation.v1 without them"
            )
        activities = list(remediation.activity_functions())
    # The remediation activities are synchronous (they hold database and
    # subprocess boundaries), so Temporal needs an explicit executor for them.
    activity_executor = (
        ThreadPoolExecutor(max_workers=8, thread_name_prefix="eip-activity") if activities else None
    )
    return Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=list(plan.workflows),
        activities=activities,
        activity_executor=activity_executor,
        max_concurrent_activities=8,
        max_concurrent_workflow_tasks=32,
        max_concurrent_workflow_task_polls=2,
        max_cached_workflows=128,
        identity="eip-control-plane-worker",
    )


async def run_worker() -> None:
    settings = TemporalWorkerSettings.from_environment()
    plan = worker_registration_plan()
    remediation = _build_remediation_activities() if plan.registration.registered else None
    client = await connect_temporal(settings)
    worker = build_worker(client, settings, remediation=remediation)
    await worker.run()


def _build_remediation_activities() -> RemediationActivityProvider:
    """Construct the remediation activity bridge from environment configuration.

    Imported here rather than at module scope so the default evidence worker
    never pulls the remediation execution plane into its process.
    """
    from orchestration.control_plane_activities import (
        ControlPlaneActivityBridge,
        build_remediation_activities,
    )
    from state.factory import build_audit_log, build_state_store

    bridge = ControlPlaneActivityBridge(build_state_store(), build_audit_log())
    return build_remediation_activities(bridge=bridge)


def _read_pem(path: str, label: str) -> bytes:
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise RuntimeError(f"{label} could not be read from its mounted path") from exc
    if not content.startswith(b"-----BEGIN CERTIFICATE-----"):
        raise RuntimeError(f"{label} is not PEM encoded")
    return content


def _read_private_key(path: str) -> bytes:
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise RuntimeError("Temporal client private key could not be read from its mounted path") from exc
    if not content.startswith(b"-----BEGIN ") or b"PRIVATE KEY-----" not in content.splitlines()[0]:
        raise RuntimeError("Temporal client private key is not PEM encoded")
    return content


if __name__ == "__main__":
    asyncio.run(run_worker())
