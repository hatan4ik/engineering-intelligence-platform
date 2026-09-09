"""Contract tests for Azure Monitor and Azure Resource Graph adapters.

These tests enforce protocol compatibility, normalized schema mapping,
and fail-closed resilience boundaries without live cloud infrastructure.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone

import pytest
from azure.core.credentials import AccessToken, TokenCredential

from integrations.azure.monitor import AzureMonitorEvidenceClient, AzureMonitorQuery
from integrations.azure.resource_graph import (
    AzureDriftSnapshotProvider,
    AzureResourceGraphClient,
    DesiredResource,
)
from intelligence.incidents import EvidenceKind
from resilience.dependencies import DependencyBoundary, DependencyLimits, DependencyUnavailable


class _FakeTokenCredential:
    """Minimal fake TokenCredential conforming to the azure.core protocol."""

    def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        return AccessToken("mock-token-xyz", 1893456000)


def test_azure_monitor_client_accepts_token_credential_protocol() -> None:
    credential = _FakeTokenCredential()
    assert isinstance(credential, TokenCredential)
    client = AzureMonitorEvidenceClient(credential)
    assert client.credential is credential


def test_azure_monitor_client_parses_kql_tables_into_normalized_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_payload = {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": [
                    {"name": "TimeGenerated", "type": "datetime"},
                    {"name": "Message", "type": "string"},
                    {"name": "SeverityLevel", "type": "int"},
                    {"name": "OperationId", "type": "string"},
                ],
                "rows": [
                    [
                        "2026-09-08T12:00:00.000Z",
                        "High latency alert: payment processing timeout",
                        3,
                        "op-987",
                    ]
                ],
            }
        ]
    }

    class MockHTTPResponse:
        def read(self) -> bytes:
            return json.dumps(response_payload).encode("utf-8")

        def __enter__(self) -> MockHTTPResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: MockHTTPResponse(),
    )

    client = AzureMonitorEvidenceClient(_FakeTokenCredential())
    query = AzureMonitorQuery(
        workspace_id="ws-12345",
        service="payments",
        start=datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        kql="AppTraces | where SeverityLevel >= 3",
    )

    events = client.query(query)
    assert len(events) == 1
    event = events[0]
    assert event.kind == EvidenceKind.LOG
    assert event.service == "payments"
    assert event.summary == "High latency alert: payment processing timeout"
    assert event.severity == 3
    assert event.source == "azure-monitor"
    assert event.id == "azure-monitor:payments:1788868800:0"
    assert event.timestamp == datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def test_azure_monitor_client_trips_circuit_breaker_on_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_request(req: object, timeout: float) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail_request)

    boundary = DependencyBoundary(
        "azure-monitor-contract-test",
        DependencyLimits(max_in_flight=1, failure_threshold=2, recovery_seconds=30),
    )
    client = AzureMonitorEvidenceClient(_FakeTokenCredential(), dependency=boundary)
    query = AzureMonitorQuery(
        workspace_id="ws-err",
        service="orders",
        start=datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        kql="AppExceptions",
    )

    with pytest.raises(DependencyUnavailable, match="request failed"):
        client.query(query)

    with pytest.raises(DependencyUnavailable, match="request failed"):
        client.query(query)

    # Circuit breaker is now open: fails fast with circuit is open
    with pytest.raises(DependencyUnavailable, match="circuit is open"):
        client.query(query)


def test_azure_resource_graph_client_snapshot_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.containerservice/managedclusters/aks-prod"
    response_payload = {
        "data": [
            {
                "id": resource_id,
                "name": "aks-prod",
                "type": "Microsoft.ContainerService/managedClusters",
                "kubernetesVersion": "1.30.2",
            }
        ]
    }

    class MockHTTPResponse:
        def read(self) -> bytes:
            return json.dumps(response_payload).encode("utf-8")

        def __enter__(self) -> MockHTTPResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: MockHTTPResponse(),
    )

    graph_client = AzureResourceGraphClient(
        subscriptions=("sub-1",),
        credential=_FakeTokenCredential(),
    )
    desired = DesiredResource(
        resource_id=resource_id,
        service="infrastructure",
        environment="prod",
        desired={"kubernetesVersion": "1.30.2"},
        source="infra/terraform/main.tf",
    )

    provider = AzureDriftSnapshotProvider(graph_client, (desired,))
    snapshots = provider.desired(service="infrastructure", environment="prod")
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.service == "infrastructure"
    assert snapshot.environment == "prod"
    assert snapshot.observed["kubernetesVersion"] == "1.30.2"
    assert snapshot.desired["kubernetesVersion"] == "1.30.2"

