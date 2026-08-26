"""PR Guardian adapter for governed Company Brain context.

This adapter is intentionally read-only. It converts Company Brain facts into
the existing PR Guardian graph and evidence contracts without changing shadow
mode or granting any merge/deployment authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from company_brain.model import BrainPrincipal, CompanyBrain, CompanyBrainError
from company_brain.projector import repository_id, service_id
from intelligence.graph import ServiceGraph, ServiceNode

from .contracts import EvidenceBasis, EvidenceBundle, EvidenceReference


@dataclass(frozen=True)
class PRGuardianCompanyContext:
    changed_services: tuple[str, ...]
    blast_radius: tuple[str, ...]
    owner_ids: tuple[str, ...]
    graph: ServiceGraph
    evidence: EvidenceBundle


class PRGuardianCompanyBrainAdapter:
    """Expose only authorized organizational context to the PR product workflow."""

    def __init__(self, brain: CompanyBrain, *, provider: str = "github") -> None:
        self.brain = brain
        self.provider = provider

    def context_for(
        self,
        *,
        repository: str,
        changed_services: tuple[str, ...],
        principal: BrainPrincipal,
    ) -> PRGuardianCompanyContext:
        repo = repository_id(provider=self.provider, repository=repository)
        core_context = self.brain.context_for_change(
            repository_id=repo,
            changed_services=tuple(service_id(name) for name in changed_services),
            principal=principal,
        )
        references = tuple(
            EvidenceReference(
                evidence_id=item.evidence_id,
                source_kind=item.source_kind,
                locator=item.citation,
                authorized=True,
            )
            for item in core_context.evidence
        )
        limitations = core_context.limitations
        if references:
            evidence = EvidenceBundle(
                basis=EvidenceBasis.MEASURED,
                references=references,
                limitations=limitations,
            )
        else:
            evidence = EvidenceBundle(
                basis=EvidenceBasis.DERIVED,
                references=(),
                limitations=limitations or ("No authorized Company Brain evidence was available.",),
            )
        graph = self._service_graph(repository_id=repo)
        return PRGuardianCompanyContext(
            changed_services=tuple(self.brain.entities[item].label for item in core_context.changed_services),
            blast_radius=tuple(self.brain.entities[item].label for item in core_context.blast_radius),
            owner_ids=core_context.owner_ids,
            graph=graph,
            evidence=evidence,
        )

    def _service_graph(self, *, repository_id: str) -> ServiceGraph:
        if repository_id not in self.brain.entities:
            raise CompanyBrainError("repository is not present in the Company Brain")
        services = self.brain.services_for_repository(repository_id)
        known = set(services)
        graph = ServiceGraph()
        for service in services:
            entity = self.brain.entities[service]
            dependencies = tuple(
                self.brain.entities[relationship.target_id].label
                for relationship in self.brain.outgoing(service)
                if relationship.kind.value == "depends_on" and relationship.target_id in known
            )
            owners = self.brain.owner_ids_for_service(service)
            owner = self.brain.entities[owners[0]].label if owners else None
            graph.add(
                ServiceNode(
                    name=entity.label,
                    tier=_tier(entity.metadata.get("tier")),
                    owner=owner,
                    dependencies=tuple(sorted(dependencies)),
                )
            )
        return graph


def _tier(value: str | None) -> int:
    try:
        tier = int(value or "3")
    except ValueError:
        return 3
    return tier if tier in {1, 2, 3} else 3
