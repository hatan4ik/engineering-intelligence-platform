from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from azure.identity import DefaultAzureCredential

from intelligence.incidents import EvidenceEvent, EvidenceKind


@dataclass(frozen=True)
class AzureMonitorQuery:
    workspace_id: str
    service: str
    start: datetime
    end: datetime
    kql: str


class AzureMonitorEvidenceClient:
    """Concrete Azure Monitor Logs REST adapter using Entra credentials.

    The adapter intentionally returns normalized EvidenceEvent objects so the
    incident engine is independent from Azure response shape.
    """

    def __init__(self, credential: DefaultAzureCredential | None = None) -> None:
        self.credential = credential or DefaultAzureCredential()

    def _token(self) -> str:
        return self.credential.get_token("https://api.loganalytics.io/.default").token

    def _post(self, query: AzureMonitorQuery) -> dict[str, object]:
        url = f"https://api.loganalytics.io/v1/workspaces/{urllib.parse.quote(query.workspace_id)}/query"
        payload = json.dumps({
            "query": query.kql,
            "timespan": f"{query.start.astimezone(timezone.utc).isoformat()}/{query.end.astimezone(timezone.utc).isoformat()}",
        }).encode()
        req = urllib.request.Request(
            url,
            method="POST",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            raw: object = json.load(response)
        if not isinstance(raw, dict):
            raise RuntimeError("Azure Monitor query response must be a JSON object")
        return {str(key): value for key, value in raw.items()}

    def query(self, query: AzureMonitorQuery) -> list[EvidenceEvent]:
        payload = self._post(query)
        tables = payload.get("tables", [])
        if not isinstance(tables, list) or not tables:
            return []
        table = tables[0]
        if not isinstance(table, dict):
            return []
        columns = [str(c.get("name")) for c in table.get("columns", []) if isinstance(c, dict)]
        rows = table.get("rows", [])
        out: list[EvidenceEvent] = []
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            if not isinstance(row, list):
                continue
            values = dict(zip(columns, row))
            out.append(self._normalize_row(query.service, index, values))
        return out

    @staticmethod
    def _normalize_row(service: str, index: int, values: dict[str, object]) -> EvidenceEvent:
        timestamp = _parse_timestamp(values.get("TimeGenerated"))
        kind = _kind(str(values.get("Kind") or values.get("Type") or "log"))
        severity = _severity(values.get("SeverityLevel") or values.get("Severity"))
        summary = str(
            values.get("Message")
            or values.get("Summary")
            or values.get("OperationName")
            or values.get("Name")
            or "Azure Monitor evidence"
        )
        evidence_id = str(values.get("Id") or values.get("_ResourceId") or f"azure-monitor:{service}:{int(timestamp.timestamp())}:{index}")
        attrs = tuple(
            sorted(
                (str(k), str(v))
                for k, v in values.items()
                if v is not None and k not in {"Message", "Summary"}
            )
        )
        return EvidenceEvent(evidence_id, kind, service, timestamp, summary, "azure-monitor", severity, attrs)


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif value:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _kind(value: str) -> EvidenceKind:
    lowered = value.lower()
    if "deploy" in lowered:
        return EvidenceKind.DEPLOYMENT
    if "alert" in lowered:
        return EvidenceKind.ALERT
    if "metric" in lowered:
        return EvidenceKind.METRIC
    if "trace" in lowered or "request" in lowered or "dependenc" in lowered:
        return EvidenceKind.TRACE
    if "k8s" in lowered or "kube" in lowered:
        return EvidenceKind.K8S_EVENT
    return EvidenceKind.LOG


def _severity(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 1
    if isinstance(value, int):
        raw = value
    elif isinstance(value, str):
        try:
            raw = int(value)
        except ValueError:
            return 1
    else:
        return 1
    return max(1, min(5, raw))
