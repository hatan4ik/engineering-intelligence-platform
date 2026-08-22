from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

from intelligence.incidents import EvidenceEvent, EvidenceKind


class LogQueryClient(Protocol):
    def query(self, *, workspace: str, query: str, timespan: str) -> Iterable[dict[str, object]]: ...


@dataclass
class AzureMonitorEvidenceProvider:
    client: LogQueryClient
    workspace: str
    timespan: str = "PT2H"

    def collect(self, *, incident_id: str, service: str, environment: str) -> list[EvidenceEvent]:
        query = (
            "union AppTraces, AppExceptions, KubeEvents, AzureActivity "
            f"| where tostring(ServiceName) == '{service.replace(chr(39), chr(39) * 2)}' "
            "| project TimeGenerated, Type, SeverityLevel, Message, OperationId"
        )
        events: list[EvidenceEvent] = []
        for index, row in enumerate(self.client.query(workspace=self.workspace, query=query, timespan=self.timespan)):
            raw_type = str(row.get("Type", "log")).lower()
            kind = EvidenceKind.K8S_EVENT if "kube" in raw_type else EvidenceKind.LOG
            timestamp = row.get("TimeGenerated")
            if isinstance(timestamp, datetime):
                ts = timestamp.astimezone(timezone.utc)
            else:
                ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
            severity = int(row.get("SeverityLevel") or 1)
            events.append(
                EvidenceEvent(
                    id=f"azure-monitor:{incident_id}:{index}",
                    kind=kind,
                    service=service,
                    timestamp=ts,
                    summary=str(row.get("Message") or raw_type),
                    source="azure-monitor",
                    severity=severity,
                    attributes=(("environment", environment), ("operation_id", str(row.get("OperationId") or ""))),
                )
            )
        return events
