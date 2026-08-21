from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceNode:
    name: str
    tier: int = 3
    owner: str | None = None
    dependencies: tuple[str, ...] = ()


@dataclass
class ServiceGraph:
    nodes: dict[str, ServiceNode] = field(default_factory=dict)

    def add(self, node: ServiceNode) -> None:
        self.nodes[node.name] = node

    def dependents_of(self, service: str) -> set[str]:
        reverse: dict[str, set[str]] = {}
        for node in self.nodes.values():
            for dep in node.dependencies:
                reverse.setdefault(dep, set()).add(node.name)
        seen: set[str] = set()
        stack = list(reverse.get(service, set()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(reverse.get(current, set()) - seen)
        return seen

    def blast_radius(self, changed_services: set[str]) -> set[str]:
        impacted = set(changed_services)
        for service in changed_services:
            impacted.update(self.dependents_of(service))
        return impacted

    def max_tier(self, services: set[str]) -> int:
        tiers = [self.nodes[s].tier for s in services if s in self.nodes]
        return min(tiers) if tiers else 3
