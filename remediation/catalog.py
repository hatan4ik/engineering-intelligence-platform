from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    RECOMMEND = 1
    HUMAN_EXECUTE = 2
    APPROVE_AND_EXECUTE = 3
    BOUNDED_AUTONOMOUS = 4


@dataclass(frozen=True)
class Runbook:
    id: str
    description: str
    environments: tuple[str, ...]
    max_blast_radius: int
    reversible: bool
    required_level: AutonomyLevel
    verify_signal: str
    rollback_id: str | None = None


class RunbookCatalog:
    def __init__(self) -> None:
        self._items: dict[str, Runbook] = {}

    def register(self, runbook: Runbook) -> None:
        if runbook.id in self._items:
            raise ValueError(f"duplicate runbook: {runbook.id}")
        if runbook.required_level >= AutonomyLevel.APPROVE_AND_EXECUTE and not runbook.reversible:
            raise ValueError("automated production runbooks must be reversible")
        self._items[runbook.id] = runbook

    def get(self, runbook_id: str) -> Runbook:
        try:
            return self._items[runbook_id]
        except KeyError as exc:
            raise KeyError(f"unknown runbook: {runbook_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


def default_catalog() -> RunbookCatalog:
    catalog = RunbookCatalog()
    catalog.register(Runbook(
        id="aks.rollout.undo",
        description="Undo the current Kubernetes deployment rollout",
        environments=("dev", "stage", "prod"),
        max_blast_radius=10,
        reversible=True,
        required_level=AutonomyLevel.APPROVE_AND_EXECUTE,
        verify_signal="deployment.available_replicas",
        rollback_id="aks.rollout.redo",
    ))
    catalog.register(Runbook(
        id="aks.restart.workload",
        description="Restart a bounded Kubernetes deployment",
        environments=("dev", "stage", "prod"),
        max_blast_radius=5,
        reversible=True,
        required_level=AutonomyLevel.APPROVE_AND_EXECUTE,
        verify_signal="deployment.ready_replicas",
    ))
    catalog.register(Runbook(
        id="aks.scale.memory",
        description="Apply a pre-approved memory limit profile",
        environments=("dev", "stage"),
        max_blast_radius=5,
        reversible=True,
        required_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        verify_signal="container.oom_count",
        rollback_id="aks.scale.memory.rollback",
    ))
    return catalog
