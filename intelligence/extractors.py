from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .graph import ServiceGraph, ServiceNode


@dataclass(frozen=True)
class ServiceMetadata:
    service: str
    owner: str | None = None
    tier: int = 3
    dependencies: tuple[str, ...] = ()


def metadata_from_manifest(path: str, content: str) -> ServiceMetadata | None:
    if not path.endswith((".yaml", ".yml")):
        return None
    service = _match(content, r"(?m)^\s*(?:app(?:\.kubernetes\.io/name)?|service):\s*[\"']?([^\s\"']+)")
    if not service:
        return None
    owner = _match(content, r"(?m)^\s*(?:owner|team):\s*[\"']?([^\s\"']+)")
    raw_tier = (_match(content, r"(?m)^\s*(?:tier|service-tier):\s*[\"']?([^\s\"']+)") or "3").lower()
    tier = _tier_value(raw_tier)
    raw_deps = _match(content, r"(?m)^\s*(?:dependencies|depends-on):\s*[\"']?([^\n\"']+)")
    deps = tuple(sorted({d.strip() for d in (raw_deps or "").split(",") if d.strip()}))
    return ServiceMetadata(service=service, owner=owner, tier=tier, dependencies=deps)


def service_from_path(path: str, known_services: set[str]) -> str | None:
    parts = PurePosixPath(path).parts
    for part in parts:
        if part in known_services:
            return part
    stem = PurePosixPath(path).stem
    return stem if stem in known_services else None


def build_graph(metadata: list[ServiceMetadata]) -> ServiceGraph:
    graph = ServiceGraph()
    all_dependencies = {dep for item in metadata for dep in item.dependencies}
    declared = {item.service for item in metadata}
    for dep in sorted(all_dependencies - declared):
        graph.add(ServiceNode(name=dep))
    for item in metadata:
        graph.add(ServiceNode(name=item.service, owner=item.owner, tier=item.tier, dependencies=item.dependencies))
    return graph


def _tier_value(value: str) -> int:
    aliases = {"critical": 1, "tier-1": 1, "1": 1, "high": 2, "tier-2": 2, "2": 2, "standard": 3, "tier-3": 3, "3": 3}
    return aliases.get(value, 3)


def _match(content: str, pattern: str) -> str | None:
    m = re.search(pattern, content)
    return m.group(1).strip() if m else None
