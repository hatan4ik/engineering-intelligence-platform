from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from topology.models import TopologyEdge, TopologyNode
from topology.store import SqliteTopologyStore


@dataclass(frozen=True)
class ApiDependency:
    consumer: str
    provider: str
    protocol: str = "http"
    operation: str | None = None


@dataclass(frozen=True)
class DataDependency:
    service: str
    resource_id: str
    kind: str
    name: str
    environment: str
    access: str = "read-write"


@dataclass(frozen=True)
class QueueDependency:
    service: str
    queue_id: str
    name: str
    environment: str
    role: str  # producer | consumer


def project_api_dependencies(store: SqliteTopologyStore, dependencies: Iterable[ApiDependency]) -> None:
    for dep in dependencies:
        _ensure_service(store, dep.consumer)
        _ensure_service(store, dep.provider)
        store.upsert_edge(TopologyEdge(dep.consumer, dep.provider, "calls-api"))
        if dep.operation:
            edge_id = f"api:{dep.provider}:{dep.operation}"
            store.upsert_node(TopologyNode(
                node_id=edge_id,
                kind="api-operation",
                name=dep.operation,
                service_id=dep.provider,
                metadata={"protocol": dep.protocol},
            ))
            store.upsert_edge(TopologyEdge(dep.consumer, edge_id, "calls"))
            store.upsert_edge(TopologyEdge(edge_id, dep.provider, "belongs-to"))


def project_data_dependencies(store: SqliteTopologyStore, dependencies: Iterable[DataDependency]) -> None:
    for dep in dependencies:
        _ensure_service(store, dep.service)
        store.upsert_node(TopologyNode(
            node_id=dep.resource_id,
            kind=dep.kind,
            name=dep.name,
            service_id=dep.service,
            environment=dep.environment,
            metadata={"access": dep.access},
        ))
        store.upsert_edge(TopologyEdge(dep.service, dep.resource_id, "uses-data"))


def project_queue_dependencies(store: SqliteTopologyStore, dependencies: Iterable[QueueDependency]) -> None:
    for dep in dependencies:
        _ensure_service(store, dep.service)
        existing = store.get_node(dep.queue_id)
        if existing is None:
            store.upsert_node(TopologyNode(
                node_id=dep.queue_id,
                kind="queue",
                name=dep.name,
                environment=dep.environment,
            ))
        relation = "produces-to" if dep.role == "producer" else "consumes-from"
        if dep.role not in {"producer", "consumer"}:
            raise ValueError("queue role must be producer or consumer")
        store.upsert_edge(TopologyEdge(dep.service, dep.queue_id, relation))


def project_service_governance(
    store: SqliteTopologyStore,
    *,
    service_id: str,
    owner: str,
    tier: int,
    slo_target: float | None = None,
    repo: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> None:
    if tier < 1 or tier > 4:
        raise ValueError("service tier must be 1..4")
    combined = dict(metadata or {})
    if slo_target is not None:
        if not 0 < slo_target <= 1:
            raise ValueError("SLO target must be in (0, 1]")
        combined["slo_target"] = str(slo_target)
    if repo:
        combined["repository"] = repo
    store.upsert_node(TopologyNode(
        node_id=service_id,
        kind="service",
        name=service_id,
        service_id=service_id,
        owner=owner,
        tier=tier,
        metadata=combined,
    ))


def impacted_owners(store: SqliteTopologyStore, origin_ids: set[str]) -> tuple[str, ...]:
    radius = store.blast_radius(origin_ids)
    owners: set[str] = set()
    for node_id in radius.impacted_nodes:
        node = store.get_node(node_id)
        if node and node.owner:
            owners.add(node.owner)
        if node and node.service_id:
            service = store.get_node(node.service_id)
            if service and service.owner:
                owners.add(service.owner)
    return tuple(sorted(owners))


def _ensure_service(store: SqliteTopologyStore, service_id: str) -> None:
    if store.get_node(service_id) is None:
        store.upsert_node(TopologyNode(
            node_id=service_id,
            kind="service",
            name=service_id,
            service_id=service_id,
        ))
