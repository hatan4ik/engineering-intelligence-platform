"""Run the L3 certification exercise suite for one service/environment/runbook scope.

By default the suite runs against a **simulated** cluster: no kubectl process is
started and nothing outside this process is touched. That produces a rehearsal
of the bounded control loop -- useful for checking that the fail-closed paths
behave -- and it is explicitly *not* production certification evidence. Every
simulated record is written with ``"evidence_grade": "rehearsal"`` and the
report carries ``"production_evidence": false``.

``--runner kubectl`` runs the same suite against a real cluster through the
digital twin's ephemeral sandbox namespace. It fails closed without
``KUBECONFIG``, without ``kubectl`` on PATH, and without an explicit OPA
endpoint; there is no implicit local fallback for a run that claims real
evidence.

Usage::

    python scripts/run_l3_exercises.py --service payments --environment prod \\
        --runbook aks.restart.crashloop
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from remediation.catalog import AutonomyLevel, Runbook, RunbookCatalog, default_catalog
from remediation.digital_twin import KubernetesDigitalTwin, SubprocessInputRunner
from remediation.executor import ExecutionResult, execute_control_loop
from remediation.kubernetes_adapter import CommandResult, KubernetesActionAdapter
from remediation.opa_policy import (
    EvaluatedPolicyDecision,
    LocalReferenceEvaluator,
    OpaPolicyClient,
    PolicyControlState,
)
from remediation.policy import ActionRequest, PolicyDecision, ServiceAutonomy
from resilience.certification import build_certification_report
from resilience.exercises import ExerciseKind, ExerciseResult


REHEARSAL_GRADE = "rehearsal"
PRODUCTION_GRADE = "cluster-exercise"
DISCLAIMER = (
    "Simulated exercises rehearse the bounded control loop against an in-memory "
    "cluster. They are not production evidence and must never be submitted as "
    "L3 or L4 certification evidence."
)
CLUSTER_NOTE = (
    "Cluster exercises are an input to certification, not a certification. A "
    "certification decision additionally requires retained, independently "
    "reviewed evidence for the exact scope."
)


def scope_hash(service: str, environment: str, runbook_id: str) -> str:
    payload = f"{service}|{environment}|{runbook_id}".encode()
    return hashlib.sha256(payload).hexdigest()[:12]


# --- the simulated cluster ---------------------------------------------------


class UnavailablePolicyEvaluator:
    """Reproduces OPA's fail-closed contract without contacting anything."""

    def evaluate(self, **_: object) -> EvaluatedPolicyDecision:
        return EvaluatedPolicyDecision(
            False, "OPA unavailable or invalid: simulated policy outage", "unknown"
        )


class SimulatedClusterRunner:
    """Answers the fixed kubectl argv the twin and action adapter issue.

    It models exactly one workload: degraded before the remediation action and,
    unless the scenario says otherwise, healthy afterwards. Nothing is executed;
    the command list is retained so a caller can see what a real run would have
    done.
    """

    def __init__(self, *, service: str, replicas: int = 2, heals: bool = True) -> None:
        self.service = service
        self.replicas = replicas
        self.heals = heals
        self.mutated = False
        self.commands: list[list[str]] = []

    @property
    def healthy(self) -> bool:
        return self.mutated and self.heals

    def run(self, argv: Sequence[str], input_text: str | None = None) -> CommandResult:
        args = list(argv)
        self.commands.append(args)
        rest = args[3:] if len(args) > 2 and args[1] == "-n" else args[1:]
        if not rest:
            return CommandResult(1, "", "empty kubectl invocation")
        head = rest[0]
        if head in {"create", "delete"} and len(rest) > 1 and rest[1] == "namespace":
            return CommandResult(0, "namespace ok")
        if head in {"label", "apply"}:
            return CommandResult(0, "applied")
        if head == "get" and len(rest) > 1 and rest[1].startswith("deployment/"):
            return CommandResult(0, json.dumps(self._deployment()))
        if head == "get" and len(rest) > 1 and rest[1] == "pods":
            return CommandResult(0, json.dumps({"items": self._pods()}))
        if head == "rollout" and len(rest) > 1 and rest[1] == "history":
            return CommandResult(0, "REVISION  CHANGE-CAUSE\n1  <none>\n2  <none>\n3  <none>\n")
        if head == "rollout" and len(rest) > 1 and rest[1] in {"undo", "restart"}:
            self.mutated = True
            return CommandResult(0, f"deployment.apps/{self.service} {rest[1]}")
        if head == "set" and len(rest) > 1 and rest[1] == "resources":
            self.mutated = True
            return CommandResult(0, f"deployment.apps/{self.service} resource requirements updated")
        return CommandResult(1, "", f"simulated cluster has no answer for: {' '.join(args)}")

    def _deployment(self) -> dict:
        ready = self.replicas if self.healthy else 0
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": self.service,
                "uid": "simulated-uid",
                "labels": {"app": self.service},
                "annotations": {
                    "eip.simdream.io/memory-profile-approved": "true",
                    "eip.simdream.io/memory-limit": "1Gi",
                    "eip.simdream.io/memory-request": "512Mi",
                    "eip.simdream.io/memory-previous-limit": "512Mi",
                    "eip.simdream.io/memory-previous-request": "256Mi",
                },
            },
            "spec": {"replicas": self.replicas, "template": {"spec": {"containers": []}}},
            "status": {"readyReplicas": ready, "availableReplicas": ready},
        }

    def _pods(self) -> list[dict]:
        if self.healthy:
            return [{"status": {"containerStatuses": [{"state": {"running": {}}}]}}]
        return [
            {
                "status": {
                    "containerStatuses": [
                        {
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                            "lastState": {"terminated": {"reason": "OOMKilled"}},
                        }
                    ]
                }
            }
        ]


# --- the exercise suite ------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    kind: ExerciseKind
    description: str
    heals: bool = True
    kill_switch: bool = False
    audit_available: bool = True
    policy_outage: bool = False
    error_budget_remaining: float = 1.0
    autonomy_level: AutonomyLevel | None = None


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(ExerciseKind.SUCCESSFUL_REMEDIATION, "bounded action verifies and completes"),
    Scenario(ExerciseKind.VERIFICATION_FAILURE, "verification fails and promotion is refused", heals=False),
    Scenario(ExerciseKind.ROLLBACK, "verification fails and the runbook rolls back", heals=False),
    Scenario(ExerciseKind.KILL_SWITCH, "the service kill switch denies the action", kill_switch=True),
    Scenario(ExerciseKind.POLICY_OUTAGE, "an unavailable policy service denies the action", policy_outage=True),
    Scenario(ExerciseKind.AUDIT_OUTAGE, "an unavailable audit sink denies the action", audit_available=False),
    Scenario(
        ExerciseKind.ERROR_BUDGET_EXHAUSTED,
        "an exhausted error budget denies autonomous mutation",
        error_budget_remaining=0.0,
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
    ),
)


def _passed(scenario: Scenario, result: ExecutionResult) -> tuple[bool, str]:
    detail = f"status={result.status}; {result.policy.reason}"
    if scenario.kind is ExerciseKind.SUCCESSFUL_REMEDIATION:
        return (result.status == "succeeded" and result.verified), detail
    if scenario.kind is ExerciseKind.VERIFICATION_FAILURE:
        return (not result.verified and result.status in {"rolled_back", "escalate"}), detail
    if scenario.kind is ExerciseKind.ROLLBACK:
        passed = result.status == "rolled_back" and bool(result.rollback_ref)
        return passed, (
            detail
            if passed
            else f"{detail}; no rollback reference was produced for this runbook"
        )
    return result.status == "denied", detail


def _evaluator(scenario: Scenario, opa_endpoint: str | None):
    if scenario.policy_outage:
        return UnavailablePolicyEvaluator()
    if opa_endpoint:
        return OpaPolicyClient(opa_endpoint)
    return LocalReferenceEvaluator()


def _policy(
    scenario: Scenario, *, service: str, environment: str, runbook: Runbook, blast_radius: int
) -> ServiceAutonomy:
    return ServiceAutonomy(
        service=service,
        environment=environment,
        level=scenario.autonomy_level or runbook.required_level,
        certified_runbooks=(runbook.id,),
        max_blast_radius=max(blast_radius, runbook.max_blast_radius),
        kill_switch=scenario.kill_switch,
    )


def run_exercise(
    scenario: Scenario,
    *,
    catalog: RunbookCatalog,
    service: str,
    environment: str,
    runbook_id: str,
    namespace: str,
    blast_radius: int,
    simulated: bool,
    opa_endpoint: str | None,
    evidence_ref: str,
) -> tuple[ExerciseResult, str]:
    runbook = catalog.get(runbook_id)
    runner = (
        SimulatedClusterRunner(service=service, heals=scenario.heals)
        if simulated
        else SubprocessInputRunner()
    )
    twin = KubernetesDigitalTwin(runner)
    request = ActionRequest(
        service=service,
        environment=environment,
        runbook_id=runbook_id,
        blast_radius=blast_radius,
        error_budget_remaining=scenario.error_budget_remaining,
    )
    policy = _policy(
        scenario,
        service=service,
        environment=environment,
        runbook=runbook,
        blast_radius=blast_radius,
    )
    # Same order as KubernetesDigitalTwin.simulate: mutable runtime preconditions
    # are checked against the real source namespace before anything is cloned,
    # and only then are they trusted inside the sandbox. Checking them against a
    # fresh clone instead would test the clone, not the workload.
    allowed, reason = KubernetesActionAdapter(runner, namespace=namespace).preflight(runbook, request)
    if not allowed:
        result = ExecutionResult(status="denied", policy=PolicyDecision(False, reason), error=reason)
    else:
        env = twin.provision(
            simulation_id=f"{scope_hash(service, environment, runbook_id)}-{scenario.kind.value}",
            service=service,
            source_namespace=namespace,
        )
        try:
            adapter = KubernetesActionAdapter(
                runner,
                namespace=env.namespace,
                trusted_preconditions=runbook.preconditions,
            )
            result = execute_control_loop(
                catalog=catalog,
                policy=policy,
                request=request,
                adapter=adapter,
                evaluator=_evaluator(scenario, opa_endpoint),
                # The approval is issued out of band for an exercise; the
                # exercises that must be denied are denied by policy, not by a
                # missing token.
                approval_verified=True,
                control=PolicyControlState(audit_available=scenario.audit_available),
            )
        finally:
            twin.destroy(env.namespace)

    passed, detail = _passed(scenario, result)
    return (
        ExerciseResult(
            kind=scenario.kind,
            passed=passed,
            service=service,
            environment=environment,
            runbook_id=runbook_id,
            observed_blast_radius=blast_radius,
            evidence_ref=evidence_ref,
            evidence_grade=REHEARSAL_GRADE if simulated else PRODUCTION_GRADE,
        ),
        detail,
    )


def _preflight(runner: str, opa_endpoint: str | None) -> None:
    if runner != "kubectl":
        return
    missing = []
    if not str(os.environ.get("KUBECONFIG", "")).strip():
        missing.append("KUBECONFIG")
    if shutil.which("kubectl") is None:
        missing.append("kubectl on PATH")
    if not opa_endpoint:
        missing.append("--opa-endpoint")
    if missing:
        raise RuntimeError(
            "--runner kubectl requires real cluster and policy access; missing: " + ", ".join(missing)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the L3 certification exercise suite for one scope")
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--runbook", required=True)
    parser.add_argument("--namespace", default=None, help="source namespace (defaults to --service)")
    parser.add_argument("--blast-radius", type=int, default=1)
    parser.add_argument("--runner", choices=("simulated", "kubectl"), default="simulated")
    parser.add_argument("--opa-endpoint", default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    catalog = default_catalog()
    try:
        runbook = catalog.get(args.runbook)
        KubernetesActionAdapter._safe_name(args.service)
        KubernetesActionAdapter._safe_name(args.namespace or args.service)
    except (KeyError, ValueError) as exc:
        print(f"invalid scope: {exc}")
        return 2
    if args.environment not in runbook.environments:
        print(f"invalid scope: runbook {runbook.id} is not permitted in {args.environment}")
        return 2

    _preflight(args.runner, args.opa_endpoint)

    simulated = args.runner == "simulated"
    digest = scope_hash(args.service, args.environment, args.runbook)
    scheme = "rehearsal" if simulated else "kubectl"
    results: list[dict] = []
    exercises: list[ExerciseResult] = []
    for scenario in SCENARIOS:
        result, detail = run_exercise(
            scenario,
            catalog=catalog,
            service=args.service,
            environment=args.environment,
            runbook_id=args.runbook,
            namespace=args.namespace or args.service,
            blast_radius=args.blast_radius,
            simulated=simulated,
            opa_endpoint=args.opa_endpoint,
            evidence_ref=f"{scheme}://l3-exercises-{digest}/{scenario.kind.value}",
        )
        exercises.append(result)
        results.append({
            **asdict(result),
            "kind": result.kind.value,
            "description": scenario.description,
            "detail": detail,
        })

    report = {
        "scope": {
            "service": args.service,
            "environment": args.environment,
            "runbook_id": args.runbook,
            "scope_hash": digest,
            "blast_radius": args.blast_radius,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner": args.runner,
        "policy_evaluator": "opa" if args.opa_endpoint else "local-reference",
        "evidence_grade": REHEARSAL_GRADE if simulated else PRODUCTION_GRADE,
        "production_evidence": not simulated,
        "disclaimer": DISCLAIMER if simulated else CLUSTER_NOTE,
        "exercises": results,
        # A simulated suite never produces a certification assessment: grading a
        # rehearsal would invite it being read as certification.
        "certification_assessment": None
        if simulated
        else _certification_assessment(args, exercises),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"l3-exercises-{digest}.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    passed = sum(1 for item in results if item["passed"])
    print(
        f"L3 exercises: scope={args.service}/{args.environment}/{args.runbook} "
        f"runner={args.runner} grade={report['evidence_grade']} "
        f"passed={passed}/{len(results)} output={output}"
    )
    print(report["disclaimer"])
    return 0


def _certification_assessment(args, exercises: list[ExerciseResult]) -> dict:
    report = build_certification_report(
        service=args.service,
        environment=args.environment,
        runbook_id=args.runbook,
        certified_max_blast_radius=args.blast_radius,
        # Neither of these is something a runner can observe; a cluster suite
        # reports them as unmet so the assessment cannot overstate itself.
        security_reviewed=False,
        verification_independent=False,
        exercises=tuple(exercises),
    )
    return {**asdict(report), "note": CLUSTER_NOTE}


if __name__ == "__main__":
    raise SystemExit(main())
