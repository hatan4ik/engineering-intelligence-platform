from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from .catalog import Runbook
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

    Model-generated commands and free-form resources are never accepted. Safety
    conditions are evaluated from Kubernetes state immediately before mutation.
    A digital twin may mark conditions as trusted only after the same adapter has
    validated them against the source namespace before sandbox provisioning.
    """

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        namespace: str = "default",
        workload_label_key: str = "app",
        trusted_preconditions: tuple[str, ...] = (),
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.namespace = self._safe_name(namespace)
        self.workload_label_key = self._safe_label_key(workload_label_key)
        self.trusted_preconditions = frozenset(trusted_preconditions)

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

    @staticmethod
    def _safe_label_key(value: str) -> str:
        if not value or len(value) > 253:
            raise ValueError("invalid Kubernetes label key")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/")
        if any(ch not in allowed for ch in value):
            raise ValueError("invalid Kubernetes label key")
        return value

    def _kubectl(self, *args: str) -> CommandResult:
        result = self.runner.run(("kubectl", "-n", self.namespace, *args))
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "kubectl command failed")
        return result

    def _deployment(self, request: ActionRequest) -> dict[str, object]:
        deployment = self._safe_name(request.service)
        result = self._kubectl("get", f"deployment/{deployment}", "-o", "json")
        return json.loads(result.stdout)

    def _pods(self, request: ActionRequest) -> list[dict[str, object]]:
        deployment = self._safe_name(request.service)
        result = self._kubectl(
            "get", "pods", "-l", f"{self.workload_label_key}={deployment}", "-o", "json"
        )
        payload = json.loads(result.stdout)
        return list(payload.get("items") or [])

    @staticmethod
    def _is_degraded(payload: dict[str, object]) -> bool:
        spec = payload.get("spec") or {}
        status = payload.get("status") or {}
        desired = int(spec.get("replicas") or 1)
        ready = int(status.get("readyReplicas") or 0)
        available = int(status.get("availableReplicas") or 0)
        return ready < desired or available < desired

    @staticmethod
    def _pod_reason_present(pods: list[dict[str, object]], reasons: set[str]) -> bool:
        for pod in pods:
            statuses = (pod.get("status") or {}).get("containerStatuses") or []
            for status in statuses:
                current = (status.get("state") or {}).get("waiting") or {}
                previous = (status.get("lastState") or {}).get("terminated") or {}
                if str(current.get("reason") or "") in reasons or str(previous.get("reason") or "") in reasons:
                    return True
        return False

    def preflight(self, runbook: Runbook, request: ActionRequest) -> tuple[bool, str]:
        pending = tuple(c for c in runbook.preconditions if c not in self.trusted_preconditions)
        if not pending:
            return True, "all runbook preconditions were validated against the source environment"
        deployment = self._deployment(request)
        pods: list[dict[str, object]] | None = None
        for condition in pending:
            if condition == "deployment.exists":
                continue
            if condition == "deployment.degraded":
                if not self._is_degraded(deployment):
                    return False, "precondition failed: deployment is not degraded"
                continue
            if condition == "rollout.history_available":
                name = self._safe_name(request.service)
                history = self._kubectl("rollout", "history", f"deployment/{name}")
                revisions = [line for line in history.stdout.splitlines() if line.strip()[:1].isdigit()]
                if len(revisions) < 2:
                    return False, "precondition failed: rollback history has fewer than two revisions"
                continue
            if condition in {"pods.crashloop_present", "pods.oomkilled_present"}:
                pods = pods if pods is not None else self._pods(request)
                reasons = {"CrashLoopBackOff"} if condition == "pods.crashloop_present" else {"OOMKilled"}
                if not self._pod_reason_present(pods, reasons):
                    return False, f"precondition failed: {condition}"
                continue
            if condition == "memory.profile_preapproved":
                annotations = (deployment.get("metadata") or {}).get("annotations") or {}
                if str(annotations.get("eip.simdream.io/memory-profile-approved", "")).lower() != "true":
                    return False, "precondition failed: memory profile is not pre-approved"
                continue
            return False, f"unsupported precondition: {condition}"
        return True, "all certified runbook preconditions satisfied"

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        deployment = self._safe_name(request.service)
        if runbook_id in {"aks.rollout.undo", "aks.rollback.readiness"}:
            result = self._kubectl("rollout", "undo", f"deployment/{deployment}")
        elif runbook_id in {"aks.restart.workload", "aks.restart.crashloop", "aks.restart.oom"}:
            result = self._kubectl("rollout", "restart", f"deployment/{deployment}")
        elif runbook_id == "aks.scale.memory":
            payload = self._deployment(request)
            annotations = (payload.get("metadata") or {}).get("annotations") or {}
            limit = str(annotations.get("eip.simdream.io/memory-limit") or "")
            request_memory = str(annotations.get("eip.simdream.io/memory-request") or "")
            if not limit or not request_memory:
                raise RuntimeError("pre-approved memory profile values are missing")
            result = self._kubectl(
                "set", "resources", f"deployment/{deployment}",
                f"--limits=memory={limit}", f"--requests=memory={request_memory}",
            )
        else:
            raise ValueError(f"runbook has no Kubernetes action adapter: {runbook_id}")
        return result.stdout.strip() or f"kubectl:{runbook_id}:{deployment}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        if signal in {"deployment.available_replicas", "deployment.ready_replicas"}:
            payload = self._deployment(request)
            status = payload.get("status") or {}
            spec = payload.get("spec") or {}
            desired = int(spec.get("replicas") or 1)
            available = int(status.get("availableReplicas") or 0)
            ready = int(status.get("readyReplicas") or 0)
            if signal == "deployment.available_replicas":
                return available >= desired
            return ready >= desired
        if signal == "container.oom_count":
            return not self._pod_reason_present(self._pods(request), {"OOMKilled"})
        raise ValueError(f"unsupported verification signal: {signal}")

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        deployment = self._safe_name(request.service)
        if rollback_id == "aks.rollout.redo":
            raise RuntimeError(
                f"automatic redo is not safely defined for deployment/{deployment}; escalate"
            )
        if rollback_id == "aks.scale.memory.rollback":
            payload = self._deployment(request)
            annotations = (payload.get("metadata") or {}).get("annotations") or {}
            limit = str(annotations.get("eip.simdream.io/memory-previous-limit") or "")
            request_memory = str(annotations.get("eip.simdream.io/memory-previous-request") or "")
            if not limit or not request_memory:
                raise RuntimeError("previous memory profile is unavailable; escalate")
            result = self._kubectl(
                "set", "resources", f"deployment/{deployment}",
                f"--limits=memory={limit}", f"--requests=memory={request_memory}",
            )
            return result.stdout.strip() or f"kubectl:{rollback_id}:{deployment}"
        raise ValueError(f"rollback has no Kubernetes action adapter: {rollback_id}")
