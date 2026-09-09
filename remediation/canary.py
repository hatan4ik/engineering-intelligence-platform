from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .catalog import Runbook
from .policy import ActionRequest


@dataclass(frozen=True)
class CanaryStrategy:
    """Declares progressive rollout constraints and verification gates."""

    canary_percentage: int = 10
    soak_seconds: float = 30.0
    canary_verify_signal: str = "deployment.canary_ready"
    full_verify_signal: str = "deployment.ready_replicas"


@dataclass(frozen=True)
class CanaryStep:
    phase: str
    status: str
    details: str


@dataclass(frozen=True)
class CanaryExecutionResult:
    status: str
    canary_verified: bool
    fleet_verified: bool
    steps: tuple[CanaryStep, ...]
    error: str | None = None


class ActionAdapter(Protocol):
    def execute(self, runbook_id: str, request: ActionRequest) -> str: ...
    def verify(self, signal: str, request: ActionRequest) -> bool: ...
    def rollback(self, rollback_id: str, request: ActionRequest) -> str: ...


class ProgressiveCanaryExecutor:
    """Executes runbooks progressively: canary first, then fleet upon verification."""

    def __init__(self, adapter: ActionAdapter) -> None:
        self.adapter = adapter

    def execute_progressive(
        self,
        runbook: Runbook,
        request: ActionRequest,
        strategy: CanaryStrategy | None = None,
    ) -> CanaryExecutionResult:
        strat = strategy or CanaryStrategy()
        steps: list[CanaryStep] = []

        # Phase 1: Deploy Canary Slice
        canary_runbook_id = f"{runbook.id}.canary"
        try:
            canary_ref = self.adapter.execute(canary_runbook_id, request)
            steps.append(
                CanaryStep(
                    phase="canary_deploy",
                    status="succeeded",
                    details=f"Canary slice deployed with ref {canary_ref}",
                )
            )
        except Exception as exc:
            steps.append(
                CanaryStep(
                    phase="canary_deploy",
                    status="failed",
                    details=f"Canary deployment failed: {exc}",
                )
            )
            return CanaryExecutionResult(
                status="aborted",
                canary_verified=False,
                fleet_verified=False,
                steps=tuple(steps),
                error=f"canary deployment failed: {exc}",
            )

        # Phase 2: Verify Canary Health
        canary_verified = False
        try:
            canary_verified = self.adapter.verify(strat.canary_verify_signal, request)
        except Exception as exc:
            steps.append(
                CanaryStep(
                    phase="canary_verify",
                    status="failed",
                    details=f"Canary verification error: {exc}",
                )
            )
        else:
            steps.append(
                CanaryStep(
                    phase="canary_verify",
                    status="succeeded" if canary_verified else "degraded",
                    details=f"Canary verification signal '{strat.canary_verify_signal}' result={canary_verified}",
                )
            )

        # Phase 3a: Canary Verification Failed -> Abort & Rollback Canary Slice
        if not canary_verified:
            rollback_ref = None
            if runbook.rollback_id:
                try:
                    rollback_ref = self.adapter.rollback(runbook.rollback_id, request)
                except Exception as exc:
                    steps.append(
                        CanaryStep(
                            phase="canary_abort",
                            status="failed",
                            details=f"Canary rollback failed: {exc}",
                        )
                    )
            steps.append(
                CanaryStep(
                    phase="canary_abort",
                    status="completed",
                    details=f"Aborted canary mutation without touching main fleet; rollback_ref={rollback_ref}",
                )
            )
            return CanaryExecutionResult(
                status="aborted",
                canary_verified=False,
                fleet_verified=False,
                steps=tuple(steps),
                error="canary health verification failed; rollout safely aborted",
            )

        # Phase 3b: Canary Passed -> Promote to 100% Workload Fleet
        try:
            fleet_ref = self.adapter.execute(runbook.id, request)
            steps.append(
                CanaryStep(
                    phase="fleet_promote",
                    status="succeeded",
                    details=f"Promoted to full fleet with ref {fleet_ref}",
                )
            )
        except Exception as exc:
            steps.append(
                CanaryStep(
                    phase="fleet_promote",
                    status="failed",
                    details=f"Fleet promotion failed: {exc}",
                )
            )
            return CanaryExecutionResult(
                status="failed",
                canary_verified=True,
                fleet_verified=False,
                steps=tuple(steps),
                error=f"fleet promotion failed: {exc}",
            )

        # Phase 4: Verify Fleet Health
        fleet_verified = False
        try:
            fleet_verified = self.adapter.verify(strat.full_verify_signal, request)
        except Exception as exc:
            steps.append(
                CanaryStep(
                    phase="fleet_verify",
                    status="failed",
                    details=f"Fleet verification error: {exc}",
                )
            )
        else:
            steps.append(
                CanaryStep(
                    phase="fleet_verify",
                    status="succeeded" if fleet_verified else "degraded",
                    details=f"Fleet verification signal '{strat.full_verify_signal}' result={fleet_verified}",
                )
            )

        if not fleet_verified:
            if runbook.rollback_id:
                try:
                    self.adapter.rollback(runbook.rollback_id, request)
                except Exception as exc:
                    steps.append(
                        CanaryStep(
                            phase="fleet_rollback",
                            status="failed",
                            details=f"Fleet rollback failed: {exc}",
                        )
                    )
            return CanaryExecutionResult(
                status="failed",
                canary_verified=True,
                fleet_verified=False,
                steps=tuple(steps),
                error="fleet health verification failed after promotion",
            )

        return CanaryExecutionResult(
            status="succeeded",
            canary_verified=True,
            fleet_verified=True,
            steps=tuple(steps),
        )

