from __future__ import annotations

from typing import Protocol


class KnowledgeProvider(Protocol):
    def search(self, query: str, *, principals: tuple[str, ...], top: int = 8) -> list[dict[str, object]]: ...


class ObservabilityProvider(Protocol):
    def service_events(self, service: str, *, since_seconds: int) -> list[dict[str, object]]: ...


class KubernetesProvider(Protocol):
    def deployment_status(self, namespace: str, deployment: str) -> dict[str, object]: ...
    def execute_runbook(self, runbook_id: str, *, namespace: str, target: str) -> str: ...


class IdentityProvider(Protocol):
    def principals_for_user(self, user_id: str) -> tuple[str, ...]: ...


class CloudResourceProvider(Protocol):
    def service_health(self, region: str) -> dict[str, object]: ...
    def resource_dependencies(self, resource_id: str) -> tuple[str, ...]: ...


class AuditProvider(Protocol):
    def append(self, event: dict[str, object]) -> None: ...
