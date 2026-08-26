from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from integrations.github.pr_guardian import GitHubRestPRClient
from product.pr_guardian_shadow import COMMENT_MARKER, observation_comment, validate_observation


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repository = os.environ.get("GITHUB_REPOSITORY")
    result_path = Path(os.environ.get("EIP_PR_GUARDIAN_RESULT_PATH", "shadow-input/pr-guardian-shadow-result.json"))
    if not token or not event_path or not repository:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_EVENT_PATH, and GITHUB_REPOSITORY are required")
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise RuntimeError("shadow result must be a JSON object")
    observation = validate_observation(raw)
    workflow_run = _workflow_run(Path(event_path))
    subject = observation["subject"]
    assert isinstance(subject, Mapping)
    if subject["repository"] != repository:
        raise RuntimeError("shadow result repository does not match publisher repository")
    if subject["head_sha"] != str(workflow_run.get("head_sha", "")).lower():
        raise RuntimeError("shadow result head SHA does not match the triggering workflow run")
    if str(workflow_run.get("event", "")) != "pull_request":
        raise RuntimeError("shadow publisher accepts only pull_request evaluation workflows")

    assessment = observation["assessment"]
    assert isinstance(assessment, Mapping)
    client = GitHubRestPRClient(token)
    body = observation_comment(observation)
    client.publish_check(
        repository=repository,
        head_sha=str(subject["head_sha"]),
        name="Engineering Intelligence / PR Guardian (shadow)",
        conclusion="neutral",
        title=f"Shadow risk: {assessment['score']}/100 ({assessment['band']})",
        summary=body,
    )
    client.publish_sticky_comment(
        repository=repository,
        pr_number=int(subject["pr_number"]),
        marker=COMMENT_MARKER,
        body=body,
    )
    print(
        f"PR Guardian shadow published for {repository}#{subject['pr_number']} "
        f"score={assessment['score']} would_block={observation['simulated_policy']['would_block']}"
    )
    return 0


def _workflow_run(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("GitHub workflow_run event must be an object")
    workflow_run = payload.get("workflow_run")
    if not isinstance(workflow_run, Mapping):
        raise RuntimeError("GitHub workflow_run event is missing workflow_run")
    return workflow_run


if __name__ == "__main__":
    raise SystemExit(main())
