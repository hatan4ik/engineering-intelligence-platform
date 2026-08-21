from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from .policy import ActionRequest


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str]) -> CommandResult: ...


class SubprocessRunner:
    """Executes argv directly; shell parsing/interpolation is intentionally disabled."""

    def run(self, argv: Sequence[str]) -> CommandResult:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)


class KubernetesActionAdapter:
    """Maps certified runbook IDs to fixed kubectl operations.

    The service name is used only as a Kubernetes Deployment name after strict
    validation. Model-generated commands are never accepted by this adapter.
    """

    def __init__(self, runner: CommandRunner | None = None, *, namespace: str = "default") -> None:
        self.runner = runner or SubprocessRunner()
        self.namespace = self._safe_name(namespace)

    @staticmethod
    def _safe_name(value: str) -> str:
        if not value or len(value) > 63:
            raise ValueError("invalid Kubernetes name")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-.")
        if value.lower() != value or any(ch not in allowed for ch in value):
            raise ValueError("invalid Kubernetes name")
        if value[0] in "-." or value[-1] in "-.":
            raise ValueError("invalid Kubernetes name")
        return value

    def _kubectl(self, *args: str) -> CommandResult:
        result = self.runner.run(("kubectl", "-n", self.namespace, *args))
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "kubectl command failed")
        return result

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        deployment = self._safe_name(request.service)
        if runbook_id == "aks.rollout.undo":
            result = self._kubectl("rollout", "undo", f"deployment/{deployment}")
        elif runbook_id == "aks.restart.workload":
            result = self._kubectl("rollout", "restart", f"deployment/{deployment}")
        else:
            raise ValueError(f"runbook has no Kubernetes action adapter: {runbook_id}")
        return result.stdout.strip() or f"kubectl:{runbook_id}:{deployment}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        deployment = self._safe_name(request.service)
        result = self._kubectl("get", f"deployment/{deployment}", "-o", "json")
        payload = json.loads(result.stdout)
        status = payload.get("status") or {}
        spec = payload.get("spec") or {}
        desired = int(spec.get("replicas") or 1)
        available = int(status.get("availableReplicas") or 0)
        ready = int(status.get("readyReplicas") or 0)
        if signal == "deployment.available_replicas":
            return available >= desired
        if signal == "deployment.ready_replicas":
            return ready >= desired
        raise ValueError(f"unsupported verification signal: {signal}")

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        deployment = self._safe_name(request.service)
        if rollback_id == "aks.rollout.redo":
            # Kubernetes has no generic 'redo'. A second undo returns to the prior
            # ReplicaSet only when rollout history supports it; therefore fail
            # closed and require escalation rather than pretending rollback is safe.
            raise RuntimeError(
                f"automatic redo is not safely defined for deployment/{deployment}; escalate"
            )
        raise ValueError(f"rollback has no Kubernetes action adapter: {rollback_id}")
