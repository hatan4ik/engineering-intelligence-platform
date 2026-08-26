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

import os
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI

_PORTAL_PROVIDERS = (
    "service_intelligence_provider",
    "portfolio_intelligence_provider",
    "portfolio_trend_provider",
)


def capability_report(app: FastAPI, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Describe what this process can actually serve. Pure; safe to call from ``/healthz``."""

    source = os.environ if environ is None else environ
    guardian = getattr(app.state, "pr_guardian", None)
    recorder = getattr(app.state, "feedback_recorder", None)
    portal_ready = all(getattr(app.state, name, None) is not None for name in _PORTAL_PROVIDERS)
    return {
        "query": source.get("EIP_BACKEND", "deterministic").strip().lower() or "deterministic",
        "pr_guardian_webhook": getattr(guardian, "mode", "unconfigured") if guardian is not None else "unconfigured",
        "feedback_recorder": "sqlite" if recorder is not None else "unconfigured",
        "portal": "configured" if portal_ready else "unconfigured",
    }


def configure_capabilities(app: FastAPI, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Attach optional services to ``app.state`` from the environment.

    Returns the names of the attributes this call configured so shutdown can
    remove exactly those and nothing a test or operator attached by hand.
    """

    source = os.environ if environ is None else environ
    configured: list[str] = []

    feedback_db = source.get("EIP_FEEDBACK_DB", "").strip()
    if feedback_db:
        from feedback.outcome_capture import OutcomeFeedbackRecorder
        from feedback.store import SqliteFeedbackStore

        app.state.feedback_recorder = OutcomeFeedbackRecorder(SqliteFeedbackStore(feedback_db))
        configured.append("feedback_recorder")

    if source.get("EIP_PR_GUARDIAN_WEBHOOK", "").strip().lower() == "enabled":
        app.state.pr_guardian = _build_shadow_pr_guardian(source)
        configured.append("pr_guardian")

    return tuple(configured)


def release_capabilities(app: FastAPI, configured: tuple[str, ...]) -> None:
    for name in configured:
        if hasattr(app.state, name):
            delattr(app.state, name)


def _build_shadow_pr_guardian(source: Mapping[str, str]):
    missing = [name for name in ("GITHUB_TOKEN", "EIP_STATE_DIR", "EIP_SERVICE_GRAPH_ROOT") if not source.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "EIP_PR_GUARDIAN_WEBHOOK=enabled requires " + ", ".join(missing) + "; refusing to start half-configured"
        )

    from control_plane.workflows import ControlPlaneWorkflows
    from integrations.github.pr_guardian import GitHubRestPRClient
    from product.graph_from_checkout import build_service_graph_from_checkout
    from product.pr_guardian_service import PRGuardianService
    from state.audit import SqliteAuditLog
    from state.store import SqliteStateStore

    state_dir = Path(source["EIP_STATE_DIR"])
    state_dir.mkdir(parents=True, exist_ok=True)
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        SqliteAuditLog(state_dir / "audit.db"),
    )
    return PRGuardianService(
        graph=build_service_graph_from_checkout(source["EIP_SERVICE_GRAPH_ROOT"]),
        github=GitHubRestPRClient(source["GITHUB_TOKEN"]),
        workflows=workflows,
        mode="shadow",
    )
