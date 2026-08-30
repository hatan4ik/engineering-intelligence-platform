"""Startup wiring for optional API capabilities.

The API exposes routes whose backing services are optional per deployment
(PR Guardian over webhook, feedback capture, portal projections). Before this
module existed those services were only ever attached to ``app.state`` by
tests, so a real deployment answered 503 on four of six routes. Wiring is now
explicit: each capability is configured from the environment at startup, is
reported by ``/healthz``, and fails closed at startup when it is enabled but
incomplete.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.settings import ApplicationSettings, PRGuardianSettings

_PORTAL_PROVIDERS = (
    "service_intelligence_provider",
    "portfolio_intelligence_provider",
    "portfolio_trend_provider",
)


def capability_report(app: FastAPI, *, settings: ApplicationSettings) -> dict[str, str]:
    """Describe what this process can actually serve. Pure; safe to call from ``/healthz``."""

    guardian = getattr(app.state, "pr_guardian", None)
    recorder = getattr(app.state, "feedback_recorder", None)
    portal_ready = all(getattr(app.state, name, None) is not None for name in _PORTAL_PROVIDERS)
    operations = getattr(app.state, "operations", None)
    return {
        "query": settings.query.backend,
        "pr_guardian_webhook": getattr(guardian, "mode", "unconfigured") if guardian is not None else "unconfigured",
        "feedback_recorder": "sqlite" if recorder is not None else "unconfigured",
        "portal": "configured" if portal_ready else "unconfigured",
        "operations": "configured" if operations is not None else "unconfigured",
    }


def control_report(settings: ApplicationSettings) -> dict[str, str]:
    """Return non-secret, deployment-visible safety-control state.

    The value comes from the immutable process configuration, not an ambient
    environment reread. This is intentionally a report of the pod's starting
    state; the contract names any change as restart-required.
    """

    runtime = settings.runtime
    return {
        "control_plane_mode": runtime.control_plane_mode,
        "autonomy_kill_switch": (
            "engaged" if runtime.autonomy_kill_switch_engaged else "ready"
        ),
        "pr_guardian_kill_switch": (
            "engaged" if runtime.pr_guardian_kill_switch_engaged else "ready"
        ),
        "opa_evaluator": (
            "required" if runtime.opa_evaluator_required else "reference-optional"
        ),
        "kill_switch_update": runtime.kill_switch_update,
    }


def configure_capabilities(app: FastAPI, settings: ApplicationSettings) -> tuple[str, ...]:
    """Attach optional services to ``app.state`` from validated settings.

    Returns the names of the attributes this call configured so shutdown can
    remove exactly those and nothing a test or operator attached by hand.
    """

    configured: list[str] = []

    if settings.feedback_database is not None:
        from feedback.outcome_capture import OutcomeFeedbackRecorder
        from feedback.store import SqliteFeedbackStore

        app.state.feedback_recorder = OutcomeFeedbackRecorder(
            SqliteFeedbackStore(settings.feedback_database)
        )
        configured.append("feedback_recorder")

    if settings.pr_guardian.enabled:
        app.state.pr_guardian = _build_shadow_pr_guardian(settings.pr_guardian)
        configured.append("pr_guardian")

    if settings.query.backend == "azure":
        azure_rag = settings.query.azure_rag
        if azure_rag is None:
            raise RuntimeError("Azure query settings were not validated before composition")
        from app.rag.azure_backend import AzureRagBackendFactory

        app.state.azure_rag_backends = AzureRagBackendFactory(azure_rag)
        configured.append("azure_rag_backends")

    # Operational intelligence (L1 analysis + L2 proposals) is enabled by the
    # presence of any of its variables; an incomplete set raises here rather than
    # answering 503 forever. The capability factory owns that validation.
    from app.operations.capability import build_operations_capability, operations_enabled

    if operations_enabled(settings.operations):
        app.state.operations = build_operations_capability(settings.operations)
        configured.append("operations")

    return tuple(configured)


def release_capabilities(app: FastAPI, configured: tuple[str, ...]) -> None:
    for name in configured:
        if hasattr(app.state, name):
            delattr(app.state, name)


def _build_shadow_pr_guardian(settings: PRGuardianSettings):
    """Build the shadow-only guardian after settings validation has completed."""

    from control_plane.workflows import ControlPlaneWorkflows
    from integrations.github.pr_guardian import GitHubRestPRClient
    from product.graph_from_checkout import build_service_graph_from_checkout
    from product.pr_guardian.store import SqlitePRGuardianStore
    from product.pr_guardian_service import PRGuardianService
    from state.audit import SqliteAuditLog
    from state.store import SqliteStateStore

    state_dir = settings.state_directory
    graph_root = settings.service_graph_root
    token = settings.github_token
    if state_dir is None or graph_root is None or token is None:
        raise RuntimeError("PR Guardian settings were not validated before composition")
    state_dir.mkdir(parents=True, exist_ok=True)
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        SqliteAuditLog(state_dir / "audit.db"),
    )
    company_context, principal = _optional_company_brain_context(settings)
    return PRGuardianService(
        graph=(
            None
            if company_context is not None
            else build_service_graph_from_checkout(graph_root)
        ),
        github=GitHubRestPRClient(token),
        workflows=workflows,
        mode="shadow",
        company_context=company_context,
        principal=principal,
        findings=SqlitePRGuardianStore(state_dir / "pr-guardian.db"),
        policy_version=settings.policy_version,
    )


def _optional_company_brain_context(settings: PRGuardianSettings):
    """Return qualified Company Brain wiring only when its complete trust boundary is configured."""

    if settings.company_brain_database is None:
        return None, None
    tenant = settings.company_brain_tenant
    groups = settings.principal_groups
    if tenant is None or not groups:
        raise RuntimeError("Company Brain PR Guardian settings were not validated before composition")

    from company_brain import BrainPrincipal, CompanyBrainWorldModel, SqliteCompanyBrainStore
    from product.pr_guardian.company_brain import PRGuardianWorldModelAdapter

    return (
        PRGuardianWorldModelAdapter(
            CompanyBrainWorldModel(
                SqliteCompanyBrainStore(settings.company_brain_database),
                tenant,
            )
        ),
        BrainPrincipal(groups=groups),
    )
