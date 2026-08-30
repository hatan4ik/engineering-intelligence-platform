"""Composition and fail-closed configuration for operations intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from app.settings import OperationsSettings
from product.deployment_failure_service import (
    DeploymentFailureInvestigatorService,
    DeploymentOutputPublisher,
)
from product.incident_service import IncidentIntelligenceService, IncidentPublisher

from .evidence import AzureMonitorEvidenceProvider, FixtureEvidenceProvider
from .publishers import NoOpOperationsPublisher


# Compatibility/exported deployment-variable inventory. Environment parsing is
# owned by ``OperationsSettings`` rather than by this capability factory.
OPERATIONS_ENV_VARS: Final[tuple[str, ...]] = (
    "EIP_OPERATIONS_WEBHOOK_SECRET",
    "EIP_OPERATIONS_EVIDENCE",
)

_DEFAULT_EVIDENCE_KQL: Final[str] = (
    "union isfuzzy=true KubeEvents, AppExceptions, AppTraces "
    "| where Message has '{service}' or Name has '{service}' "
    "| project TimeGenerated, Kind=Type, SeverityLevel, Message, Id=_ItemId "
    "| order by TimeGenerated asc | take 200"
)


@dataclass(frozen=True)
class OperationsCapability:
    """The configured L1 analysis and L2-proposal services for one process."""

    evidence_mode: str
    incident: IncidentIntelligenceService
    deployment: DeploymentFailureInvestigatorService


def operations_enabled(settings: OperationsSettings) -> bool:
    """Whether validated settings explicitly enable operational intelligence."""

    return settings.enabled


def build_operations_capability(
    settings: OperationsSettings,
    *,
    incident_publisher: IncidentPublisher | None = None,
    deployment_publisher: DeploymentOutputPublisher | None = None,
    require_webhook_secret: bool = True,
) -> OperationsCapability:
    """Compose L1/L2 services from one validated runtime settings record."""

    from control_plane.workflows import ControlPlaneWorkflows
    from state.audit import SqliteAuditLog
    from state.store import SqliteStateStore
    from topology.store import SqliteTopologyStore

    try:
        settings.validate(require_webhook_secret=require_webhook_secret)
    except ValueError as error:
        raise RuntimeError(f"{error}; refusing to start half-configured") from error
    state_dir = settings.state_directory
    mode = settings.evidence_mode
    if state_dir is None or mode is None:
        raise RuntimeError("operations settings were not validated before composition")
    state_dir.mkdir(parents=True, exist_ok=True)
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        SqliteAuditLog(state_dir / "audit.db"),
    )
    topology = SqliteTopologyStore(settings.topology_database or state_dir / "topology.db")
    evidence = _build_evidence_provider(settings, mode)

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


def _build_evidence_provider(
    settings: OperationsSettings,
    mode: str,
) -> FixtureEvidenceProvider | AzureMonitorEvidenceProvider:
    if mode.startswith("fixture:"):
        return FixtureEvidenceProvider(mode.split(":", 1)[1].strip())

    from integrations.azure.monitor import AzureMonitorEvidenceClient

    workspace_id = settings.log_analytics_workspace_id
    if workspace_id is None:
        raise RuntimeError("operations settings were not validated before composition")
    return AzureMonitorEvidenceProvider(
        AzureMonitorEvidenceClient(),
        workspace_id=workspace_id,
        kql=settings.evidence_kql or _DEFAULT_EVIDENCE_KQL,
        lookback=timedelta(minutes=settings.evidence_lookback_minutes),
    )
