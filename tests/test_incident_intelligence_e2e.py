from datetime import datetime, timedelta, timezone

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.incidents import EvidenceEvent, EvidenceKind
from product.incident_service import IncidentIntelligenceService
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore
from topology.models import TopologyEdge, TopologyNode
from topology.store import SqliteTopologyStore


class Evidence:
    def collect(self, *, incident_id, service, environment):
        deployed = datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc)
        return [
            EvidenceEvent(
                id="deploy-1",
                kind=EvidenceKind.DEPLOYMENT,
                service=service,
                timestamp=deployed,
                summary="release abc deployed",
                source="azure-devops",
            ),
            EvidenceEvent(
                id="alert-1",
                kind=EvidenceKind.ALERT,
                service=service,
                timestamp=deployed + timedelta(minutes=3),
                summary="OOMKilled rate increased",
                source="azure-monitor",
                severity=4,
            ),
            EvidenceEvent(
                id="k8s-1",
                kind=EvidenceKind.K8S_EVENT,
                service=service,
                timestamp=deployed + timedelta(minutes=4),
                summary="memory pressure on payments pods",
                source="aks",
                severity=4,
            ),
        ]


class Publisher:
    def __init__(self):
        self.items = []

    def publish(self, **kwargs):
        self.items.append(kwargs)


def test_incident_workflow_includes_topology_blast_radius(tmp_path):
    topology = SqliteTopologyStore(tmp_path / "topology.db")
    topology.upsert_node(TopologyNode("payments", "service", "payments", service_id="payments", tier=1))
    topology.upsert_node(TopologyNode("checkout", "service", "checkout", service_id="checkout", tier=2))
    topology.upsert_edge(TopologyEdge("checkout", "payments", "depends-on"))

    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    publisher = Publisher()
    service = IncidentIntelligenceService(
        evidence=Evidence(),
        topology=topology,
        workflows=ControlPlaneWorkflows(store, audit),
        publisher=publisher,
    )

    result = service.investigate(incident_id="INC-42", service="payments", environment="prod")
    assert result.workflow_id == "incident:INC-42"
    assert result.impacted_services == ("checkout", "payments")
    assert len(result.analysis.hypotheses) >= 2
    assert result.analysis.hypotheses[0].confidence >= 0.8
    assert store.get_workflow("incident:INC-42") is not None
    assert audit.verify_chain() is True
    assert publisher.items[0]["impacted_services"] == ("checkout", "payments")
