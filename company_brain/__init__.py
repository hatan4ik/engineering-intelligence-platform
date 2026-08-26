"""Canonical organizational memory and world-model contracts.

The Company Brain is the shared, governed substrate consumed by product
workflows. It contains facts and evidence; it does not grant action authority.
"""

from .model import (
    BrainEntity,
    BrainEvidence,
    BrainPrincipal,
    CompanyBrain,
    CompanyBrainContext,
    CompanyBrainError,
    EntityKind,
    RelationshipKind,
)
from .projector import CompanyBrainProjector, ProjectionResult, repository_id, service_id

__all__ = [
    "BrainEntity",
    "BrainEvidence",
    "BrainPrincipal",
    "CompanyBrain",
    "CompanyBrainContext",
    "CompanyBrainError",
    "EntityKind",
    "RelationshipKind",
    "CompanyBrainProjector",
    "ProjectionResult",
    "repository_id",
    "service_id",
]
