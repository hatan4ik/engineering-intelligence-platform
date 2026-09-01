"""Evidence adapters for the operational-intelligence application service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from integrations.azure.monitor import AzureMonitorQuery
from integrations.azure_devops.deployment_failure import DeploymentFailureEvent
from intelligence.incidents import EvidenceEvent, EvidenceKind


class AzureMonitorQueryClient(Protocol):
    def query(self, query: AzureMonitorQuery) -> list[EvidenceEvent]: ...


class FixtureEvidenceProvider:
    """Evidence from a JSON fixture for reference deployments, demos, and CLIs.

    The file is either a list of event objects or an object with any of the
    keys ``events`` (used on both paths), ``deployment_events``, and
    ``incident_events``. String fields may contain ``${service}``,
    ``${environment}``, ``${incident_id}``, and ``${deployment_id}``.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise RuntimeError(f"operations evidence fixture not found: {self.path}")
        raw: object = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            raw = {"events": raw}
        if not isinstance(raw, Mapping):
            raise RuntimeError(
                f"operations evidence fixture must be a list or object: {self.path}"
            )
        self._shared = _entries(raw, "events")
        self._deployment = _entries(raw, "deployment_events")
        self._incident = _entries(raw, "incident_events")

    def collect(
        self, *, incident_id: str, service: str, environment: str
    ) -> list[EvidenceEvent]:
        return self._build(
            (*self._shared, *self._incident),
            {
                "service": service,
                "environment": environment,
                "incident_id": incident_id,
            },
        )

    def evidence_for(self, event: DeploymentFailureEvent) -> list[EvidenceEvent]:
        return self._build(
            (*self._shared, *self._deployment),
            {
                "service": event.service,
                "environment": event.environment,
                "deployment_id": event.deployment_id,
            },
        )

    @staticmethod
    def _build(
        entries: Sequence[Mapping[str, object]],
        values: Mapping[str, str],
    ) -> list[EvidenceEvent]:
        return sorted(
            (_event_from_mapping(entry, values) for entry in entries),
            key=lambda event: event.timestamp,
        )


class AzureMonitorEvidenceProvider:
    """Live Azure Monitor evidence that satisfies both product evidence ports."""

    def __init__(
        self,
        client: AzureMonitorQueryClient,
        *,
        workspace_id: str,
        kql: str,
        lookback: timedelta,
    ) -> None:
        self.client = client
        self.workspace_id = workspace_id
        self.kql = kql
        self.lookback = lookback

    def collect(
        self, *, incident_id: str, service: str, environment: str
    ) -> list[EvidenceEvent]:
        return self._query(service)

    def evidence_for(self, event: DeploymentFailureEvent) -> list[EvidenceEvent]:
        return self._query(event.service)

    def _query(self, service: str) -> list[EvidenceEvent]:
        end = datetime.now(timezone.utc)
        return list(
            self.client.query(
                AzureMonitorQuery(
                    workspace_id=self.workspace_id,
                    service=service,
                    start=end - self.lookback,
                    end=end,
                    kql=self.kql.format(service=service),
                )
            )
        )


def _entries(
    payload: Mapping[str, object], key: str
) -> tuple[Mapping[str, object], ...]:
    raw = payload.get(key, [])
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise RuntimeError(f"operations evidence fixture field {key!r} must be a list")
    if not all(isinstance(entry, Mapping) for entry in raw):
        raise RuntimeError(
            f"operations evidence fixture field {key!r} must contain objects"
        )
    return tuple(raw)


def _substitute(value: str, values: Mapping[str, str]) -> str:
    for key, replacement in values.items():
        value = value.replace("${" + key + "}", replacement)
    return value


def _event_from_mapping(
    entry: Mapping[str, object], values: Mapping[str, str]
) -> EvidenceEvent:
    def text(name: str, default: str = "") -> str:
        return _substitute(str(entry.get(name, default) or default), values)

    timestamp = entry.get("timestamp")
    if not timestamp:
        raise RuntimeError("evidence fixture entry has no timestamp")
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    attributes = entry.get("attributes") or {}
    if isinstance(attributes, Mapping):
        pairs = tuple(
            sorted(
                (str(key), _substitute(str(value), values))
                for key, value in attributes.items()
            )
        )
    else:
        pairs = _attribute_pairs(attributes, values)

    return EvidenceEvent(
        id=text("id"),
        kind=EvidenceKind(str(entry.get("kind", "log")).lower()),
        service=text("service"),
        timestamp=parsed.astimezone(timezone.utc),
        summary=text("summary"),
        source=text("source", "fixture"),
        severity=_severity(entry.get("severity", 1)),
        attributes=pairs,
    )


def _attribute_pairs(
    value: object, substitutions: Mapping[str, str]
) -> tuple[tuple[str, str], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RuntimeError(
            "evidence fixture attributes must be an object or sequence of pairs"
        )
    pairs: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, Sequence)
            or isinstance(item, (str, bytes))
            or len(item) != 2
        ):
            raise RuntimeError(
                "evidence fixture attributes must contain key/value pairs"
            )
        pairs.append((str(item[0]), _substitute(str(item[1]), substitutions)))
    return tuple(sorted(pairs))


def _severity(value: object) -> int:
    """Accept an integer fixture severity without silently coercing strings or bools."""

    if type(value) is not int or value < 0:
        raise RuntimeError(
            "operations evidence fixture severity must be a non-negative integer"
        )
    return value
