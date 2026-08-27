"""Publish one PR Guardian observation from a trusted workflow.

This is the only writer.  It runs default-branch code with write scope and
never checks out or executes the pull-request head.  It re-reads the repository
configuration from that trusted default-branch checkout and re-derives the
conclusion itself, so an observation produced by the untrusted evaluation job
cannot escalate what gets published beyond what that configuration allows.

Three failure modes must never take the publisher down, because a repository in
enforce mode is exactly the one likely to have marked this check required:

* an unreadable or lapsed repository configuration publishes ``neutral`` and
  says why;
* a missing, unparseable, or invalid evaluation artifact publishes ``neutral``
  and says the evaluation could not be trusted;
* neither is ever silent.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from integrations.github.pr_guardian import GitHubRestPRClient
from product.architecture_review import (
    coverage_from_records,
    render_architecture_review,
    violations_from_records,
)
from product.pr_guardian.config import load_effective_config
from product.pr_guardian.contracts import RepositoryConfig
from product.pr_guardian.enforcement import explain, publishable_conclusion
from product.pr_guardian_shadow import COMMENT_MARKER, observation_comment, validate_observation


CHECK_PREFIX = "Engineering Intelligence / PR Guardian"


class UntrustedEvaluation(RuntimeError):
    """The evaluation artifact could not be trusted; publish neutral, say so."""


def trusted_observation(
    result_path: Path,
    *,
    repository: str,
    head_sha: str,
) -> dict[str, object]:
    """Load the artifact, or refuse it with a reason a human can act on.

    Every refusal is an ``UntrustedEvaluation`` rather than a crash, so the
    caller can still publish an honest neutral result for the pull request.
    """
    try:
        raw_text = result_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise UntrustedEvaluation(
            f"no evaluation artifact was found at {result_path}"
        ) from exc
    except OSError as exc:
        raise UntrustedEvaluation(f"the evaluation artifact could not be read: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise UntrustedEvaluation(f"the evaluation artifact could not be parsed: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise UntrustedEvaluation("the evaluation artifact is not a JSON object")
    try:
        observation = validate_observation(raw)
    except ValueError as exc:
        raise UntrustedEvaluation(f"the evaluation artifact did not validate: {exc}") from exc
    subject = observation["subject"]
    assert isinstance(subject, Mapping)
    if subject["repository"] != repository:
        raise UntrustedEvaluation(
            "the evaluation artifact names a different repository "
            f"({subject['repository']}) than this workflow ({repository})"
        )
    if str(subject["head_sha"]).lower() != head_sha.lower():
        raise UntrustedEvaluation(
            "the evaluation artifact's head SHA does not match the triggering workflow run"
        )
    return observation


def publish_untrusted_evaluation(
    *,
    repository: str,
    head_sha: str,
    pr_number: int | None,
    client,
    mode: str,
    reason: str,
) -> str:
    """Publish a neutral check stating that the evaluation could not be used."""
    body = (
        f"{COMMENT_MARKER}\n"
        f"## {CHECK_PREFIX} — evaluation not published\n\n"
        "**This pull request was not assessed.** The evaluation result could not be "
        f"trusted: {reason}\n\n"
        "The check is published as `neutral` so a platform failure never blocks a merge. "
        "Re-run the *PR Guardian Shadow (non-blocking)* workflow to produce a fresh "
        "evaluation."
    )
    client.publish_check(
        repository=repository,
        head_sha=head_sha,
        name=f"{CHECK_PREFIX} ({mode})",
        conclusion="neutral",
        title="PR Guardian could not verify this evaluation",
        summary=body,
    )
    if pr_number is not None:
        client.publish_sticky_comment(
            repository=repository,
            pr_number=pr_number,
            marker=COMMENT_MARKER,
            body=body,
        )
    return "neutral"


def publish_observation(
    observation: Mapping[str, object],
    *,
    config: RepositoryConfig,
    repository: str,
    client,
    environ: Mapping[str, str] | None = None,
    now: date | datetime | None = None,
    config_error: str | None = None,
) -> str:
    """Publish the check and sticky comment; return the conclusion used."""
    observation = validate_observation(observation)
    subject = observation["subject"]
    assert isinstance(subject, Mapping)
    if subject["repository"] != repository:
        raise RuntimeError("observation repository does not match the publisher repository")
    if config.repository != repository:
        raise RuntimeError("repository configuration does not match the publisher repository")

    if config_error is None:
        decision = publishable_conclusion(observation, config, environ=environ, now=now)
        conclusion, reason = decision.conclusion, explain(decision.reason)
    else:
        # A configuration this workflow could not read cannot authorize a
        # failing check, and must not take the run down either.
        conclusion = "neutral"
        reason = f"the repository configuration could not be read: {config_error}"

    assessment = observation["assessment"]
    architecture = observation["architecture"]
    assert isinstance(assessment, Mapping) and isinstance(architecture, Mapping)
    violations = violations_from_records(architecture["violations"])  # type: ignore[arg-type]
    coverage = coverage_from_records(
        violations,
        reviewed=int(architecture["reviewed"]),  # type: ignore[arg-type]
        in_scope=int(architecture["in_scope"]),  # type: ignore[arg-type]
        skipped=architecture["skipped"],  # type: ignore[arg-type]
        summary=str(architecture["summary"]),
    )

    # One rendering path: observation_comment states the mode's real authority
    # and discloses the conclusion this trusted workflow actually published.
    body = "\n\n".join((
        observation_comment(
            observation,
            published_conclusion=conclusion,
            publish_reason=reason,
        ),
        render_architecture_review(violations, coverage=coverage),
    ))
    # The check identity follows the *trusted* configuration, not the mode the
    # untrusted evaluation job claimed: a repository that has since changed
    # mode should not have an old artifact publish under the old check name.
    client.publish_check(
        repository=repository,
        head_sha=str(subject["head_sha"]),
        name=f"{CHECK_PREFIX} ({config.mode})",
        conclusion=conclusion,
        title=_title(str(config.mode), assessment, conclusion, reason),
        summary=body,
    )
    client.publish_sticky_comment(
        repository=repository,
        pr_number=int(subject["pr_number"]),
        marker=COMMENT_MARKER,
        body=body,
    )
    return conclusion


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repository = os.environ.get("GITHUB_REPOSITORY")
    result_path = Path(os.environ.get("EIP_PR_GUARDIAN_RESULT_PATH", "shadow-input/pr-guardian-shadow-result.json"))
    if not token or not event_path or not repository:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_EVENT_PATH, and GITHUB_REPOSITORY are required")
    workflow_run = _workflow_run(Path(event_path))
    if str(workflow_run.get("event", "")) != "pull_request":
        raise RuntimeError("PR Guardian publisher accepts only pull_request evaluation workflows")
    head_sha = str(workflow_run.get("head_sha", "")).lower()
    if not head_sha:
        raise RuntimeError("the triggering workflow run did not report a head SHA")

    # The trusted default-branch checkout, not the pull request, decides the
    # repository's mode.  An unreadable file lapses to shadow with a reason
    # instead of taking down the only workflow that can publish anything.
    config, config_error = load_effective_config(
        Path(os.environ.get("EIP_PR_GUARDIAN_CONFIG_ROOT", ".")), repository=repository
    )
    client = GitHubRestPRClient(token)

    try:
        observation = trusted_observation(result_path, repository=repository, head_sha=head_sha)
    except UntrustedEvaluation as exc:
        conclusion = publish_untrusted_evaluation(
            repository=repository,
            head_sha=head_sha,
            pr_number=_pull_request_number(workflow_run),
            client=client,
            mode=str(config.mode),
            reason=str(exc),
        )
        print(f"PR Guardian: refused the evaluation artifact ({exc}); published {conclusion}")
        # The pull request is not blocked, but this workflow goes red so an
        # operator sees that an evaluation went missing or was tampered with.
        return 1

    conclusion = publish_observation(
        observation,
        config=config,
        repository=repository,
        client=client,
        config_error=config_error,
    )
    subject = observation["subject"]
    enforcement = observation["enforcement"]
    assert isinstance(subject, Mapping) and isinstance(enforcement, Mapping)
    print(
        f"PR Guardian published for {repository}#{subject['pr_number']} "
        f"observed_mode={observation['mode']} config_mode={config.mode} "
        f"conclusion={conclusion} would_block={enforcement['would_block']}"
        + (f" config_error={config_error}" if config_error else "")
    )
    return 0


def _title(mode: str, assessment: Mapping[str, object], conclusion: str, reason: str) -> str:
    risk = f"{assessment['score']}/100 ({assessment['band']})"
    if conclusion == "failure":
        return f"Blocked: risk {risk}"
    if mode == "advisory":
        return f"Advisory risk: {risk} — this check does not block merges"
    if mode == "enforce":
        return f"Enforcing risk: {risk} — not blocked ({reason})"
    return f"Shadow risk: {risk}"


def _pull_request_number(workflow_run: Mapping[str, object]) -> int | None:
    pull_requests = workflow_run.get("pull_requests")
    if not isinstance(pull_requests, list):
        return None
    for entry in pull_requests:
        if isinstance(entry, Mapping) and isinstance(entry.get("number"), int):
            return int(entry["number"])
    return None


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
