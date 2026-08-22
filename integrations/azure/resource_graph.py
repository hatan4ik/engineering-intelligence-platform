from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Mapping

from azure.identity import DefaultAzureCredential

from intelligence.drift import ResourceSnapshot


@dataclass(frozen=True)
class DesiredResource:
    resource_id: str
    service: str
    environment: str
    desired: Mapping[str, object]
    source: str


class AzureResourceGraphClient:
    """Query Azure Resource Graph using workload identity / DefaultAzureCredential."""

    def __init__(
        self,
        *,
        subscriptions: tuple[str, ...],
        credential: DefaultAzureCredential | None = None,
        api_version: str = "2022-10-01",
    ) -> None:
        self.subscriptions = subscriptions
        self.credential = credential or DefaultAzureCredential()
        self.api_version = api_version

    def _token(self) -> str:
        return self.credential.get_token("https://management.azure.com/.default").token

    def _post(self, query: str) -> dict[str, object]:
        if not self.subscriptions:
            raise ValueError("at least one Azure subscription is required")
        payload = json.dumps({
            "subscriptions": list(self.subscriptions),
            "query": query,
            "options": {"resultFormat": "objectArray"},
        }).encode()
        req = urllib.request.Request(
            f"https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version={self.api_version}",
            method="POST",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    def observed_by_id(self, resource_ids: tuple[str, ...], *, properties: tuple[str, ...]) -> dict[str, dict[str, object]]:
        if not resource_ids:
            return {}
        ids = ", ".join(_kusto_string(r.lower()) for r in resource_ids)
        projections = ["id", "type", "name", "location"]
        projections.extend(
            f"{_safe_alias(prop)}=tostring(properties.{prop})" for prop in properties
        )
        query = (
            "resources | extend normalized_id=tolower(id) "
            f"| where normalized_id in ({ids}) "
            f"| project {', '.join(projections)}"
        )
        payload = self._post(query)
        rows = payload.get("data", [])
        out: dict[str, dict[str, object]] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            out[str(row["id"]).lower()] = dict(row)
        return out


class AzureDriftSnapshotProvider:
    """Compose Git/Terraform desired state with Azure Resource Graph observations."""

    def __init__(self, graph: AzureResourceGraphClient, resources: tuple[DesiredResource, ...]) -> None:
        self.graph = graph
        self.resources = resources

    def desired(self, *, service: str, environment: str) -> list[ResourceSnapshot]:
        selected = tuple(
            r for r in self.resources if r.service == service and r.environment == environment
        )
        if not selected:
            return []
        property_names = tuple(sorted({key for r in selected for key in r.desired}))
        observed = self.graph.observed_by_id(
            tuple(r.resource_id for r in selected), properties=property_names
        )
        snapshots: list[ResourceSnapshot] = []
        for resource in selected:
            row = observed.get(resource.resource_id.lower(), {})
            observed_values = {
                key: row.get(_safe_alias(key))
                for key in resource.desired
            }
            if not row:
                observed_values["resource_exists"] = False
                desired_values = dict(resource.desired)
                desired_values["resource_exists"] = True
            else:
                desired_values = dict(resource.desired)
            snapshots.append(ResourceSnapshot(
                resource_id=resource.resource_id,
                service=resource.service,
                environment=resource.environment,
                desired=desired_values,
                observed=observed_values,
                source=resource.source,
            ))
        return snapshots


def _safe_alias(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "p_" + cleaned
    return cleaned


def _kusto_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
