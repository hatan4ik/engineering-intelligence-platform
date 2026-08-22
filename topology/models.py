from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class TopologyNode:
    node_id: str
    kind: str
    name: str
    service_id: str | None = None
    owner: str | None = None
    tier: int = 3
    environment: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TopologyEdge:
    source_id: str
    target_id: str
    relation: str


@dataclass(frozen=True)
class BlastRadius:
    origin_ids: tuple[str, ...]
    impacted_ids: tuple[str, ...]
    impacted_services: tuple[str, ...]
