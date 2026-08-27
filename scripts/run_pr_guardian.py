from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import GitHubRestPRClient, normalize_pull_request_event
from product.pr_guardian_shadow import observation_from_assessment
from product.graph_from_checkout import build_service_graph_from_checkout
from product.pr_guardian_service import PRGuardianService
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    token = os.environ.get("GITHUB_TOKEN")
    if not event_path or not token:
        raise RuntimeError("GITHUB_EVENT_PATH and GITHUB_TOKEN are required")

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    event = normalize_pull_request_event(payload)
    if event.action not in {"opened", "reopened", "synchronize", "ready_for_review"}:
        print(f"PR Guardian: ignoring pull_request action {event.action}")
        return 0

    mode = os.environ.get("EIP_PR_GUARDIAN_MODE", "shadow")
    if mode != "shadow":
        raise RuntimeError("PR Guardian CI supports only EIP_PR_GUARDIAN_MODE=shadow")
    graph = build_service_graph_from_checkout(".")
    state_dir = Path(os.environ.get("EIP_STATE_DIR", ".eip"))
    state_dir.mkdir(parents=True, exist_ok=True)
    audit = SqliteAuditLog(state_dir / "audit.db")
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        audit,
    )
    service = PRGuardianService(
        graph=graph,
        github=GitHubRestPRClient(token),
        workflows=workflows,
    )
    # ``ControlPlaneWorkflows`` is asynchronous, so the product service is a
    # coroutine even in the local/reference runner.  This entry point is a
    # synchronous CLI boundary; run it to completion before serializing the
    # transferable observation.
    result = asyncio.run(service.evaluate(event, publish=False))
    observation = observation_from_assessment(
        event=event,
        assessment=result.assessment,
        workflow_id=result.workflow_id,
        changed_services=result.changed_services,
        would_require_extended_tests=result.policy.require_extended_tests,
        would_require_additional_approval=result.policy.require_additional_approval,
        would_block=result.would_block,
        audit_chain_verified=audit.verify_chain(),
    )
    result_path = Path(os.environ.get("EIP_PR_GUARDIAN_RESULT_PATH", "pr-guardian-shadow-result.json"))
    result_path.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"PR Guardian: {event.repository}#{event.number} "
        f"risk={result.assessment.score} mode=shadow would_block={result.would_block} "
        f"workflow={result.workflow_id} result={result_path}"
    )
    # A simulated policy result must never change the workflow exit status.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
