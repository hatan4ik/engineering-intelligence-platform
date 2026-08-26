from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from integrations.github.pr_guardian import GitHubRestPRClient
from product.pr_guardian_shadow import (
    COMMENT_MARKER,
    OUTCOME_COMMENT_MARKER,
    closure_outcome,
    observation_from_comment,
    outcome_comment,
)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not event_path or not repository:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_EVENT_PATH, and GITHUB_REPOSITORY are required")
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("GitHub pull_request event must be a JSON object")
    pr_number = int(payload.get("number", 0))
    if pr_number <= 0:
        raise RuntimeError("GitHub pull_request event has no PR number")
    client = GitHubRestPRClient(token)
    existing = client.latest_comment_with_marker(
        repository=repository,
        pr_number=pr_number,
        marker=COMMENT_MARKER,
    )
    observation = observation_from_comment(existing) if existing else None
    outcome = closure_outcome(payload=payload, observation=observation)
    outcome_path = Path(os.environ.get("EIP_PR_GUARDIAN_OUTCOME_PATH", "pr-guardian-shadow-outcome.json"))
    outcome_path.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    client.publish_sticky_comment(
        repository=repository,
        pr_number=pr_number,
        marker=OUTCOME_COMMENT_MARKER,
        body=outcome_comment(outcome),
    )
    print(
        f"PR Guardian shadow outcome captured for {repository}#{pr_number} "
        f"risk_signal={outcome['reviewer_signal']['risk']} result={outcome_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
