"""Operational-intelligence triggers: the first real entry points into L1/L2.

Two webhook routes turn an Azure DevOps deployment-failure service hook and an
Azure Monitor common-alert-schema payload into an evidence-backed analysis (L1)
and a set of proposals a human executes (L2, see ``product/l2_proposals.py``).

The routes never execute a proposal, never mutate a deployment, and never grant
autonomy. The HTTP response *is* the delivery mechanism; ``--publish github`` in
the two CLIs is the only other output path, and it opens an issue.

Configuration (see ``docs/OPERATIONS-INTELLIGENCE-RUNBOOK.md``):

``EIP_OPERATIONS_WEBHOOK_SECRET``
    Shared secret both routes require in the ``X-EIP-Operations-Secret`` header.
``EIP_OPERATIONS_EVIDENCE``
    ``azure-monitor`` (live Log Analytics) or ``fixture:<path>`` (a JSON evidence
    file, for reference deployments and the CLIs).
``EIP_STATE_DIR``
    Directory for the control-plane state, audit, and topology databases.
"""
from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from fastapi import APIRouter, Header, HTTPException, Request

from integrations.azure_devops.deployment_failure import DeploymentFailureEvent, normalize_service_hook
from integrations.github.pr_guardian import GitHubRestPRClient
from intelligence.deployment_failures import DeploymentFailureAnalysis
from intelligence.incidents import EvidenceEvent, EvidenceKind, IncidentAnalysis
from product.deployment_failure_service import DeploymentFailureInvestigatorService
from product.incident_service import IncidentIntelligenceService
from product.l2_proposals import build_proposals, proposals_to_dicts

#: Presence of any of these enables the capability; an incomplete set fails closed.
OPERATIONS_ENV_VARS: Final[tuple[str, ...]] = (
    "EIP_OPERATIONS_WEBHOOK_SECRET",
    "EIP_OPERATIONS_EVIDENCE",
)

#: Required in addition, for every evidence mode.
_ALWAYS_REQUIRED: Final[tuple[str, ...]] = (
    "EIP_OPERATIONS_WEBHOOK_SECRET",
    "EIP_OPERATIONS_EVIDENCE",
    "EIP_STATE_DIR",
)

#: The CLIs run the same composition without serving the webhook routes, so the
#: shared secret is not part of their required set.
_CLI_REQUIRED: Final[tuple[str, ...]] = ("EIP_OPERATIONS_EVIDENCE", "EIP_STATE_DIR")

#: ``AzureMonitorEvidenceClient`` builds a ``DefaultAzureCredential`` and queries a
#: Log Analytics workspace; these are the names that must be present for both.
_AZURE_MONITOR_REQUIRED: Final[tuple[str, ...]] = (
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID",
)

_DEFAULT_EVIDENCE_KQL: Final[str] = (
    "union isfuzzy=true KubeEvents, AppExceptions, AppTraces "
    "| where Message has '{service}' or Name has '{service}' "
    "| project TimeGenerated, Kind=Type, SeverityLevel, Message, Id=_ItemId "
    "| order by TimeGenerated asc | take 200"
)

SECRET_HEADER: Final[str] = "X-EIP-Operations-Secret"
OPERATIONS_ISSUE_MARKER: Final[str] = "<!-- eip-operations-intelligence -->"

router = APIRouter(prefix="/v1/events", tags=["operational-intelligence"])


# --------------------------------------------------------------------------- #
# Payload normalization
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IncidentTrigger:
    incident_id: str
    service: str
    environment: str
    fired: bool


def normalize_common_alert(payload: Mapping[str, Any]) -> IncidentTrigger:
    """Parse an Azure Monitor common alert schema payload into an incident scope.

    ``service`` and ``environment`` come from the alert rule's ``customProperties``;
    Azure Monitor has no other reliable carrier for them, and guessing them from
    resource ids would attribute evidence to the wrong service.
    """

    data = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        raise ValueError("common alert schema payload has no 'data' object")
    essentials = data.get("essentials")
    if not isinstance(essentials, Mapping):
        raise ValueError("common alert schema payload has no 'data.essentials' object")

    raw_id = str(essentials.get("originAlertId") or essentials.get("alertId") or "").strip()
    if not raw_id:
        raise ValueError("common alert schema payload has no alertId")
    incident_id = raw_id.rsplit("/", 1)[-1]

    properties = data.get("customProperties")
    if not isinstance(properties, Mapping):
        raise ValueError("alert is missing data.customProperties.service and .environment")
    missing = [name for name in ("service", "environment") if not str(properties.get(name) or "").strip()]
    if missing:
        raise ValueError("alert customProperties is missing " + ", ".join(missing))

    condition = str(essentials.get("monitorCondition") or "Fired").strip().lower()
    return IncidentTrigger(
        incident_id=incident_id,
        service=str(properties["service"]).strip(),
        environment=str(properties["environment"]).strip(),
        fired=condition == "fired",
    )


# --------------------------------------------------------------------------- #
# Evidence providers
# --------------------------------------------------------------------------- #


class FixtureEvidenceProvider:
    """Evidence from a JSON file. For reference deployments, demos, and the CLIs.

    The file is either a list of event objects or an object with any of the keys
    ``events`` (used on both paths), ``deployment_events``, and ``incident_events``.
    String fields may contain ``${service}``, ``${environment}``, ``${incident_id}``
    and ``${deployment_id}``; unknown tokens are left untouched.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise RuntimeError(f"operations evidence fixture not found: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            raw = {"events": raw}
        if not isinstance(raw, dict):
            raise RuntimeError(f"operations evidence fixture must be a list or object: {self.path}")
        self._shared = list(raw.get("events") or [])
        self._deployment = list(raw.get("deployment_events") or [])
        self._incident = list(raw.get("incident_events") or [])

    def collect(self, *, incident_id: str, service: str, environment: str) -> list[EvidenceEvent]:
        return self._build(
            self._shared + self._incident,
            {"service": service, "environment": environment, "incident_id": incident_id},
        )

    def evidence_for(self, event: DeploymentFailureEvent) -> list[EvidenceEvent]:
        return self._build(
            self._shared + self._deployment,
            {
                "service": event.service,
                "environment": event.environment,
                "deployment_id": event.deployment_id,
            },
        )

    def _build(self, entries: Sequence[Mapping[str, Any]], values: Mapping[str, str]) -> list[EvidenceEvent]:
        return sorted(
            (_event_from_mapping(entry, values) for entry in entries),
            key=lambda e: e.timestamp,
        )


def _substitute(value: str, values: Mapping[str, str]) -> str:
    for key, replacement in values.items():
        value = value.replace("${" + key + "}", replacement)
    return value


def _event_from_mapping(entry: Mapping[str, Any], values: Mapping[str, str]) -> EvidenceEvent:
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
        pairs = tuple(sorted((str(k), _substitute(str(v), values)) for k, v in attributes.items()))
    else:
        pairs = tuple(sorted((str(k), _substitute(str(v), values)) for k, v in attributes))

    return EvidenceEvent(
        id=text("id"),
        kind=EvidenceKind(str(entry.get("kind", "log")).lower()),
        service=text("service"),
        timestamp=parsed.astimezone(timezone.utc),
        summary=text("summary"),
        source=text("source", "fixture"),
        severity=int(entry.get("severity", 1)),
        attributes=pairs,
    )


class AzureMonitorEvidenceProvider:
    """Live evidence from Azure Monitor Logs. Satisfies both evidence protocols."""

    def __init__(self, client: Any, *, workspace_id: str, kql: str, lookback: timedelta) -> None:
        self.client = client
        self.workspace_id = workspace_id
        self.kql = kql
        self.lookback = lookback

    def collect(self, *, incident_id: str, service: str, environment: str) -> list[EvidenceEvent]:
        return self._query(service)

    def evidence_for(self, event: DeploymentFailureEvent) -> list[EvidenceEvent]:
        return self._query(event.service)

    def _query(self, service: str) -> list[EvidenceEvent]:
        from integrations.azure.monitor import AzureMonitorQuery

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


# --------------------------------------------------------------------------- #
# Publishers
# --------------------------------------------------------------------------- #


class NoOpOperationsPublisher:
    """The API response carries the analysis; nothing is pushed anywhere by default."""

    def publish(self, **_: Any) -> None:
        return None


def _issue_body(header: str, analysis_lines: Sequence[str], proposals: Sequence[dict[str, object]]) -> str:
    lines = [header, "", "## Evidence-backed analysis (L1)", ""]
    lines.extend(f"- {line}" for line in analysis_lines)
    lines.extend(["", "## Proposals (L2 - requires human execution)", ""])
    for proposal in proposals:
        lines.append(f"### {proposal['kind']}: {proposal['title']}")
        lines.append(f"- Exact action: {proposal['exact_action']}")
        lines.append(f"- Rollback path: {proposal['rollback_path']}")
        lines.append(f"- Evidence: {', '.join(str(ref) for ref in proposal['evidence_refs']) or 'none'}")
        lines.append("")
    lines.append(
        "This platform proposes only. Every action above requires human execution; "
        "nothing here has been applied."
    )
    return "\n".join(lines)


@dataclass
class GitHubIncidentPublisher:
    """Opens/updates one marked issue per repository with the incident proposals."""

    client: Any
    repository: str
    environment: str = "unknown"

    def publish(
        self,
        *,
        incident_id: str,
        service: str,
        analysis: IncidentAnalysis,
        impacted_services: tuple[str, ...],
    ) -> None:
        proposals = proposals_to_dicts(
            build_proposals(analysis, service=service, environment=self.environment)
        )
        lines = [f"impacted services: {', '.join(impacted_services)}"] + [
            f"{h.title} (confidence {h.confidence:.2f})" for h in analysis.hypotheses
        ]
        self.client.ensure_maintenance_issue(
            repository=self.repository,
            marker=OPERATIONS_ISSUE_MARKER,
            title=f"Incident {incident_id}: {service} operational intelligence",
            body=_issue_body(OPERATIONS_ISSUE_MARKER, lines, proposals),
            labels=("engineering-intelligence", "operational-intelligence"),
        )


@dataclass
class GitHubDeploymentFailurePublisher:
    """Opens/updates one marked issue per repository with the deployment proposals."""

    client: Any
    repository: str

    def publish(
        self,
        *,
        event: DeploymentFailureEvent,
        analysis: DeploymentFailureAnalysis,
        evidence: tuple[EvidenceEvent, ...] = (),
    ) -> None:
        proposals = proposals_to_dicts(
            build_proposals(
                analysis,
                service=event.service,
                environment=event.environment,
                evidence=evidence,
            )
        )
        lines = list(analysis.facts) + [
            f"{h.title} (confidence {h.confidence:.2f})" for h in analysis.hypotheses
        ]
        self.client.ensure_maintenance_issue(
            repository=self.repository,
            marker=OPERATIONS_ISSUE_MARKER,
            title=f"Deployment failure {analysis.deployment_id}: {event.service} operational intelligence",
            body=_issue_body(OPERATIONS_ISSUE_MARKER, lines, proposals),
            labels=("engineering-intelligence", "operational-intelligence"),
        )


def github_intelligence_client(token: str) -> GitHubRestPRClient:
    """The existing REST client already satisfies ``GitHubIntelligenceClient``."""

    return GitHubRestPRClient(token)


# --------------------------------------------------------------------------- #
# Capability construction
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OperationsCapability:
    evidence_mode: str
    incident: IncidentIntelligenceService
    deployment: DeploymentFailureInvestigatorService


def operations_enabled(source: Mapping[str, str]) -> bool:
    return any(source.get(name, "").strip() for name in OPERATIONS_ENV_VARS)


def build_operations_capability(
    source: Mapping[str, str],
    *,
    incident_publisher: Any | None = None,
    deployment_publisher: Any | None = None,
    require_webhook_secret: bool = True,
) -> OperationsCapability:
    """Compose the incident and deployment-failure services. Fails closed, loudly."""

    from control_plane.workflows import ControlPlaneWorkflows
    from state.audit import SqliteAuditLog
    from state.store import SqliteStateStore
    from topology.store import SqliteTopologyStore

    required = _ALWAYS_REQUIRED if require_webhook_secret else _CLI_REQUIRED
    missing = [name for name in required if not source.get(name, "").strip()]
    mode = source.get("EIP_OPERATIONS_EVIDENCE", "").strip()
    if mode and mode != "azure-monitor" and not mode.startswith("fixture:"):
        raise RuntimeError(
            "EIP_OPERATIONS_EVIDENCE must be 'azure-monitor' or 'fixture:<path>'; "
            f"got {mode!r}; refusing to start half-configured"
        )
    if mode == "azure-monitor":
        missing += [name for name in _AZURE_MONITOR_REQUIRED if not source.get(name, "").strip()]
    elif mode.startswith("fixture:") and not mode.split(":", 1)[1].strip():
        missing.append("EIP_OPERATIONS_EVIDENCE fixture path")
    if missing:
        raise RuntimeError(
            "operational intelligence requires " + ", ".join(missing) + "; refusing to start half-configured"
        )

    state_dir = Path(source["EIP_STATE_DIR"])
    state_dir.mkdir(parents=True, exist_ok=True)
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        SqliteAuditLog(state_dir / "audit.db"),
    )
    topology = SqliteTopologyStore(source.get("EIP_TOPOLOGY_DB", "").strip() or state_dir / "topology.db")
    evidence = _build_evidence_provider(source, mode)

    return OperationsCapability(
        evidence_mode=mode,
        incident=IncidentIntelligenceService(
            evidence=evidence,
            topology=topology,
            workflows=workflows,
            publisher=incident_publisher or NoOpOperationsPublisher(),
        ),
        deployment=DeploymentFailureInvestigatorService(
            evidence=evidence,
            workflows=workflows,
            publisher=deployment_publisher or NoOpOperationsPublisher(),
        ),
    )


def _build_evidence_provider(source: Mapping[str, str], mode: str) -> Any:
    if mode.startswith("fixture:"):
        return FixtureEvidenceProvider(mode.split(":", 1)[1].strip())

    from integrations.azure.monitor import AzureMonitorEvidenceClient

    minutes = int(source.get("EIP_OPERATIONS_EVIDENCE_LOOKBACK_MINUTES", "").strip() or "120")
    return AzureMonitorEvidenceProvider(
        AzureMonitorEvidenceClient(),
        workspace_id=source["EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID"].strip(),
        kql=source.get("EIP_OPERATIONS_EVIDENCE_KQL", "").strip() or _DEFAULT_EVIDENCE_KQL,
        lookback=timedelta(minutes=minutes),
    )


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def _hypotheses_to_dicts(analysis: IncidentAnalysis | DeploymentFailureAnalysis) -> list[dict[str, object]]:
    return [
        {
            "title": h.title,
            "confidence": round(h.confidence, 4),
            "facts": list(h.facts),
            "inferences": list(h.inferences),
            "evidence_ids": list(h.evidence_ids),
        }
        for h in analysis.hypotheses
    ]


def _timeline_to_dicts(events: Sequence[EvidenceEvent]) -> list[dict[str, object]]:
    return [
        {
            "id": e.id,
            "kind": e.kind.value,
            "service": e.service,
            "timestamp": e.timestamp.isoformat(),
            "summary": e.summary,
            "source": e.source,
            "severity": e.severity,
        }
        for e in events
    ]


def incident_analysis_to_dict(analysis: IncidentAnalysis) -> dict[str, object]:
    return {
        "hypotheses": _hypotheses_to_dicts(analysis),
        "timeline": _timeline_to_dicts(analysis.timeline),
    }


def deployment_analysis_to_dict(analysis: DeploymentFailureAnalysis) -> dict[str, object]:
    return {
        "deployment_id": analysis.deployment_id,
        "service": analysis.service,
        "facts": list(analysis.facts),
        "hypotheses": _hypotheses_to_dicts(analysis),
        "evidence_ids": list(analysis.evidence_ids),
    }


def deployment_report(event: DeploymentFailureEvent, result: Any) -> dict[str, object]:
    """The response/CLI document for a deployment-failure investigation."""

    proposals = build_proposals(
        result.analysis,
        service=event.service,
        environment=event.environment,
        evidence=result.evidence,
    )
    return {
        "status": "investigated",
        "autonomy_level": "L2-propose",
        "executed": False,
        "correlation_id": result.correlation_id,
        "workflow_id": result.workflow_id,
        "service": event.service,
        "environment": event.environment,
        "analysis": deployment_analysis_to_dict(result.analysis),
        "proposals": proposals_to_dicts(proposals),
    }


def incident_report(trigger: IncidentTrigger, result: Any) -> dict[str, object]:
    """The response/CLI document for an incident correlation."""

    proposals = build_proposals(
        result.analysis, service=trigger.service, environment=trigger.environment
    )
    return {
        "status": "investigated",
        "autonomy_level": "L2-propose",
        "executed": False,
        "correlation_id": result.correlation_id,
        "workflow_id": result.workflow_id,
        "incident_id": trigger.incident_id,
        "service": trigger.service,
        "environment": trigger.environment,
        "impacted_services": list(result.impacted_services),
        "analysis": incident_analysis_to_dict(result.analysis),
        "proposals": proposals_to_dicts(proposals),
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def _verify_secret(provided: str | None) -> None:
    expected = os.getenv("EIP_OPERATIONS_WEBHOOK_SECRET", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "operational intelligence is not configured on this deployment: "
                "EIP_OPERATIONS_WEBHOOK_SECRET is unset"
            ),
        )
    # Encode explicitly: compare_digest on str raises TypeError for non-ASCII, and a
    # header is attacker-controlled.
    if not provided or not hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8")):
        raise HTTPException(status_code=401, detail=f"invalid or missing {SECRET_HEADER} header")


def _capability(request: Request) -> OperationsCapability:
    capability = getattr(request.app.state, "operations", None)
    if capability is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "operational intelligence is not configured on this deployment: "
                "set EIP_OPERATIONS_EVIDENCE and EIP_STATE_DIR and restart"
            ),
        )
    return capability


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = json.loads(await request.body())
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="request body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    return payload


@router.post("/deployment")
async def deployment_event(
    request: Request,
    x_eip_operations_secret: str | None = Header(default=None),
) -> dict[str, object]:
    _verify_secret(x_eip_operations_secret)
    capability = _capability(request)
    payload = await _json_body(request)
    try:
        event = normalize_service_hook(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = capability.deployment.investigate(event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return deployment_report(event, result)


@router.post("/incident")
async def incident_event(
    request: Request,
    x_eip_operations_secret: str | None = Header(default=None),
) -> dict[str, object]:
    _verify_secret(x_eip_operations_secret)
    capability = _capability(request)
    payload = await _json_body(request)
    try:
        trigger = normalize_common_alert(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not trigger.fired:
        return {"status": "ignored", "reason": "monitorCondition is not Fired"}
    result = capability.incident.investigate(
        incident_id=trigger.incident_id,
        service=trigger.service,
        environment=trigger.environment,
    )
    return incident_report(trigger, result)
