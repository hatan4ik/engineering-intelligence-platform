"""Evaluate one pull request and write a transferable observation.

This job runs with a read-only token on the pull request's *base* commit.  It
publishes nothing and it is never the gate: it always exits 0, so a platform
defect cannot stop a merge.  The trusted publisher workflow is the only writer.

The repository's mode comes from `.eip/pr-guardian.json` in that base checkout,
so a pull request cannot raise its own repository's enforcement level.  It can
still suppress a block on itself by editing this workflow's definition, which
`pull_request` runs from the head — require Code Owner review on
`.github/workflows/` and `.eip/`; see docs/PR-GUARDIAN-REPOSITORY-CONFIG.md.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import GitHubRestPRClient, normalize_pull_request_event
from intelligence.architecture_guard import ArchitectureRule
from product.architecture_review import (
    DEFAULT_ARCHITECTURE_RULES,
    FileContent,
    review_changed_paths,
    skipped_records,
    violation_records,
)
from product.graph_from_checkout import build_service_graph_from_checkout
from product.pr_guardian.config import CONFIG_RELATIVE_PATH, load_effective_config
from product.pr_guardian_service import PRGuardianService
from product.pr_guardian_shadow import observation_from_assessment
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


# A pull request that rewrites a huge generated file should not turn into a
# hundred content requests; Architecture Guard is advisory, so a partial review
# is acceptable and is reported as such.
MAX_REVIEWED_FILES = 200
MAX_CONTENT_BYTES = 512_000


@dataclass
class GitHubFileContents:
    """Read the pull-request revision of a changed file, never executing it."""

    token: str
    repository: str
    ref: str
    api_url: str = "https://api.github.com"

    def read_changed_file(self, path: str) -> FileContent:
        request = urllib.request.Request(
            f"{self.api_url.rstrip('/')}/repos/{self.repository}/contents/"
            f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(self.ref)}",
            method="GET",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # A deleted file, a submodule, or a transient API error must not
            # fail an advisory review — but it is reported, not treated as
            # a clean file.
            return FileContent.unavailable(f"contents API returned {exc.code}")
        except (urllib.error.URLError, json.JSONDecodeError):
            return FileContent.unavailable("contents API was unreachable or unreadable")
        if not isinstance(payload, dict) or payload.get("encoding") != "base64":
            return FileContent.unavailable("not an inline base64 file (submodule or too large)")
        if int(payload.get("size", 0)) > MAX_CONTENT_BYTES:
            return FileContent.unavailable(f"larger than {MAX_CONTENT_BYTES} bytes")
        try:
            return FileContent.available(
                base64.b64decode(str(payload.get("content", ""))).decode("utf-8")
            )
        except (ValueError, UnicodeDecodeError):
            return FileContent.unavailable("not decodable as UTF-8 text")


async def evaluate_pull_request(
    event,
    *,
    service: PRGuardianService,
    audit: SqliteAuditLog,
    contents,
    rules: tuple[ArchitectureRule, ...] = DEFAULT_ARCHITECTURE_RULES,
    now: date | datetime | None = None,
) -> dict[str, object]:
    """Assess risk, run Architecture Guard, and return the observation record."""
    result = await service.evaluate(event, publish=False, now=now)
    review = review_changed_paths(
        result.changed_files[:MAX_REVIEWED_FILES], provider=contents, rules=rules
    )
    return observation_from_assessment(
        event=event,
        assessment=result.assessment,
        workflow_id=result.workflow_id,
        changed_services=result.changed_services,
        would_require_extended_tests=result.policy.require_extended_tests,
        would_require_additional_approval=result.policy.require_additional_approval,
        would_block=result.would_block,
        audit_chain_verified=audit.verify_chain(),
        mode=result.mode,
        enforcement=result.enforcement.as_dict(),
        architecture={
            "violations": violation_records(review.violations),
            # Coverage travels with the findings: a file whose content could
            # not be fetched is reported as skipped, never as clean.
            "in_scope": review.in_scope,
            "reviewed": review.reviewed,
            "skipped": skipped_records(review.skipped),
            # Architecture Guard is advisory in this stage: its findings are
            # recorded and rendered, and never change a check conclusion.
            "summary": review.summary,
        },
    )


def main() -> int:
    """Evaluate the pull request and always return 0.

    The read-only evaluate job is never the merge gate: the trusted publisher
    decides what is published from the artifact this job writes. An unexpected
    failure here is therefore reported loudly and still exits 0 -- an uncaught
    exception would turn a broken evaluate step into a de-facto required check,
    which the workflow header promises it is not.
    """

    try:
        return _evaluate_and_write()
    except Exception as exc:  # noqa: BLE001 - see docstring: never a gate
        print(
            f"PR Guardian: evaluation failed and produced no observation "
            f"({type(exc).__name__}: {exc}); the evaluate job is not a gate, exiting 0",
            file=sys.stderr,
        )
        return 0


def _evaluate_and_write() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    token = os.environ.get("GITHUB_TOKEN")
    if not event_path or not token:
        raise RuntimeError("GITHUB_EVENT_PATH and GITHUB_TOKEN are required")

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    event = normalize_pull_request_event(payload)
    if event.action not in {"opened", "reopened", "synchronize", "ready_for_review"}:
        print(f"PR Guardian: ignoring pull_request action {event.action}")
        return 0

    checkout = Path(os.environ.get("EIP_PR_GUARDIAN_CONFIG_ROOT", "."))
    # The evaluation job is never the gate, so an unreadable configuration
    # degrades to shadow here and is reported loudly rather than raising.
    config, config_error = load_effective_config(checkout, repository=event.repository)
    if config_error is not None:
        print(
            f"PR Guardian: {CONFIG_RELATIVE_PATH} is invalid ({config_error}); "
            "evaluating in shadow mode",
            file=sys.stderr,
        )

    graph = build_service_graph_from_checkout(checkout)
    state_dir = Path(os.environ.get("EIP_STATE_DIR", ".eip"))
    state_dir.mkdir(parents=True, exist_ok=True)
    audit = SqliteAuditLog(state_dir / "audit.db")
    workflows = ControlPlaneWorkflows(SqliteStateStore(state_dir / "state.db"), audit)
    service = PRGuardianService(
        graph=graph,
        github=GitHubRestPRClient(token),
        workflows=workflows,
        config=config,
    )
    # ``ControlPlaneWorkflows`` is asynchronous, so the product service is a
    # coroutine even in the local/reference runner.  This entry point is a
    # synchronous CLI boundary; run the evaluation (risk + Architecture Guard)
    # to completion before serializing the transferable observation.
    observation = asyncio.run(
        evaluate_pull_request(
            event,
            service=service,
            audit=audit,
            contents=GitHubFileContents(
                token=token, repository=event.repository, ref=event.head_sha
            ),
        )
    )
    result_path = Path(os.environ.get("EIP_PR_GUARDIAN_RESULT_PATH", "pr-guardian-shadow-result.json"))
    result_path.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    enforcement = observation["enforcement"]
    architecture = observation["architecture"]
    assert isinstance(enforcement, dict) and isinstance(architecture, dict)
    print(
        f"PR Guardian: {event.repository}#{event.number} "
        f"risk={observation['assessment']['score']} mode={observation['mode']} "
        f"would_block={enforcement['would_block']} ({enforcement['reason']}) "
        f"architecture={len(architecture['violations'])} finding(s) "
        f"({architecture['reviewed']}/{architecture['in_scope']} file(s) reviewed) "
        f"workflow={observation['workflow']['id']} result={result_path}"
    )
    # A simulated policy result must never change the workflow exit status.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
