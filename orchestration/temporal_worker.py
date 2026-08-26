"""Temporal worker entrypoint for the non-consequential control-plane slice."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from control_plane.runtime import TemporalControlPlaneSettings
from orchestration.temporal_workflow import ControlPlaneEvidenceWorkflow


def temporal_tls_config(settings: TemporalControlPlaneSettings) -> TLSConfig:
    """Load mTLS material from mounted files; never accept PEM through env vars."""
    return TLSConfig(
        server_root_ca_cert=_read_pem(settings.temporal_tls_ca_cert_path, "Temporal CA certificate"),
        client_cert=_read_pem(settings.temporal_tls_client_cert_path, "Temporal client certificate"),
        client_private_key=_read_private_key(settings.temporal_tls_client_key_path),
        domain=settings.temporal_tls_server_name,
    )


async def connect_temporal(
    settings: TemporalControlPlaneSettings,
    *,
    connect: Callable[..., Awaitable[Client]] = Client.connect,
) -> Client:
    return await connect(
        settings.temporal_endpoint,
        namespace=settings.temporal_namespace,
        tls=temporal_tls_config(settings),
        identity="eip-control-plane-worker",
    )


def build_worker(client: Client, settings: TemporalControlPlaneSettings) -> Worker:
    return Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[ControlPlaneEvidenceWorkflow],
        max_concurrent_workflow_tasks=32,
        max_concurrent_workflow_task_polls=2,
        max_cached_workflows=128,
        identity="eip-control-plane-worker",
    )


async def run_worker() -> None:
    settings = TemporalControlPlaneSettings.from_environment()
    client = await connect_temporal(settings)
    worker = build_worker(client, settings)
    await worker.run()


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
