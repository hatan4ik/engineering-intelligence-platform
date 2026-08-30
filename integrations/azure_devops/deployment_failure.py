from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, NewType


ProjectName = NewType("ProjectName", str)
PipelineId = NewType("PipelineId", str)
RunId = NewType("RunId", str)
DeploymentId = NewType("DeploymentId", str)


class AzureDevOpsEventError(ValueError):
    """An untrusted Azure DevOps service-hook payload has an invalid shape."""


@dataclass(frozen=True)
class DeploymentFailureEvent:
    project: ProjectName
    pipeline_id: PipelineId
    run_id: RunId
    deployment_id: DeploymentId
    service: str
    environment: str
    commit_sha: str | None = None


def normalize_service_hook(payload: Mapping[str, object]) -> DeploymentFailureEvent:
    """Normalize a failed Azure DevOps run without coercing arbitrary JSON values.

    The service hook is an untrusted external boundary. Identifiers may be the
    numeric or string representation Azure DevOps emits, while descriptive
    fields must be text. Invalid payloads are rejected before they enter the
    incident-intelligence domain.
    """

    try:
        resource = _required_mapping(payload, "resource")
        project = ProjectName(_required_text(_required_mapping(resource, "project"), "name"))
        definition = _optional_mapping(resource.get("definition"), "resource.definition")
        pipeline_id = PipelineId(
            _first_identifier(
                definition.get("id"),
                resource.get("definitionId"),
                label="resource.definition.id or resource.definitionId",
            )
        )
        run_id = RunId(_required_identifier(resource.get("id"), "resource.id"))
        result = _required_text(resource, "result").casefold()
        if result not in {"failed", "canceled", "partiallysucceeded"}:
            raise AzureDevOpsEventError("event is not a failed deployment/run")
        service = _optional_text(resource.get("service"), "resource.service") or _optional_text(
            definition.get("name"), "resource.definition.name"
        ) or "unknown"
        environment = _optional_text(resource.get("environment"), "resource.environment") or "unknown"
        commit_sha = _optional_text(resource.get("sourceVersion"), "resource.sourceVersion")
    except AzureDevOpsEventError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise AzureDevOpsEventError("invalid Azure DevOps deployment failure payload") from error
    return DeploymentFailureEvent(
        project=project,
        pipeline_id=pipeline_id,
        run_id=run_id,
        deployment_id=DeploymentId(f"ado:{project}:{pipeline_id}:{run_id}"),
        service=service,
        environment=environment,
        commit_sha=commit_sha,
    )


def _required_mapping(payload: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise AzureDevOpsEventError(f"{field} must be an object")
    return value


def _optional_mapping(value: object, label: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AzureDevOpsEventError(f"{label} must be an object when supplied")
    return value


def _required_text(payload: Mapping[str, object], field: str) -> str:
    return _optional_text(payload.get(field), field, required=True) or ""


def _optional_text(value: object, label: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise AzureDevOpsEventError(f"{label} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise AzureDevOpsEventError(f"{label} must be a non-empty string")
    return value.strip()


def _required_identifier(value: object, label: str) -> str:
    if isinstance(value, bool) or value is None:
        raise AzureDevOpsEventError(f"{label} is required")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise AzureDevOpsEventError(f"{label} must be a non-empty string or integer")


def _first_identifier(*values: object, label: str) -> str:
    for value in values:
        if value is not None:
            return _required_identifier(value, label)
    raise AzureDevOpsEventError(f"{label} is required")
