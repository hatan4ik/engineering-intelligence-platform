"""Publish one PR Guardian observation from a trusted workflow.

This is the only writer.  It runs default-branch code with write scope and
never checks out or executes the pull-request head.  It re-reads the repository
configuration from that trusted default-branch checkout and re-derives the
conclusion itself, so an observation produced by the untrusted evaluation job
can only ever *lower* what gets published.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from integrations.github.pr_guardian import GitHubRestPRClient
from product.architecture_review import render_architecture_review, violations_from_records
from product.pr_guardian.config import load_repository_config
from product.pr_guardian.contracts import RepositoryConfig
from product.pr_guardian.enforcement import explain, publishable_conclusion
from product.pr_guardian_shadow import COMMENT_MARKER, observation_comment, validate_observation


def publish_observation(
    observation: Mapping[str, object],
    *,
    config: RepositoryConfig,
    repository: str,
    client,
    environ: Mapping[str, str] | None = None,
    now: date | datetime | None = None,
) -> str:
    """Publish the check and sticky comment; return the conclusion used."""
    observation = validate_observation(observation)
    subject = observation["subject"]
    assert isinstance(subject, Mapping)
    if subject["repository"] != repository:
        raise RuntimeError("observation repository does not match the publisher repository")
    if config.repository != repository:
        raise RuntimeError("repository configuration does not match the publisher repository")

    decision = publishable_conclusion(observation, config, environ=environ, now=now)
    assessment = observation["assessment"]
    architecture = observation["architecture"]
    assert isinstance(assessment, Mapping) and isinstance(architecture, Mapping)
    violations = violations_from_records(architecture["violations"])  # type: ignore[arg-type]

    # One rendering path: observation_comment states the mode's real authority
    # and discloses the conclusion this trusted workflow actually published.
    body = "\n\n".join((
        observation_comment(
            observation,
            published_conclusion=decision.conclusion,
            publish_reason=decision.reason,
        ),
        render_architecture_review(violations),
    ))
    # The check identity follows the *trusted* configuration, not the mode the
    # untrusted evaluation job claimed: a repository that has since changed
    # mode should not have an old artifact publish under the old check name.
    client.publish_check(
        repository=repository,
        head_sha=str(subject["head_sha"]),
        name=f"Engineering Intelligence / PR Guardian ({config.mode})",
        conclusion=decision.conclusion,
        title=_title(str(config.mode), assessment, decision.conclusion, decision.reason),
        summary=body,
    )
    client.publish_sticky_comment(
        repository=repository,
        pr_number=int(subject["pr_number"]),
        marker=COMMENT_MARKER,
        body=body,
    )
    return decision.conclusion


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repository = os.environ.get("GITHUB_REPOSITORY")
    result_path = Path(os.environ.get("EIP_PR_GUARDIAN_RESULT_PATH", "shadow-input/pr-guardian-shadow-result.json"))
    if not token or not event_path or not repository:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_EVENT_PATH, and GITHUB_REPOSITORY are required")
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise RuntimeError("PR Guardian result must be a JSON object")
    observation = validate_observation(raw)
    workflow_run = _workflow_run(Path(event_path))
    subject = observation["subject"]
    assert isinstance(subject, Mapping)
    if subject["head_sha"] != str(workflow_run.get("head_sha", "")).lower():
        raise RuntimeError("PR Guardian result head SHA does not match the triggering workflow run")
    if str(workflow_run.get("event", "")) != "pull_request":
        raise RuntimeError("PR Guardian publisher accepts only pull_request evaluation workflows")

    # The trusted default-branch checkout, not the pull request, decides the
    # repository's mode.  A malformed configuration fails this workflow, which
    # is safe: the pull-request evaluation job has already exited 0.
    config = load_repository_config(
        Path(os.environ.get("EIP_PR_GUARDIAN_CONFIG_ROOT", ".")), repository=repository
    )
    conclusion = publish_observation(
        observation,
        config=config,
        repository=repository,
        client=GitHubRestPRClient(token),
    )
    enforcement = observation["enforcement"]
    assert isinstance(enforcement, Mapping)
    print(
        f"PR Guardian published for {repository}#{subject['pr_number']} "
        f"observed_mode={observation['mode']} config_mode={config.mode} "
        f"conclusion={conclusion} would_block={enforcement['would_block']}"
    )
    return 0


def _title(mode: str, assessment: Mapping[str, object], conclusion: str, reason: str) -> str:
    risk = f"{assessment['score']}/100 ({assessment['band']})"
    if conclusion == "failure":
        return f"Blocked: risk {risk}"
    if mode == "advisory":
        return f"Advisory risk: {risk} — this check does not block merges"
    if mode == "enforce":
        return f"Enforcing risk: {risk} — not blocked ({explain(reason)})"
    return f"Shadow risk: {risk}"


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
