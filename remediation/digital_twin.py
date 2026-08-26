from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from .catalog import RunbookCatalog
from .kubernetes_adapter import CommandResult, KubernetesActionAdapter
from .policy import ActionRequest, ServiceAutonomy
from .simulation import SimulationResult, simulate


class InputCommandRunner(Protocol):
    def run(self, argv: Sequence[str], input_text: str | None = None) -> CommandResult: ...


class SubprocessInputRunner:
    """Runs fixed argv directly. Shell interpolation is intentionally disabled."""

    def run(self, argv: Sequence[str], input_text: str | None = None) -> CommandResult:
        proc = subprocess.run(
            list(argv),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class TwinEnvironment:
    namespace: str
    source_namespace: str
    service: str


class KubernetesDigitalTwin:
    """Ephemeral namespace sandbox for a single certified workload simulation.

    Source-only safety preconditions are checked against the real source namespace
    before cloning. The isolated clone then tests action execution and independent
    post-action verification; it does not invent rollout history or incident state.
    """

    def __init__(self, runner: InputCommandRunner | None = None) -> None:
        self.runner = runner or SubprocessInputRunner()

    @staticmethod
    def _safe_name(value: str) -> str:
        return KubernetesActionAdapter._safe_name(value)

    def _run(self, argv: Sequence[str], input_text: str | None = None) -> CommandResult:
        result = self.runner.run(argv, input_text)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(argv)}")
        return result

    def provision(self, *, simulation_id: str, service: str, source_namespace: str) -> TwinEnvironment:
        service = self._safe_name(service)
        source_namespace = self._safe_name(source_namespace)
        suffix = "".join(ch for ch in simulation_id.lower() if ch.isalnum() or ch == "-")[:30].strip("-") or "run"
        namespace = self._safe_name(f"eip-sim-{suffix}"[:63].rstrip("-"))

        self._run(("kubectl", "create", "namespace", namespace))
        try:
            self._run(("kubectl", "label", "namespace", namespace, "eip.openai/sandbox=true", "--overwrite"))
            raw = self._run((
                "kubectl", "-n", source_namespace, "get", f"deployment/{service}", "-o", "json"
            )).stdout
            source = json.loads(raw)
            clone = self._sanitize_deployment(source, namespace)
            self._run(
                ("kubectl", "-n", namespace, "apply", "-f", "-"),
                json.dumps(clone),
            )
            return TwinEnvironment(namespace, source_namespace, service)
        except Exception:
            self.destroy(namespace)
            raise

    @staticmethod
    def _sanitize_deployment(source: dict[str, object], namespace: str) -> dict[str, object]:
        metadata = dict(source.get("metadata") or {})
        spec = dict(source.get("spec") or {})
        labels = dict(metadata.get("labels") or {})
        labels["eip.openai/sandbox"] = "true"
        safe_metadata = {
            "name": metadata.get("name"),
            "namespace": namespace,
            "labels": labels,
            "annotations": {"eip.openai/source-uid": str(metadata.get("uid") or "unknown")},
        }
        template = dict(spec.get("template") or {})
        pod_spec = dict(template.get("spec") or {})
        pod_spec.pop("serviceAccountName", None)
        pod_spec["automountServiceAccountToken"] = False
        template["spec"] = pod_spec
        spec["template"] = template
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": safe_metadata,
            "spec": spec,
        }

    def destroy(self, namespace: str) -> None:
        namespace = self._safe_name(namespace)
        result = self.runner.run(("kubectl", "delete", "namespace", namespace, "--wait=false"))
        if result.returncode != 0 and "notfound" not in result.stderr.lower() and "not found" not in result.stderr.lower():
            raise RuntimeError(result.stderr.strip() or "failed to delete sandbox namespace")

    def simulate(
        self,
        *,
        simulation_id: str,
        source_namespace: str,
        catalog: RunbookCatalog,
        policy: ServiceAutonomy,
        request: ActionRequest,
        approval_verified: bool = False,
    ) -> SimulationResult:
        runbook = catalog.get(request.runbook_id)
        source_adapter = KubernetesActionAdapter(self.runner, namespace=source_namespace)
        allowed, reason = source_adapter.preflight(runbook, request)
        if not allowed:
            from remediation.executor import ExecutionResult
            from remediation.policy import PolicyDecision
            return SimulationResult(
                safe_to_promote=False,
                execution=ExecutionResult(
                    status="denied",
                    policy=PolicyDecision(False, reason),
                    error=reason,
                ),
                notes=("source preconditions failed; sandbox was not provisioned",),
            )

        env = self.provision(
            simulation_id=simulation_id,
            service=request.service,
            source_namespace=source_namespace,
        )
        try:
            adapter = KubernetesActionAdapter(
                self.runner,
                namespace=env.namespace,
                trusted_preconditions=runbook.preconditions,
            )
            return simulate(
                catalog=catalog,
                policy=policy,
                request=request,
                sandbox_adapter=adapter,
                approval_verified=approval_verified,
            )
        finally:
            self.destroy(env.namespace)
