from topology.engineering_projection import (
    ApiDependency,
    DataDependency,
    QueueDependency,
    impacted_owners,
    project_api_dependencies,
    project_data_dependencies,
    project_queue_dependencies,
    project_service_governance,
)
from topology.store import SqliteTopologyStore


def test_api_dependency_expands_blast_radius_and_owner_context(tmp_path):
    store = SqliteTopologyStore(tmp_path / "topology.db")
    project_service_governance(store, service_id="identity", owner="security", tier=1, slo_target=0.999)
    project_service_governance(store, service_id="payments", owner="payments", tier=1, slo_target=0.9995)
    project_api_dependencies(store, [ApiDependency("payments", "identity", operation="POST /token")])

    radius = store.blast_radius({"identity"})
    assert "payments" in radius.impacted_services
    assert impacted_owners(store, {"identity"}) == ("payments", "security")
    operation = store.get_node("api:identity:POST /token")
    assert operation is not None
    assert operation.kind == "api-operation"


def test_database_and_queue_nodes_are_first_class_topology(tmp_path):
    store = SqliteTopologyStore(tmp_path / "topology.db")
    project_service_governance(store, service_id="checkout", owner="commerce", tier=2, repo="acme/checkout")
    project_data_dependencies(store, [
        DataDependency("checkout", "pg:orders", "postgresql", "orders", "prod", "read-write")
    ])
    project_queue_dependencies(store, [
        QueueDependency("checkout", "sb:orders", "orders", "prod", "producer"),
        QueueDependency("fulfillment", "sb:orders", "orders", "prod", "consumer"),
    ])

    db = store.get_node("pg:orders")
    queue = store.get_node("sb:orders")
    assert db is not None and db.metadata["access"] == "read-write"
    assert queue is not None and queue.kind == "queue"
    relations = {(e.source_id, e.target_id, e.relation) for e in store.edges()}
    assert ("checkout", "pg:orders", "uses-data") in relations
    assert ("checkout", "sb:orders", "produces-to") in relations
    assert ("fulfillment", "sb:orders", "consumes-from") in relations


def test_invalid_governance_and_queue_role_fail_closed(tmp_path):
    store = SqliteTopologyStore(tmp_path / "topology.db")
    try:
        project_service_governance(store, service_id="x", owner="o", tier=0)
    except ValueError as exc:
        assert "tier" in str(exc)
    else:
        raise AssertionError("invalid tier accepted")

    try:
        project_queue_dependencies(store, [QueueDependency("x", "q", "q", "prod", "reader")])
    except ValueError as exc:
        assert "role" in str(exc)
    else:
        raise AssertionError("invalid queue role accepted")
