"""Portable PR Guardian observation records and their rendered comment.

The records contain only deterministic assessment metadata, so they are safe to
pass between the untrusted pull-request evaluation workflow and a separate,
trusted publisher workflow.  They are *not* production evidence.

A record carries the mode the evaluated repository chose for itself — ``shadow``,
``advisory``, or ``enforce`` — and ``observation_comment`` renders the authority
that mode actually has.  A record never authorizes enforcement: the mode comes
from the repository's own ``.eip/pr-guardian.json``, and the trusted publisher
re-derives the published conclusion from that file rather than trusting this
record.  Closure/outcome records below remain non-enforcing calibration inputs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Mapping

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
    mode: str = "shadow",
    enforcement: Mapping[str, object] | None = None,
    architecture: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a strictly shaped observation for the repository's current mode.

    ``mode`` comes from the evaluated repository's own configuration.  The
    optional ``enforcement`` and ``architecture`` sections default to an
    explicitly non-blocking, empty state so a caller that knows nothing about
    them still produces a record the trusted publisher accepts.
    """
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "mode": mode,
        "enforcement": dict(enforcement) if enforcement is not None else {
            "would_block": False,
            "reason": "mode-not-enforcing",
            "rule": None,
            "waived_by": None,
        },
        "architecture": dict(architecture) if architecture is not None else {
            "violations": [],
            "in_scope": 0,
            "reviewed": 0,
            "skipped": [],
            "summary": "Architecture Guard did not run for this evaluation.",
        },
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

    def _optional_string(raw: object, name: str, maximum: int) -> str | None:
        return None if raw is None else _string(raw, name, maximum)

    # Records written before advisory/enforce modes existed carry neither an
    # enforcement nor an architecture section.  Fill both with their explicitly
    # non-blocking, empty defaults so old artifacts keep validating and every
    # normalized record has the same shape.
    value = {
        "enforcement": {
            "would_block": False,
            "reason": "mode-not-enforcing",
            "rule": None,
            "waived_by": None,
        },
        "architecture": {
            "violations": [],
            "in_scope": 0,
            "reviewed": 0,
            "skipped": [],
            "summary": "Architecture Guard did not run for this evaluation.",
        },
        **dict(value),
    }
    _exact_keys(
        value,
        {
            "schema_version", "kind", "mode", "enforcement", "architecture", "observed_at",
            "subject", "assessment", "changed_services", "simulated_policy", "workflow",
        },
        "shadow observation",
    )
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != OBSERVATION_KIND:
        raise ValueError("unsupported shadow observation schema")
    mode = _string(value.get("mode"), "mode", 20)
    if mode not in {"shadow", "advisory", "enforce"}:
        raise ValueError("mode is invalid")

    raw_enforcement = _mapping(value.get("enforcement"), "enforcement")
    _exact_keys(raw_enforcement, {"would_block", "reason", "rule", "waived_by"}, "enforcement")
    enforcement: dict[str, object] = {
        "would_block": _boolean(raw_enforcement.get("would_block"), "enforcement.would_block"),
        "reason": _string(raw_enforcement.get("reason"), "enforcement.reason", 120),
        "rule": _optional_string(raw_enforcement.get("rule"), "enforcement.rule", 120),
        "waived_by": _optional_string(raw_enforcement.get("waived_by"), "enforcement.waived_by", 200),
    }
    # A record can describe a block only when it also names the rule that
    # produced it; an unattributed block is not publishable.
    if enforcement["would_block"] and not enforcement["rule"]:
        raise ValueError("enforcement.rule is required when enforcement.would_block is true")
    if enforcement["would_block"] and mode != "enforce":
        raise ValueError("enforcement.would_block is allowed only in enforce mode")

    # Older records carried only violations+summary; fill the coverage counts
    # with a "nothing was reviewed" default so they cannot read as a clean run.
    raw_architecture = {
        "in_scope": 0,
        "reviewed": 0,
        "skipped": [],
        **dict(_mapping(value.get("architecture"), "architecture")),
    }
    _exact_keys(
        raw_architecture,
        {"violations", "in_scope", "reviewed", "skipped", "summary"},
        "architecture",
    )
    raw_violations = raw_architecture.get("violations")
    if not isinstance(raw_violations, list) or len(raw_violations) > 64:
        raise ValueError("architecture.violations is invalid")
    violations: list[dict[str, object]] = []
    for index, raw in enumerate(raw_violations):
        item = _mapping(raw, f"architecture.violations[{index}]")
        _exact_keys(
            item,
            {"rule_id", "path", "marker", "rationale", "severity"},
            f"architecture.violations[{index}]",
        )
        violations.append({
            "rule_id": _string(item.get("rule_id"), f"architecture.violations[{index}].rule_id", 120),
            "path": _string(item.get("path"), f"architecture.violations[{index}].path", 400),
            "marker": _string(item.get("marker"), f"architecture.violations[{index}].marker", 400),
            "rationale": _string(item.get("rationale"), f"architecture.violations[{index}].rationale", 500),
            "severity": _integer(
                item.get("severity"), f"architecture.violations[{index}].severity", minimum=1, maximum=5
            ),
        })
    raw_skipped = raw_architecture.get("skipped")
    if not isinstance(raw_skipped, list) or len(raw_skipped) > 64:
        raise ValueError("architecture.skipped is invalid")
    skipped: list[dict[str, object]] = []
    for index, raw in enumerate(raw_skipped):
        item = _mapping(raw, f"architecture.skipped[{index}]")
        _exact_keys(item, {"path", "reason"}, f"architecture.skipped[{index}]")
        skipped.append({
            "path": _string(item.get("path"), f"architecture.skipped[{index}].path", 400),
            "reason": _string(item.get("reason"), f"architecture.skipped[{index}].reason", 200),
        })
    reviewed = _integer(
        raw_architecture.get("reviewed"), "architecture.reviewed", minimum=0, maximum=10_000
    )
    in_scope = _integer(
        raw_architecture.get("in_scope"), "architecture.in_scope", minimum=0, maximum=10_000
    )
    if reviewed > in_scope:
        raise ValueError("architecture.reviewed cannot exceed architecture.in_scope")
    # A record must not report findings it claims never to have read.
    if violations and reviewed == 0:
        raise ValueError("architecture.violations requires at least one reviewed file")
    architecture = {
        "violations": violations,
        "in_scope": in_scope,
        "reviewed": reviewed,
        "skipped": skipped,
        "summary": _string(raw_architecture.get("summary"), "architecture.summary", 500),
    }

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
        "mode": mode,
        "enforcement": enforcement,
        "architecture": architecture,
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


def observation_comment(
    observation: Mapping[str, object],
    *,
    published_conclusion: str | None = None,
    publish_reason: str | None = None,
) -> str:
    """Render the sticky comment, stating the authority this mode actually has.

    This is the single rendering path for an observation.  The wording is a
    function of the record's own ``mode``: a shadow record still says it cannot
    change merge status, and an enforcing record names its rule, says whether it
    would block *this* pull request, and names any waiver that applied.  A
    trusted publisher that re-derived a different conclusion passes it in via
    ``published_conclusion`` so the comment discloses what was actually posted.
    """
    # Imported here rather than at module scope so this transfer-record module
    # keeps its narrow import surface; `explain` owns the reason wording.
    from product.pr_guardian.enforcement import explain

    observation = validate_observation(observation)
    mode = str(observation["mode"])
    assessment = _mapping(observation["assessment"], "assessment")
    policy = _mapping(observation["simulated_policy"], "simulated_policy")
    enforcement = _mapping(observation["enforcement"], "enforcement")
    factors = assessment["factors"]
    assert isinstance(factors, list)
    evidence = "\n".join(
        f"- **+{factor['points']}** `{factor['name']}` — {factor['evidence']}"
        for factor in factors
    ) or "- No material risk factors detected"
    simulated_controls = _simulated_controls(policy)
    payload = json.dumps(observation, sort_keys=True, separators=(",", ":"))

    if mode == "advisory":
        heading = "## Engineering Intelligence — PR Guardian advisory review"
        authority = (
            "**Advisory — non-blocking check for this repository's certified scope.** "
            "It is published as a neutral check and does not change merge status."
        )
        policy_heading = "### Advisory policy signals"
    elif mode == "enforce":
        heading = "## Engineering Intelligence — PR Guardian enforcement check"
        would_block = bool(enforcement["would_block"])
        verdict = (
            "**would block this pull request**"
            if would_block
            else "does not block this pull request"
        )
        authority_lines = [
            "**Selective enforcement is enabled for this repository by its service owners.**",
            "",
            f"- **Rule:** `{enforcement['rule'] or 'none'}`",
            f"- **Result:** this change {verdict} — {explain(str(enforcement['reason']))}",
        ]
        if enforcement["waived_by"]:
            authority_lines.append(
                f"- **Waiver applied by:** `{enforcement['waived_by']}` "
                "(a service owner accepted this risk in `.eip/pr-guardian.json`)"
            )
        authority = "\n".join(authority_lines)
        policy_heading = "### Advisory policy signals"
    else:
        heading = "## Engineering Intelligence — PR Guardian shadow observation"
        authority = (
            "**Advisory only.** This result cannot approve, block, or otherwise change merge status."
        )
        policy_heading = "### Simulated policy"

    if published_conclusion is not None:
        authority += (
            f"\n\n**Published check conclusion:** `{published_conclusion}` — "
            f"{explain(publish_reason or '')}"
        )
    policy_note = "" if mode == "shadow" else (
        "\n\nThese are the risk policy's recommendations to reviewers. They are separate "
        "from the enforcement rule above, which is the only thing that can change this "
        "check's conclusion."
    )
    return (
        f"{COMMENT_MARKER}\n{DATA_MARKER}{payload}{DATA_SUFFIX}\n"
        f"{heading}\n\n"
        f"{authority}\n\n"
        f"**Risk score:** `{assessment['score']}/100` ({assessment['band']})\n\n"
        "### Evidence\n"
        f"{evidence}\n\n"
        f"{policy_heading}\n"
        f"{simulated_controls}{policy_note}\n\n"
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
