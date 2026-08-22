from __future__ import annotations

from intelligence.extractors import ServiceMetadata
from topology.models import TopologyEdge, TopologyNode
from topology.store import SqliteTopologyStore


def project_services(store: SqliteTopologyStore, metadata: list[ServiceMetadata]) -> None:
    declared = {item.service for item in metadata}
    for item in metadata:
        store.upsert_node(
            TopologyNode(
                node_id=item.service,
                kind="service",
                name=item.service,
                service_id=item.service,
                owner=item.owner,
                tier=item.tier,
            )
        )
    for item in metadata:
        for dependency in item.dependencies:
            if dependency not in declared:
                store.upsert_node(
                    TopologyNode(
                        node_id=dependency,
                        kind="service",
                        name=dependency,
                        service_id=dependency,
                    )
                )
            store.upsert_edge(TopologyEdge(item.service, dependency, "depends-on"))


def project_resource(
    store: SqliteTopologyStore,
    *,
    resource_id: str,
    kind: str,
    name: str,
    service_id: str,
    environment: str,
    owner: str | None = None,
    depends_on: tuple[str, ...] = (),
    metadata: dict[str, str] | None = None,
) -> None:
    store.upsert_node(
        TopologyNode(
            node_id=resource_id,
            kind=kind,
            name=name,
            service_id=service_id,
            owner=owner,
            environment=environment,
            metadata=metadata or {},
        )
    )
    store.upsert_edge(TopologyEdge(resource_id, service_id, "belongs-to"))
    for dependency in depends_on:
        store.upsert_edge(TopologyEdge(resource_id, dependency, "depends-on"))
