"""PR Guardian adapter for governed Company Brain context.

This adapter is intentionally read-only. It converts Company Brain facts into
the existing PR Guardian graph and evidence contracts without changing shadow
mode or granting any merge/deployment authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from company_brain.model import BrainPrincipal, CompanyBrain, CompanyBrainError
from company_brain.projector import repository_id, service_id
from company_brain.world_model import CompanyBrainWorldModel, QualifiedWorldModelContext
from intelligence.graph import ServiceGraph, ServiceNode

from .contracts import EvidenceBasis, EvidenceBundle, EvidenceReference


@dataclass(frozen=True)
class PRGuardianCompanyContext:
    changed_services: tuple[str, ...]
    blast_radius: tuple[str, ...]
    owner_ids: tuple[str, ...]
    graph: ServiceGraph
    evidence: EvidenceBundle
    context_version: str
    qualified: bool
    limitations: tuple[str, ...]
    conflict_ids: tuple[str, ...]


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
            context_version="legacy-company-brain-v1",
            # The in-memory snapshot has no source-freshness qualification.
            # It remains compatible as a display/context adapter but cannot
            # drive a product control decision.
            qualified=False,
            limitations=limitations or ("Legacy Company Brain context is not freshness-qualified.",),
            conflict_ids=(),
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


class PRGuardianWorldModelAdapter:
    """Translate qualified, durable Company Brain context for PR Guardian.

    Entity discovery is used only to map changed paths to candidate services.
    The world-model query remains the authority for membership, graph edges,
    evidence and decision qualification.  A context with stale, withheld,
    conflicted, or insufficient evidence is explicitly *not* qualified.
    """

    def __init__(self, world_model: CompanyBrainWorldModel, *, provider: str = "github") -> None:
        self.world_model = world_model
        self.provider = provider

    def known_services(self, *, repository: str, principal: BrainPrincipal) -> tuple[str, ...]:
        repository_id_value = repository_id(provider=self.provider, repository=repository)
        candidates = tuple(
            sorted(
                item.entity.entity_id
                for item in self.world_model.store.list_entities(self.world_model.tenant_id)
                if item.entity.kind.value == "service"
            )
        )
        context = self.world_model.context_for_change(
            repository_id=repository_id_value,
            changed_services=candidates,
            principal=principal,
        )
        return tuple(
            self._entity_labels(context, context.changed_services)
        )

    def context_for(
        self,
        *,
        repository: str,
        changed_services: tuple[str, ...],
        principal: BrainPrincipal,
    ) -> PRGuardianCompanyContext:
        context = self.world_model.context_for_change(
            repository_id=repository_id(provider=self.provider, repository=repository),
            changed_services=tuple(sorted({service_id(name) for name in changed_services})),
            principal=principal,
        )
        evidence = self._evidence(context)
        limitations = tuple(dict.fromkeys(context.limitations))
        qualified = bool(
            context.changed_services
            and context.evidence
            and context.confidence >= self.world_model.policy.minimum_confidence
            and not context.conflicts
            and not limitations
        )
        if not qualified and not limitations:
            limitations = ("Company Brain context is insufficient for a control decision.",)
        return PRGuardianCompanyContext(
            changed_services=self._entity_labels(context, context.changed_services),
            blast_radius=self._entity_labels(context, context.blast_radius),
            owner_ids=context.owner_ids,
            graph=self._graph(context),
            evidence=evidence,
            context_version=_context_version(context),
            qualified=qualified,
            limitations=limitations,
            conflict_ids=tuple(conflict.conflict_id for conflict in context.conflicts),
        )

    @staticmethod
    def _entity_labels(context: QualifiedWorldModelContext, entity_ids: tuple[str, ...]) -> tuple[str, ...]:
        labels = {item.entity.entity_id: item.entity.label for item in context.entities}
        return tuple(sorted(labels[item] for item in entity_ids if item in labels))

    @staticmethod
    def _evidence(context: QualifiedWorldModelContext) -> EvidenceBundle:
        references = tuple(
            EvidenceReference(
                evidence_id=item.evidence_id,
                source_kind=item.source_kind,
                locator=item.citation,
                authorized=True,
            )
            for item in context.evidence
        )
        if references:
            return EvidenceBundle(
                basis=EvidenceBasis.MEASURED,
                references=references,
                limitations=context.limitations,
            )
        return EvidenceBundle(
            basis=EvidenceBasis.DERIVED,
            references=(),
            limitations=context.limitations or ("No qualified Company Brain evidence was available.",),
        )

    @staticmethod
    def _graph(context: QualifiedWorldModelContext) -> ServiceGraph:
        entities = {item.entity.entity_id: item.entity for item in context.entities}
        services = tuple(
            sorted(
                entity_id
                for entity_id in set((*context.changed_services, *context.blast_radius))
                if entity_id in entities and entities[entity_id].kind.value == "service"
            )
        )
        service_set = set(services)
        dependencies: dict[str, set[str]] = {item: set() for item in services}
        owners: dict[str, set[str]] = {item: set() for item in services}
        for qualification in context.relationships:
            relationship = qualification.relationship
            if not qualification.usable:
                continue
            if relationship.kind.value == "depends_on" and {
                relationship.source_id,
                relationship.target_id,
            }.issubset(service_set):
                dependencies[relationship.source_id].add(relationship.target_id)
            if relationship.kind.value == "owns" and relationship.target_id in service_set:
                owners[relationship.target_id].add(relationship.source_id)
        graph = ServiceGraph()
        for entity_id in services:
            entity = entities[entity_id]
            owner_ids = owners[entity_id]
            # Avoid selecting an owner if evidence yields an ambiguity.
            owner = entities[next(iter(owner_ids))].label if len(owner_ids) == 1 and next(iter(owner_ids)) in entities else None
            graph.add(
                ServiceNode(
                    name=entity.label,
                    tier=_tier(entity.metadata.get("tier")),
                    owner=owner,
                    dependencies=tuple(sorted(entities[item].label for item in dependencies[entity_id])),
                )
            )
        return graph


def _context_version(context: QualifiedWorldModelContext) -> str:
    """A reproducible context fingerprint, not a mutable-store version claim."""

    payload = {
        "tenant_id": context.tenant_id,
        "repository_id": context.repository_id,
        "changed_services": context.changed_services,
        "blast_radius": context.blast_radius,
        "owner_ids": context.owner_ids,
        "confidence": context.confidence,
        "relationships": [
            {
                "source": item.relationship.source_id,
                "kind": item.relationship.kind.value,
                "target": item.relationship.target_id,
                "confidence": item.confidence,
                "freshness": item.freshness.value,
                "usable": item.usable,
            }
            for item in context.relationships
        ],
        "evidence": [
            {
                "id": item.evidence_id,
                "source_kind": item.source_kind,
                "citation": item.citation,
                "observed_at": item.observed_at.isoformat(),
                "freshness": item.freshness.value,
            }
            for item in context.evidence
        ],
        "conflicts": [item.conflict_id for item in context.conflicts],
        "limitations": context.limitations,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"world-model:v1:{digest}"
