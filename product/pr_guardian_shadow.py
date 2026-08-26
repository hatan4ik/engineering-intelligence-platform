"""Portable, non-enforcing records for the PR Guardian shadow pilot.

The records deliberately contain only deterministic assessment metadata.  They
are safe to pass between the untrusted pull-request evaluation workflow and a
separate, trusted publisher workflow; they are *not* production evidence or an
authorization to enable merge enforcement.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import PullRequestEvent


SCHEMA_VERSION = 1
OBSERVATION_KIND = "pr-guardian-shadow-observation"
OUTCOME_KIND = "pr-guardian-shadow-outcome"
COMMENT_MARKER = "<!-- eip-pr-guardian-shadow -->"
DATA_MARKER = "<!-- eip-pr-guardian-shadow-observation:"
DATA_SUFFIX = " -->"
OUTCOME_COMMENT_MARKER = "<!-- eip-pr-guardian-shadow-outcome -->"

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# GitHub supplies full head SHAs in production, while callers/tests may use a
# legitimate abbreviated SHA. The value is a binding identifier, not a secret.
_SHA = re.compile(r"^[0-9a-fA-F]{4,64}$")
_BANDS = frozenset({"low", "moderate", "high", "critical"})
_RISK_LABELS = {
    "eip-pr-guardian/confirmed-risk": "confirmed-risk",
    "eip-pr-guardian/false-positive": "false-positive",
}
_UTILITY_LABELS = {
    "eip-pr-guardian/useful": "useful",
    "eip-pr-guardian/not-useful": "not-useful",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def observation_from_assessment(
    *,
    event: PullRequestEvent,
    assessment: RiskAssessment,
    workflow_id: str,
    changed_services: tuple[str, ...],
    would_require_extended_tests: bool,
    would_require_additional_approval: bool,
    would_block: bool,
    audit_chain_verified: bool,
    observed_at: str | None = None,
) -> dict[str, object]:
    """Return a strictly shaped non-enforcing shadow observation."""
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "mode": "shadow",
        "observed_at": observed_at or utc_now(),
        "subject": {
            "repository": event.repository,
            "pr_number": event.number,
            "head_sha": event.head_sha,
            "action": event.action,
        },
        "assessment": {
            "score": assessment.score,
            "band": assessment.band,
            "factors": [
                {"name": factor.name, "points": factor.points, "evidence": factor.evidence}
                for factor in assessment.factors
            ],
        },
        "changed_services": list(changed_services),
        "simulated_policy": {
            "would_require_extended_tests": would_require_extended_tests,
            "would_require_additional_approval": would_require_additional_approval,
            "would_block": would_block,
        },
        "workflow": {"id": workflow_id, "audit_chain_verified": audit_chain_verified},
    }
    return validate_observation(record)


def validate_observation(value: Mapping[str, object]) -> dict[str, object]:
    """Validate a workflow-transfer record before a trusted workflow uses it."""
    _exact_keys(
        value,
        {
            "schema_version", "kind", "mode", "observed_at", "subject", "assessment",
            "changed_services", "simulated_policy", "workflow",
        },
        "shadow observation",
    )
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != OBSERVATION_KIND:
        raise ValueError("unsupported shadow observation schema")
    if value.get("mode") != "shadow":
        raise ValueError("only shadow PR Guardian observations may be published")
    observed_at = _string(value.get("observed_at"), "observed_at", 80)
    subject = _mapping(value.get("subject"), "subject")
    _exact_keys(subject, {"repository", "pr_number", "head_sha", "action"}, "subject")
    repository = _string(subject.get("repository"), "subject.repository", 200)
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("subject.repository is invalid")
    pr_number = _integer(subject.get("pr_number"), "subject.pr_number", minimum=1, maximum=10**9)
    head_sha = _string(subject.get("head_sha"), "subject.head_sha", 64)
    if not _SHA.fullmatch(head_sha):
        raise ValueError("subject.head_sha is invalid")
    action = _string(subject.get("action"), "subject.action", 64)

    assessment = _mapping(value.get("assessment"), "assessment")
    _exact_keys(assessment, {"score", "band", "factors"}, "assessment")
    score = _integer(assessment.get("score"), "assessment.score", minimum=0, maximum=100)
    band = _string(assessment.get("band"), "assessment.band", 20)
    if band not in _BANDS:
        raise ValueError("assessment.band is invalid")
    raw_factors = assessment.get("factors")
    if not isinstance(raw_factors, list) or len(raw_factors) > 32:
        raise ValueError("assessment.factors is invalid")
    factors: list[dict[str, object]] = []
    for index, raw in enumerate(raw_factors):
        factor = _mapping(raw, f"assessment.factors[{index}]")
        _exact_keys(factor, {"name", "points", "evidence"}, f"assessment.factors[{index}]")
        factors.append({
            "name": _string(factor.get("name"), f"assessment.factors[{index}].name", 120),
            "points": _integer(factor.get("points"), f"assessment.factors[{index}].points", minimum=0, maximum=100),
            "evidence": _string(factor.get("evidence"), f"assessment.factors[{index}].evidence", 500),
        })

    raw_services = value.get("changed_services")
    if not isinstance(raw_services, list) or len(raw_services) > 64:
        raise ValueError("changed_services is invalid")
    services = [_string(item, "changed_services item", 120) for item in raw_services]
    if services != sorted(set(services)):
        raise ValueError("changed_services must be sorted and unique")

    policy = _mapping(value.get("simulated_policy"), "simulated_policy")
    _exact_keys(
        policy,
        {"would_require_extended_tests", "would_require_additional_approval", "would_block"},
        "simulated_policy",
    )
    normalized_policy = {
        key: _boolean(policy.get(key), f"simulated_policy.{key}")
        for key in sorted(policy)
    }
    workflow = _mapping(value.get("workflow"), "workflow")
    _exact_keys(workflow, {"id", "audit_chain_verified"}, "workflow")
    workflow_id = _string(workflow.get("id"), "workflow.id", 240)
    audit_chain_verified = _boolean(workflow.get("audit_chain_verified"), "workflow.audit_chain_verified")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "mode": "shadow",
        "observed_at": observed_at,
        "subject": {
            "repository": repository,
            "pr_number": pr_number,
            "head_sha": head_sha.lower(),
            "action": action,
        },
        "assessment": {"score": score, "band": band, "factors": factors},
        "changed_services": services,
        "simulated_policy": normalized_policy,
        "workflow": {"id": workflow_id, "audit_chain_verified": audit_chain_verified},
    }


def observation_comment(observation: Mapping[str, object]) -> str:
    observation = validate_observation(observation)
    assessment = _mapping(observation["assessment"], "assessment")
    policy = _mapping(observation["simulated_policy"], "simulated_policy")
    factors = assessment["factors"]
    assert isinstance(factors, list)
    evidence = "\n".join(
        f"- **+{factor['points']}** `{factor['name']}` — {factor['evidence']}"
        for factor in factors
    ) or "- No material risk factors detected"
    simulated_controls = _simulated_controls(policy)
    payload = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return (
        f"{COMMENT_MARKER}\n{DATA_MARKER}{payload}{DATA_SUFFIX}\n"
        "## Engineering Intelligence — PR Guardian shadow observation\n\n"
        "**Advisory only.** This result cannot approve, block, or otherwise change merge status.\n\n"
        f"**Risk score:** `{assessment['score']}/100` ({assessment['band']})\n\n"
        "### Evidence\n"
        f"{evidence}\n\n"
        "### Simulated policy\n"
        f"{simulated_controls}\n\n"
        "For calibration, an authorized reviewer may apply at most one risk label "
        "(`eip-pr-guardian/confirmed-risk` or `eip-pr-guardian/false-positive`) and at most "
        "one utility label (`eip-pr-guardian/useful` or `eip-pr-guardian/not-useful`). "
        "No label means not reviewed."
    )


def observation_from_comment(comment: str) -> dict[str, object] | None:
    start = comment.find(DATA_MARKER)
    if start < 0:
        return None
    start += len(DATA_MARKER)
    end = comment.find(DATA_SUFFIX, start)
    if end < 0:
        raise ValueError("shadow observation comment is malformed")
    try:
        raw = json.loads(comment[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError("shadow observation comment has invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("shadow observation comment payload is not an object")
    return validate_observation(raw)


def closure_outcome(
    *,
    payload: Mapping[str, object],
    observation: Mapping[str, object] | None,
    recorded_at: str | None = None,
) -> dict[str, object]:
    """Join an explicit reviewer label with a prior shadow observation.

    Closing or merging a pull request is not treated as proof that the risk
    assessment was correct.  Only explicit reviewer labels supply a pilot
    classification, and even that remains insufficient for enforcement.
    """
    if str(payload.get("action", "")) != "closed":
        raise ValueError("only closed pull_request events can produce a shadow outcome")
    repository = _mapping(payload.get("repository"), "repository")
    pull_request = _mapping(payload.get("pull_request"), "pull_request")
    name = _string(repository.get("full_name"), "repository.full_name", 200)
    if not _REPOSITORY.fullmatch(name):
        raise ValueError("repository.full_name is invalid")
    number = _integer(payload.get("number"), "number", minimum=1, maximum=10**9)
    head = _mapping(pull_request.get("head"), "pull_request.head")
    head_sha = _string(head.get("sha"), "pull_request.head.sha", 64)
    if not _SHA.fullmatch(head_sha):
        raise ValueError("pull_request.head.sha is invalid")
    labels = _recognized_labels(pull_request.get("labels"))
    risk_signal = _single_signal(labels, _RISK_LABELS, "risk")
    utility_signal = _single_signal(labels, _UTILITY_LABELS, "utility")
    normalized_observation = validate_observation(observation) if observation is not None else None
    matches_observation = False
    if normalized_observation is not None:
        observation_subject = _mapping(normalized_observation["subject"], "observation.subject")
        matches_observation = (
            observation_subject["repository"] == name
            and observation_subject["pr_number"] == number
            and observation_subject["head_sha"] == head_sha.lower()
        )
    if normalized_observation is not None and not matches_observation:
        raise ValueError("shadow observation does not match the closed pull request")
    source: dict[str, object] | None = None
    if normalized_observation is not None:
        assessment = _mapping(normalized_observation["assessment"], "assessment")
        policy = _mapping(normalized_observation["simulated_policy"], "simulated_policy")
        source = {
            "score": assessment["score"],
            "band": assessment["band"],
            "would_block": policy["would_block"],
            "would_require_additional_approval": policy["would_require_additional_approval"],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTCOME_KIND,
        "recorded_at": recorded_at or utc_now(),
        "subject": {"repository": name, "pr_number": number, "head_sha": head_sha.lower()},
        "closure": {"merged": _boolean(pull_request.get("merged"), "pull_request.merged")},
        "reviewer_signal": {"risk": risk_signal, "utility": utility_signal},
        "recognized_labels": labels,
        "source_observation": source,
        "limitations": [
            "PR closure is not evidence of a production incident or rollback outcome.",
            "Reviewer labels are calibration inputs, not authorization for merge enforcement.",
        ],
    }


def validate_outcome(value: Mapping[str, object]) -> dict[str, object]:
    _exact_keys(
        value,
        {
            "schema_version", "kind", "recorded_at", "subject", "closure", "reviewer_signal",
            "recognized_labels", "source_observation", "limitations",
        },
        "shadow outcome",
    )
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != OUTCOME_KIND:
        raise ValueError("unsupported shadow outcome schema")
    _string(value.get("recorded_at"), "recorded_at", 80)
    subject = _mapping(value.get("subject"), "subject")
    _exact_keys(subject, {"repository", "pr_number", "head_sha"}, "subject")
    repository = _string(subject.get("repository"), "subject.repository", 200)
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("subject.repository is invalid")
    pr_number = _integer(subject.get("pr_number"), "subject.pr_number", minimum=1, maximum=10**9)
    head_sha = _string(subject.get("head_sha"), "subject.head_sha", 64)
    if not _SHA.fullmatch(head_sha):
        raise ValueError("subject.head_sha is invalid")
    closure = _mapping(value.get("closure"), "closure")
    _exact_keys(closure, {"merged"}, "closure")
    merged = _boolean(closure.get("merged"), "closure.merged")
    signal = _mapping(value.get("reviewer_signal"), "reviewer_signal")
    _exact_keys(signal, {"risk", "utility"}, "reviewer_signal")
    risk = _string(signal.get("risk"), "reviewer_signal.risk", 40)
    utility = _string(signal.get("utility"), "reviewer_signal.utility", 40)
    if risk not in {"confirmed-risk", "false-positive", "not-reviewed"}:
        raise ValueError("reviewer_signal.risk is invalid")
    if utility not in {"useful", "not-useful", "not-reviewed"}:
        raise ValueError("reviewer_signal.utility is invalid")
    labels = value.get("recognized_labels")
    if not isinstance(labels, list) or labels != sorted(set(labels)) or any(not isinstance(label, str) for label in labels):
        raise ValueError("recognized_labels is invalid")
    raw_source = value.get("source_observation")
    source: dict[str, object] | None
    if raw_source is None:
        source = None
    else:
        raw_source = _mapping(raw_source, "source_observation")
        _exact_keys(raw_source, {"score", "band", "would_block", "would_require_additional_approval"}, "source_observation")
        source_score = _integer(raw_source.get("score"), "source_observation.score", minimum=0, maximum=100)
        source_band = _string(raw_source.get("band"), "source_observation.band", 20)
        if source_band not in _BANDS:
            raise ValueError("source_observation.band is invalid")
        source = {
            "score": source_score,
            "band": source_band,
            "would_block": _boolean(raw_source.get("would_block"), "source_observation.would_block"),
            "would_require_additional_approval": _boolean(
                raw_source.get("would_require_additional_approval"),
                "source_observation.would_require_additional_approval",
            ),
        }
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or not limitations or any(not isinstance(item, str) for item in limitations):
        raise ValueError("limitations is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTCOME_KIND,
        "recorded_at": value["recorded_at"],
        "subject": {"repository": repository, "pr_number": pr_number, "head_sha": head_sha.lower()},
        "closure": {"merged": merged},
        "reviewer_signal": {"risk": risk, "utility": utility},
        "recognized_labels": labels,
        "source_observation": source,
        "limitations": limitations,
    }


def outcome_comment(outcome: Mapping[str, object]) -> str:
    outcome = validate_outcome(outcome)
    signal = _mapping(outcome["reviewer_signal"], "reviewer_signal")
    source = outcome["source_observation"]
    source_text = "No matching shadow observation was found; this closure cannot be used for calibration."
    if source is not None:
        source_data = _mapping(source, "source_observation")
        source_text = (
            f"Matched shadow score: `{source_data['score']}/100`; simulated merge block: "
            f"`{source_data['would_block']}`."
        )
    return (
        f"{OUTCOME_COMMENT_MARKER}\n"
        "## PR Guardian shadow-pilot closure record\n\n"
        f"{source_text}\n\n"
        f"Reviewer risk signal: `{signal['risk']}`. Utility signal: `{signal['utility']}`.\n\n"
        "This is a calibration record only. It does not prove production impact and does not "
        "authorize a blocking rule."
    )


def _simulated_controls(policy: Mapping[str, object]) -> str:
    controls: list[str] = []
    if policy["would_require_extended_tests"]:
        controls.append("would request extended tests")
    if policy["would_require_additional_approval"]:
        controls.append("would request additional approval")
    if policy["would_block"]:
        controls.append("would block pending remediation")
    return ", ".join(controls) if controls else "would use standard branch protections"


def _recognized_labels(raw_labels: object) -> list[str]:
    if not isinstance(raw_labels, list):
        raise ValueError("pull_request.labels is invalid")
    known = set(_RISK_LABELS) | set(_UTILITY_LABELS)
    labels: list[str] = []
    for raw in raw_labels:
        label = _mapping(raw, "pull_request.labels item")
        name = _string(label.get("name"), "pull_request.labels item.name", 100).lower()
        if name in known:
            labels.append(name)
    return sorted(set(labels))


def _single_signal(labels: list[str], choices: Mapping[str, str], name: str) -> str:
    selected = sorted({choices[label] for label in labels if label in choices})
    if len(selected) > 1:
        raise ValueError(f"conflicting {name} reviewer labels")
    return selected[0] if selected else "not-reviewed"


def _exact_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} has unexpected or missing fields")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _string(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} is invalid")
    return value


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} is invalid")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} is invalid")
    return value
