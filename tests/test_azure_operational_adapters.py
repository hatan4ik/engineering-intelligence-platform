from datetime import datetime, timezone

from integrations.azure.monitor import AzureMonitorEvidenceClient, AzureMonitorQuery
from integrations.azure.resource_graph import AzureDriftSnapshotProvider, AzureResourceGraphClient, DesiredResource
from intelligence.incidents import EvidenceKind


class Monitor(AzureMonitorEvidenceClient):
    def __init__(self):
        pass
    def _post(self, query):
        return {
            "tables": [{
                "columns": [
                    {"name": "TimeGenerated"}, {"name": "Kind"}, {"name": "SeverityLevel"},
                    {"name": "Message"}, {"name": "Id"},
                ],
                "rows": [["2026-08-22T10:00:00Z", "K8sEvent", 4, "OOMKilled payments pod", "evt-1"]],
            }]
        }


class ResourceGraph(AzureResourceGraphClient):
    def __init__(self):
        self.subscriptions = ("sub-1",)
        self.api_version = "2022-10-01"
    def _post(self, query):
        assert "resources" in query
        return {
            "data": [{
                "id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks",
                "image": "payments:v1",
                "replicas": "2",
            }]
        }


def test_monitor_normalizes_operational_evidence():
    client = Monitor()
    result = client.query(AzureMonitorQuery(
        workspace_id="ws",
        service="payments",
        start=datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc),
        kql="KubeEvents | take 10",
    ))
    assert len(result) == 1
    assert result[0].id == "evt-1"
    assert result[0].kind is EvidenceKind.K8S_EVENT
    assert result[0].severity == 4
    assert result[0].source == "azure-monitor"


def test_resource_graph_builds_drift_snapshot_from_desired_state():
    resource_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks"
    provider = AzureDriftSnapshotProvider(ResourceGraph(), (
        DesiredResource(
            resource_id=resource_id,
            service="payments",
            environment="prod",
            desired={"image": "payments:v2", "replicas": "3"},
            source="git:main:infra/payments.tf",
        ),
    ))
    snapshots = provider.desired(service="payments", environment="prod")
    assert len(snapshots) == 1
    assert snapshots[0].desired["image"] == "payments:v2"
    assert snapshots[0].observed["image"] == "payments:v1"
    assert snapshots[0].observed["replicas"] == "2"


def test_missing_resource_fails_closed_as_drift():
    class EmptyGraph(ResourceGraph):
        def _post(self, query): return {"data": []}

    resource_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Web/sites/api"
    provider = AzureDriftSnapshotProvider(EmptyGraph(), (
        DesiredResource(resource_id, "api", "prod", {"state": "Running"}, "git:main"),
    ))
    snapshot = provider.desired(service="api", environment="prod")[0]
    assert snapshot.desired["resource_exists"] is True
    assert snapshot.observed["resource_exists"] is False
