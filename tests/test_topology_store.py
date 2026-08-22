from intelligence.extractors import ServiceMetadata
from topology.projections import project_resource, project_services
from topology.store import SqliteTopologyStore


def test_persistent_service_graph_and_reverse_blast_radius(tmp_path):
    store = SqliteTopologyStore(tmp_path / "topology.db")
    project_services(
        store,
        [
            ServiceMetadata("identity", owner="security", tier=1),
            ServiceMetadata("payments", owner="payments", tier=1, dependencies=("identity",)),
            ServiceMetadata("checkout", owner="commerce", tier=2, dependencies=("payments",)),
        ],
    )

    radius = store.blast_radius({"identity"})
    assert radius.impacted_services == ("checkout", "identity", "payments")

    graph = store.to_service_graph()
    assert graph.nodes["payments"].dependencies == ("identity",)
    assert graph.dependents_of("identity") == {"payments", "checkout"}


def test_resource_projection_links_runtime_resource_to_service(tmp_path):
    store = SqliteTopologyStore(tmp_path / "topology.db")
    project_services(store, [ServiceMetadata("payments", owner="payments", tier=1)])
    project_resource(
        store,
        resource_id="aks:prod:deployment/payments",
        kind="kubernetes-deployment",
        name="payments",
        service_id="payments",
        environment="prod",
        metadata={"namespace": "payments"},
    )
    node = store.get_node("aks:prod:deployment/payments")
    assert node is not None
    assert node.service_id == "payments"
    assert node.environment == "prod"
