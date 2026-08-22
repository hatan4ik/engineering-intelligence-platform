from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentFailureEvent:
    project: str
    pipeline_id: str
    run_id: str
    deployment_id: str
    service: str
    environment: str
    commit_sha: str | None = None


def normalize_service_hook(payload: dict[str, object]) -> DeploymentFailureEvent:
    try:
        resource = payload["resource"]  # type: ignore[index]
        project = str(resource["project"]["name"])  # type: ignore[index]
        definition = resource.get("definition", {})  # type: ignore[union-attr]
        pipeline_id = str(definition.get("id") or resource.get("definitionId"))  # type: ignore[union-attr]
        run_id = str(resource["id"])  # type: ignore[index]
        result = str(resource.get("result", "")).lower()  # type: ignore[union-attr]
        if result not in {"failed", "canceled", "partiallySucceeded".lower()}:
            raise ValueError("event is not a failed deployment/run")
        service = str(resource.get("service") or definition.get("name") or "unknown")  # type: ignore[union-attr]
        environment = str(resource.get("environment") or "unknown")  # type: ignore[union-attr]
        commit_sha = resource.get("sourceVersion")  # type: ignore[union-attr]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid Azure DevOps deployment failure payload") from exc
    return DeploymentFailureEvent(
        project=project,
        pipeline_id=pipeline_id,
        run_id=run_id,
        deployment_id=f"ado:{project}:{pipeline_id}:{run_id}",
        service=service,
        environment=environment,
        commit_sha=str(commit_sha) if commit_sha else None,
    )
