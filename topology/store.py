from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from intelligence.graph import ServiceGraph, ServiceNode
from topology.models import BlastRadius, TopologyEdge, TopologyNode


class SqliteTopologyStore:
    def __init__(self, path: str | Path = "eip-topology.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS topology_nodes (
                    node_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    service_id TEXT,
                    owner TEXT,
                    tier INTEGER NOT NULL,
                    environment TEXT,
                    metadata TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topology_edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_topology_edges_source ON topology_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_topology_edges_target ON topology_edges(target_id);
                """
            )

    def upsert_node(self, node: TopologyNode) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO topology_nodes(node_id, kind, name, service_id, owner, tier, environment, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(node_id) DO UPDATE SET
                     kind=excluded.kind, name=excluded.name, service_id=excluded.service_id,
                     owner=excluded.owner, tier=excluded.tier, environment=excluded.environment,
                     metadata=excluded.metadata""",
                (
                    node.node_id,
                    node.kind,
                    node.name,
                    node.service_id,
                    node.owner,
                    node.tier,
                    node.environment,
                    json.dumps(dict(node.metadata), sort_keys=True),
                ),
            )

    def upsert_edge(self, edge: TopologyEdge) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO topology_edges(source_id, target_id, relation) VALUES (?, ?, ?)",
                (edge.source_id, edge.target_id, edge.relation),
            )

    def get_node(self, node_id: str) -> TopologyNode | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM topology_nodes WHERE node_id=?", (node_id,)).fetchone()
        if not row:
            return None
        return TopologyNode(
            node_id=row["node_id"],
            kind=row["kind"],
            name=row["name"],
            service_id=row["service_id"],
            owner=row["owner"],
            tier=int(row["tier"]),
            environment=row["environment"],
            metadata=json.loads(row["metadata"]),
        )

    def edges(self) -> list[TopologyEdge]:
        with self._connect() as db:
            rows = db.execute("SELECT source_id, target_id, relation FROM topology_edges").fetchall()
        return [TopologyEdge(r["source_id"], r["target_id"], r["relation"]) for r in rows]

    def blast_radius(self, origin_ids: set[str]) -> BlastRadius:
        # Edges point from dependent -> dependency. A dependency change can impact reverse dependents.
        reverse: dict[str, set[str]] = {}
        for edge in self.edges():
            reverse.setdefault(edge.target_id, set()).add(edge.source_id)
        seen = set(origin_ids)
        stack = list(origin_ids)
        while stack:
            current = stack.pop()
            for dependent in reverse.get(current, set()):
                if dependent in seen:
                    continue
                seen.add(dependent)
                stack.append(dependent)
        services = sorted(
            {
                node.service_id
                for node_id in seen
                if (node := self.get_node(node_id)) is not None and node.service_id
            }
        )
        return BlastRadius(tuple(sorted(origin_ids)), tuple(sorted(seen)), tuple(services))

    def to_service_graph(self) -> ServiceGraph:
        graph = ServiceGraph()
        with self._connect() as db:
            rows = db.execute(
                "SELECT node_id, name, owner, tier FROM topology_nodes WHERE kind='service'"
            ).fetchall()
        service_ids = {row["node_id"] for row in rows}
        deps: dict[str, set[str]] = {sid: set() for sid in service_ids}
        for edge in self.edges():
            if edge.relation == "depends-on" and edge.source_id in service_ids and edge.target_id in service_ids:
                deps[edge.source_id].add(edge.target_id)
        for row in rows:
            graph.add(
                ServiceNode(
                    name=row["name"],
                    owner=row["owner"],
                    tier=int(row["tier"]),
                    dependencies=tuple(sorted(deps[row["node_id"]])),
                )
            )
        return graph
