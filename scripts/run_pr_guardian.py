from __future__ import annotations

import json
import os
from pathlib import Path

from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import GitHubRestPRClient, normalize_pull_request_event
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

    graph = build_service_graph_from_checkout(".")
    state_dir = Path(os.environ.get("EIP_STATE_DIR", ".eip"))
    state_dir.mkdir(parents=True, exist_ok=True)
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(state_dir / "state.db"),
        SqliteAuditLog(state_dir / "audit.db"),
    )
    service = PRGuardianService(
        graph=graph,
        github=GitHubRestPRClient(token),
        workflows=workflows,
    )
    result = service.evaluate(event)
    print(
        f"PR Guardian: {event.repository}#{event.number} "
        f"risk={result.assessment.score} conclusion={result.conclusion} "
        f"workflow={result.workflow_id}"
    )
    return 1 if result.policy.block_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
