from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import build_graph, metadata_from_manifest
from intelligence.graph import ServiceGraph
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore

from .github_checks import COMMENT_MARKER
from .github_events import ChangedFile, PullRequestEvent
from .pr_guardian_service import PRGuardianService


def _changed_paths(base_ref: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _repo_graph(root: Path) -> ServiceGraph:
    metadata = []
    for path in list(root.rglob("*.yaml")) + list(root.rglob("*.yml")):
        if ".git" in path.parts:
            continue
        try:
            item = metadata_from_manifest(str(path), path.read_text(errors="ignore"))
        except OSError:
            continue
        if item is not None and "{" not in item.service:
            metadata.append(item)
    return build_graph(metadata)


class _LocalDiff:
    def __init__(self, paths: list[str]) -> None:
        self.paths = paths

    def changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        return [ChangedFile(path=p) for p in self.paths]


class _SummaryPublisher:
    def __init__(self) -> None:
        self.summary: str | None = None

    def publish(self, check) -> None:
        self.summary = check.summary


def _upsert_comment(repository: str, pr_number: int, body: str, token: str) -> None:
    api = os.getenv("GITHUB_API_URL", "https://api.github.com")

    def call(url: str, method: str = "GET", payload: dict | None = None) -> object:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}

    base = f"{api}/repos/{repository}/issues/{pr_number}/comments"
    existing = call(f"{base}?per_page=100")
    marker = next(
        (c for c in existing if COMMENT_MARKER in str(c.get("body", ""))),
        None,
    ) if isinstance(existing, list) else None
    if marker is not None:
        call(f"{api}/repos/{repository}/issues/comments/{marker['id']}", "PATCH", {"body": body})
    else:
        call(base, "POST", {"body": body})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PR Guardian against the local checkout")
    parser.add_argument("--base-ref", required=True, help="merge base, e.g. origin/main")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "local/checkout"))
    parser.add_argument("--pr-number", type=int, default=int(os.getenv("PR_NUMBER", "0")))
    parser.add_argument("--head-sha", default=os.getenv("GITHUB_SHA", "HEAD"))
    args = parser.parse_args()

    paths = _changed_paths(args.base_ref)
    if not paths:
        print("No changed files; nothing to review.")
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="eip-guardian-"))
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(workdir / "state.db"),
        SqliteAuditLog(workdir / "audit.db"),
    )
    publisher = _SummaryPublisher()
    service = PRGuardianService(
        diff_provider=_LocalDiff(paths),
        graph_provider=lambda repo: _repo_graph(Path.cwd()),
        workflows=workflows,
        check_publisher=publisher,
    )
    event = PullRequestEvent(
        repository=args.repository,
        pr_number=args.pr_number,
        action="synchronize",
        head_sha=args.head_sha,
        base_ref=args.base_ref,
        head_ref="HEAD",
        title="local review",
        author="ci",
    )
    result = service.handle(event)
    chain_ok = workflows.audit.verify_chain()

    body = (
        f"{publisher.summary}\n\n"
        f"_Workflow `{result.workflow_id}` · correlation `{result.correlation_id}` · "
        f"audit chain verified: {chain_ok}_"
    )
    print(body)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(body + "\n")

    token = os.getenv("GITHUB_TOKEN", "")
    if token and args.pr_number:
        try:
            _upsert_comment(args.repository, args.pr_number, body, token)
        except Exception as exc:  # comment is best-effort; the check result is the gate
            print(f"warning: could not publish PR comment: {exc}", file=sys.stderr)

    if not chain_ok:
        print("error: audit chain failed verification", file=sys.stderr)
        return 2
    return 1 if result.policy.block_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
