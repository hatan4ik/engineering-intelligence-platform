from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.change_context import HistoricalFailure, build_change_context
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment, assess_change
from telemetry.events import NullTelemetrySink, OperationEvent, TelemetrySink

from .github_checks import CheckPublisher, CheckRun, build_check_run
from .github_events import DiffProvider, PullRequestEvent

TEST_PATH_TOKENS = ("tests/", "test/", "spec/")


def tests_present(paths: list[str]) -> bool:
    for path in paths:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        if any(token in f"{lowered}/" or lowered.startswith(token) for token in TEST_PATH_TOKENS):
            return True
        if name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts")):
            return True
    return False


GraphProvider = Callable[[str], ServiceGraph]
HistoryProvider = Callable[[str, tuple[str, ...]], list[HistoricalFailure]]


@dataclass(frozen=True)
class PRGuardianResult:
    workflow_id: str
    correlation_id: str
    assessment: RiskAssessment
    policy: PRPolicyDecision
    check: CheckRun


@dataclass
class PRGuardianService:
    """End-to-end PR Guardian: PR event -> diff -> service graph -> deterministic
    risk -> durable workflow + audit -> published check.

    The LLM plays no role in the decision; every input to the score is recorded
    in the audit payload via the workflow plan hash.
    """

    diff_provider: DiffProvider
    graph_provider: GraphProvider
    workflows: ControlPlaneWorkflows
    check_publisher: CheckPublisher
    history_provider: HistoryProvider | None = None
    telemetry: TelemetrySink = field(default_factory=NullTelemetrySink)

    def handle(self, event: PullRequestEvent) -> PRGuardianResult:
        started = time.monotonic()
        changed = self.diff_provider.changed_files(event.repository, event.pr_number)
        paths = [f.path for f in changed]
        graph = self.graph_provider(event.repository)
        known_services = set(graph.nodes)

        preliminary_services = tuple(sorted(
            s for s in known_services
            if any(self._path_touches(p, s) for p in paths)
        ))
        history = (
            self.history_provider(event.repository, preliminary_services)
            if self.history_provider
            else []
        )
        context = build_change_context(
            paths=paths,
            known_services=known_services,
            tests_present=tests_present(paths),
            historical_failures=history,
        )
        assessment = assess_change(graph, context)

        service_id = context.changed_services[0] if context.changed_services else event.repository
        workflow, policy = self.workflows.start_pr_review(
            service_id=service_id,
            repository=event.repository,
            pr_number=event.pr_number,
            assessment=assessment,
        )
        check = build_check_run(event, assessment, policy)
        self.check_publisher.publish(check)

        self.telemetry.emit(OperationEvent(
            correlation_id=workflow.correlation_id,
            operation="pr-guardian-review",
            component="sdlc.pr_guardian",
            outcome=check.conclusion,
            latency_ms=(time.monotonic() - started) * 1000.0,
            repo=event.repository,
            service=service_id,
            agent="pr-guardian",
            attributes={
                "pr": str(event.pr_number),
                "head_sha": event.head_sha,
                "score": str(assessment.score),
                "band": assessment.band,
                "delivery_id": event.delivery_id or "",
            },
        ))
        return PRGuardianResult(
            workflow_id=workflow.workflow_id,
            correlation_id=workflow.correlation_id,
            assessment=assessment,
            policy=policy,
            check=check,
        )

    @staticmethod
    def _path_touches(path: str, service: str) -> bool:
        return service in path.split("/") or path.rsplit("/", 1)[-1].startswith(service)

