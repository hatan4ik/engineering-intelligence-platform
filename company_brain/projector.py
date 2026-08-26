"""Project governed ingestion records into the Company Brain world model."""

from __future__ import annotations

from dataclasses import dataclass

from ingestion.documents import KnowledgeDocument, KnowledgeSourceType
from ingestion.models import FileChange

from .model import (
    BrainEntity,
    BrainEvidence,
    CompanyBrain,
    EntityKind,
    RelationshipKind,
)


def repository_id(*, provider: str, repository: str) -> str:
    return f"repository:{provider}:{repository}"


def service_id(service: str) -> str:
    return f"service:{service}"


def owner_id(owner: str) -> str:
    return f"owner:{owner}"


def _attributes(**values: str | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in values.items() if value))


@dataclass(frozen=True)
class ProjectionResult:
    entity_ids: tuple[str, ...]
    evidence_id: str
    unresolved_relationships: tuple[str, ...] = ()


class CompanyBrainProjector:
    """Creates only provenance-backed facts from already-governed source records."""

    def __init__(self, brain: CompanyBrain) -> None:
        self.brain = brain

    def project_file_change(self, change: FileChange) -> ProjectionResult:
        source = change.source
        repo = repository_id(provider=source.provider, repository=source.repository)
        change_entity = (
            f"change:{source.provider}:{source.repository}:{source.branch}:"
            f"{source.commit_sha}:{source.path}"
        )
        evidence_id = f"evidence:{source.provider}:{source.repository}:{source.branch}:{source.commit_sha}:{source.path}"
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=repo,
                kind=EntityKind.REPOSITORY,
                label=source.repository,
                attributes=_attributes(provider=source.provider, branch=source.branch),
            )
        )
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=change_entity,
                kind=EntityKind.CHANGE,
                label=f"{source.repository}@{source.commit_sha}:{source.path}",
                attributes=_attributes(
                    branch=source.branch,
                    commit_sha=source.commit_sha,
                    path=source.path,
                    change_type=change.change_type.value,
                    language=change.language,
                ),
            )
        )
        self.brain.record_evidence(
            BrainEvidence(
                evidence_id=evidence_id,
                source_kind="repository-change",
                citation=source.citation,
                revision=source.commit_sha,
                acl_groups=tuple(sorted(set(change.acl.groups))),
                acl_users=tuple(sorted(set(change.acl.users))),
            )
        )
        self.brain.relate(
            source_id=repo,
            target_id=change_entity,
            kind=RelationshipKind.CHANGED_BY,
            evidence_ids=(evidence_id,),
        )
        self.brain.relate(
            source_id=repo,
            target_id=evidence_id,
            kind=RelationshipKind.HAS_EVIDENCE,
            evidence_ids=(evidence_id,),
        )
        self.brain.relate(
            source_id=change_entity,
            target_id=evidence_id,
            kind=RelationshipKind.HAS_EVIDENCE,
            evidence_ids=(evidence_id,),
        )

        entity_ids = [repo, change_entity]
        if change.service:
            service = service_id(change.service)
            self.brain.upsert_entity(
                BrainEntity(
                    entity_id=service,
                    kind=EntityKind.SERVICE,
                    label=change.service,
                    attributes=_attributes(repository=source.repository),
                )
            )
            self.brain.relate(
                source_id=service,
                target_id=repo,
                kind=RelationshipKind.BELONGS_TO,
                evidence_ids=(evidence_id,),
            )
            self.brain.relate(
                source_id=service,
                target_id=change_entity,
                kind=RelationshipKind.CHANGED_BY,
                evidence_ids=(evidence_id,),
            )
            self.brain.relate(
                source_id=service,
                target_id=evidence_id,
                kind=RelationshipKind.HAS_EVIDENCE,
                evidence_ids=(evidence_id,),
            )
            entity_ids.append(service)
            if change.owner:
                owner = owner_id(change.owner)
                self.brain.upsert_entity(
                    BrainEntity(entity_id=owner, kind=EntityKind.OWNER, label=change.owner)
                )
                self.brain.relate(
                    source_id=owner,
                    target_id=service,
                    kind=RelationshipKind.OWNS,
                    evidence_ids=(evidence_id,),
                )
                entity_ids.append(owner)
        return ProjectionResult(tuple(sorted(entity_ids)), evidence_id)

    def project_knowledge_document(self, document: KnowledgeDocument) -> ProjectionResult:
        document_kind = _entity_kind(document.identity.source_type)
        artifact = f"{document_kind.value}:{document.identity.provider}:{document.identity.source_id}"
        evidence_id = f"evidence:{document.identity.document_id}:{document.revision}"
        citation = document.source_url or document.identity.document_id
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=artifact,
                kind=document_kind,
                label=document.title,
                attributes=_attributes(
                    provider=document.identity.provider,
                    source_type=document.identity.source_type.value,
                    revision=document.revision,
                ),
            )
        )
        self.brain.record_evidence(
            BrainEvidence(
                evidence_id=evidence_id,
                source_kind=document.identity.source_type.value,
                citation=citation,
                revision=document.revision,
                acl_groups=tuple(sorted(set(document.acl.groups))),
                acl_users=tuple(sorted(set(document.acl.users))),
            )
        )
        self.brain.relate(
            source_id=artifact,
            target_id=evidence_id,
            kind=RelationshipKind.HAS_EVIDENCE,
            evidence_ids=(evidence_id,),
        )
        entity_ids = [artifact]
        if document.service:
            service = service_id(document.service)
            self.brain.upsert_entity(
                BrainEntity(entity_id=service, kind=EntityKind.SERVICE, label=document.service)
            )
            self.brain.relate(
                source_id=service,
                target_id=evidence_id,
                kind=RelationshipKind.HAS_EVIDENCE,
                evidence_ids=(evidence_id,),
            )
            if document_kind is EntityKind.ADR:
                self.brain.relate(
                    source_id=service,
                    target_id=artifact,
                    kind=RelationshipKind.GOVERNED_BY,
                    evidence_ids=(evidence_id,),
                )
            entity_ids.append(service)
        if document.owner:
            owner = owner_id(document.owner)
            self.brain.upsert_entity(BrainEntity(entity_id=owner, kind=EntityKind.OWNER, label=document.owner))
            self.brain.relate(
                source_id=owner,
                target_id=artifact,
                kind=RelationshipKind.OWNS,
                evidence_ids=(evidence_id,),
            )
            entity_ids.append(owner)
        unresolved = self._project_declared_operational_relationships(
            artifact=artifact,
            document=document,
            evidence_id=evidence_id,
        )
        return ProjectionResult(tuple(sorted(entity_ids)), evidence_id, unresolved)

    def _project_declared_operational_relationships(
        self,
        *,
        artifact: str,
        document: KnowledgeDocument,
        evidence_id: str,
    ) -> tuple[str, ...]:
        """Use explicit metadata only; causal facts are never inferred from prose."""
        unresolved: list[str] = []
        if document.identity.source_type is KnowledgeSourceType.INCIDENT:
            cause = document.metadata.get("caused_by")
            if cause:
                if cause in self.brain.entities:
                    self.brain.relate(
                        source_id=cause,
                        target_id=artifact,
                        kind=RelationshipKind.CAUSED,
                        evidence_ids=(evidence_id,),
                    )
                else:
                    unresolved.append(f"caused_by:{cause}")
            resolution = document.metadata.get("resolved_by")
            if resolution:
                if resolution in self.brain.entities:
                    self.brain.relate(
                        source_id=artifact,
                        target_id=resolution,
                        kind=RelationshipKind.RESOLVED_BY,
                        evidence_ids=(evidence_id,),
                    )
                else:
                    unresolved.append(f"resolved_by:{resolution}")
        return tuple(sorted(unresolved))


def _entity_kind(source_type: KnowledgeSourceType) -> EntityKind:
    return {
        KnowledgeSourceType.ADR: EntityKind.ADR,
        KnowledgeSourceType.DEPLOYMENT: EntityKind.DEPLOYMENT,
        KnowledgeSourceType.INCIDENT: EntityKind.INCIDENT,
        KnowledgeSourceType.RUNBOOK: EntityKind.RUNBOOK,
        KnowledgeSourceType.WORK_ITEM: EntityKind.WORK_ITEM,
        KnowledgeSourceType.CONVERSATION: EntityKind.CONVERSATION,
        KnowledgeSourceType.DOCUMENTATION: EntityKind.DOCUMENT,
    }[source_type]
