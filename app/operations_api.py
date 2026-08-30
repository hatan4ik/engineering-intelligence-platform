"""Compatibility façade for the operations application package.

New application code should import from ``app.operations`` submodules by
responsibility. This module preserves the original import surface for existing
CLIs and integrations while avoiding a second implementation of the routes.
"""

from app.operations.capability import (
    OPERATIONS_ENV_VARS,
    OperationsCapability,
    build_operations_capability,
    operations_enabled,
)
from app.operations.contracts import IncidentTrigger
from app.operations.evidence import AzureMonitorEvidenceProvider, FixtureEvidenceProvider
from app.operations.normalization import normalize_common_alert
from app.operations.presentation import deployment_report, incident_report
from app.operations.publishers import (
    GitHubDeploymentFailurePublisher,
    GitHubIncidentPublisher,
    NoOpOperationsPublisher,
    github_intelligence_client,
)
from app.operations.routes import SECRET_HEADER, router


__all__ = [
    "AzureMonitorEvidenceProvider",
    "FixtureEvidenceProvider",
    "GitHubDeploymentFailurePublisher",
    "GitHubIncidentPublisher",
    "IncidentTrigger",
    "NoOpOperationsPublisher",
    "OPERATIONS_ENV_VARS",
    "OperationsCapability",
    "SECRET_HEADER",
    "build_operations_capability",
    "deployment_report",
    "github_intelligence_client",
    "incident_report",
    "normalize_common_alert",
    "operations_enabled",
    "router",
]
