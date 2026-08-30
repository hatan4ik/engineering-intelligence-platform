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
from typing import Literal, Mapping, TypedDict, cast

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

ShadowMode = Literal["shadow", "advisory", "enforce"]
RiskBand = Literal["low", "moderate", "high", "critical"]
RiskSignal = Literal["confirmed-risk", "false-positive", "not-reviewed"]
UtilitySignal = Literal["useful", "not-useful", "not-reviewed"]


class ShadowEnforcement(TypedDict):
    would_block: bool
    reason: str
    rule: str | None
    waived_by: str | None


class ArchitectureViolation(TypedDict):
    rule_id: str
    path: str
    marker: str
    rationale: str
    severity: int


class ArchitectureSkip(TypedDict):
    path: str
    reason: str


class ArchitectureReview(TypedDict):
    violations: list[ArchitectureViolation]
    in_scope: int
    reviewed: int
    skipped: list[ArchitectureSkip]
    summary: str


class ShadowSubject(TypedDict):
    repository: str
    pr_number: int
    head_sha: str
    action: str


class ShadowRiskFactor(TypedDict):
    name: str
    points: int
    evidence: str


class ShadowAssessment(TypedDict):
    score: int
    band: RiskBand
    factors: list[ShadowRiskFactor]


class SimulatedPolicy(TypedDict):
    would_require_extended_tests: bool
    would_require_additional_approval: bool
    would_block: bool


class ShadowWorkflow(TypedDict):
    id: str
    audit_chain_verified: bool


class ShadowObservation(TypedDict):
    schema_version: int
    kind: str
    mode: ShadowMode
    enforcement: ShadowEnforcement
    architecture: ArchitectureReview
    observed_at: str
    subject: ShadowSubject
    assessment: ShadowAssessment
    changed_services: list[str]
    simulated_policy: SimulatedPolicy
    workflow: ShadowWorkflow


class OutcomeSubject(TypedDict):
    repository: str
    pr_number: int
    head_sha: str


class OutcomeClosure(TypedDict):
    merged: bool


class ReviewerSignal(TypedDict):
    risk: RiskSignal
    utility: UtilitySignal


class SourceObservation(TypedDict):
    score: int
    band: RiskBand
    would_block: bool
    would_require_additional_approval: bool


class ShadowOutcome(TypedDict):
    schema_version: int
    kind: str
    recorded_at: str
    subject: OutcomeSubject
    closure: OutcomeClosure
    reviewer_signal: ReviewerSignal
    recognized_labels: list[str]
    source_observation: SourceObservation | None
    limitations: list[str]


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
) -> ShadowObservation:
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


def validate_observation(value: Mapping[str, object]) -> ShadowObservation:
    """Validate and normalize one untrusted workflow-transfer observation.

    Each nested boundary is deliberately validated by a focused function so a
    schema change cannot make this trusted publisher depend on ambient dict
    coercion or a hidden field relationship.
    """

    envelope = _observation_envelope(value)
    mode = _shadow_mode(envelope.get("mode"))
    enforcement = _validate_enforcement(envelope.get("enforcement"), mode=mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "mode": mode,
        "enforcement": enforcement,
        "architecture": _validate_architecture(envelope.get("architecture")),
        "observed_at": _string(envelope.get("observed_at"), "observed_at", 80),
        "subject": _validate_observation_subject(envelope.get("subject")),
        "assessment": _validate_assessment(envelope.get("assessment")),
        "changed_services": _validate_changed_services(envelope.get("changed_services")),
        "simulated_policy": _validate_simulated_policy(envelope.get("simulated_policy")),
        "workflow": _validate_workflow(envelope.get("workflow")),
    }


def _observation_envelope(value: Mapping[str, object]) -> dict[str, object]:
    """Apply explicit legacy defaults before enforcing the current envelope."""

    envelope = {
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
        envelope,
        {
            "schema_version", "kind", "mode", "enforcement", "architecture", "observed_at",
            "subject", "assessment", "changed_services", "simulated_policy", "workflow",
        },
        "shadow observation",
    )
    if envelope.get("schema_version") != SCHEMA_VERSION or envelope.get("kind") != OBSERVATION_KIND:
        raise ValueError("unsupported shadow observation schema")
    return envelope


def _shadow_mode(value: object) -> ShadowMode:
    mode = _string(value, "mode", 20)
    if mode not in {"shadow", "advisory", "enforce"}:
        raise ValueError("mode is invalid")
    return cast(ShadowMode, mode)


def _validate_enforcement(value: object, *, mode: ShadowMode) -> ShadowEnforcement:
    raw = _mapping(value, "enforcement")
    _exact_keys(raw, {"would_block", "reason", "rule", "waived_by"}, "enforcement")
    enforcement: ShadowEnforcement = {
        "would_block": _boolean(raw.get("would_block"), "enforcement.would_block"),
        "reason": _string(raw.get("reason"), "enforcement.reason", 120),
        "rule": _optional_string(raw.get("rule"), "enforcement.rule", 120),
        "waived_by": _optional_string(raw.get("waived_by"), "enforcement.waived_by", 200),
    }
    if enforcement["would_block"] and not enforcement["rule"]:
        raise ValueError("enforcement.rule is required when enforcement.would_block is true")
    if enforcement["would_block"] and mode != "enforce":
        raise ValueError("enforcement.would_block is allowed only in enforce mode")
    return enforcement


def _validate_architecture(value: object) -> ArchitectureReview:
    raw = {
        "in_scope": 0,
        "reviewed": 0,
        "skipped": [],
        **dict(_mapping(value, "architecture")),
    }
    _exact_keys(raw, {"violations", "in_scope", "reviewed", "skipped", "summary"}, "architecture")
    violations = _validate_architecture_violations(raw.get("violations"))
    skipped = _validate_architecture_skips(raw.get("skipped"))
    reviewed = _integer(raw.get("reviewed"), "architecture.reviewed", minimum=0, maximum=10_000)
    in_scope = _integer(raw.get("in_scope"), "architecture.in_scope", minimum=0, maximum=10_000)
    if reviewed > in_scope:
        raise ValueError("architecture.reviewed cannot exceed architecture.in_scope")
    if violations and reviewed == 0:
        raise ValueError("architecture.violations requires at least one reviewed file")
    return {
        "violations": violations,
        "in_scope": in_scope,
        "reviewed": reviewed,
        "skipped": skipped,
        "summary": _string(raw.get("summary"), "architecture.summary", 500),
    }


def _validate_architecture_violations(value: object) -> list[ArchitectureViolation]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("architecture.violations is invalid")
    violations: list[ArchitectureViolation] = []
    for index, item in enumerate(value):
        raw = _mapping(item, f"architecture.violations[{index}]")
        _exact_keys(raw, {"rule_id", "path", "marker", "rationale", "severity"}, f"architecture.violations[{index}]")
        violations.append({
            "rule_id": _string(raw.get("rule_id"), f"architecture.violations[{index}].rule_id", 120),
            "path": _string(raw.get("path"), f"architecture.violations[{index}].path", 400),
            "marker": _string(raw.get("marker"), f"architecture.violations[{index}].marker", 400),
            "rationale": _string(raw.get("rationale"), f"architecture.violations[{index}].rationale", 500),
            "severity": _integer(raw.get("severity"), f"architecture.violations[{index}].severity", minimum=1, maximum=5),
        })
    return violations


def _validate_architecture_skips(value: object) -> list[ArchitectureSkip]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("architecture.skipped is invalid")
    skipped: list[ArchitectureSkip] = []
    for index, item in enumerate(value):
        raw = _mapping(item, f"architecture.skipped[{index}]")
        _exact_keys(raw, {"path", "reason"}, f"architecture.skipped[{index}]")
        skipped.append({
            "path": _string(raw.get("path"), f"architecture.skipped[{index}].path", 400),
            "reason": _string(raw.get("reason"), f"architecture.skipped[{index}].reason", 200),
        })
    return skipped


def _validate_observation_subject(value: object) -> ShadowSubject:
    raw = _mapping(value, "subject")
    _exact_keys(raw, {"repository", "pr_number", "head_sha", "action"}, "subject")
    repository = _string(raw.get("repository"), "subject.repository", 200)
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("subject.repository is invalid")
    head_sha = _string(raw.get("head_sha"), "subject.head_sha", 64)
    if not _SHA.fullmatch(head_sha):
        raise ValueError("subject.head_sha is invalid")
    return {
        "repository": repository,
        "pr_number": _integer(raw.get("pr_number"), "subject.pr_number", minimum=1, maximum=10**9),
        "head_sha": head_sha.lower(),
        "action": _string(raw.get("action"), "subject.action", 64),
    }


def _validate_assessment(value: object) -> ShadowAssessment:
    raw = _mapping(value, "assessment")
    _exact_keys(raw, {"score", "band", "factors"}, "assessment")
    band = _string(raw.get("band"), "assessment.band", 20)
    if band not in _BANDS:
        raise ValueError("assessment.band is invalid")
    return {
        "score": _integer(raw.get("score"), "assessment.score", minimum=0, maximum=100),
        "band": cast(RiskBand, band),
        "factors": _validate_risk_factors(raw.get("factors")),
    }


def _validate_risk_factors(value: object) -> list[ShadowRiskFactor]:
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("assessment.factors is invalid")
    factors: list[ShadowRiskFactor] = []
    for index, item in enumerate(value):
        raw = _mapping(item, f"assessment.factors[{index}]")
        _exact_keys(raw, {"name", "points", "evidence"}, f"assessment.factors[{index}]")
        factors.append({
            "name": _string(raw.get("name"), f"assessment.factors[{index}].name", 120),
            "points": _integer(raw.get("points"), f"assessment.factors[{index}].points", minimum=0, maximum=100),
            "evidence": _string(raw.get("evidence"), f"assessment.factors[{index}].evidence", 500),
        })
    return factors


def _validate_changed_services(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("changed_services is invalid")
    services = [_string(item, "changed_services item", 120) for item in value]
    if services != sorted(set(services)):
        raise ValueError("changed_services must be sorted and unique")
    return services


def _validate_simulated_policy(value: object) -> SimulatedPolicy:
    raw = _mapping(value, "simulated_policy")
    _exact_keys(
        raw,
        {"would_require_extended_tests", "would_require_additional_approval", "would_block"},
        "simulated_policy",
    )
    return {
        "would_require_extended_tests": _boolean(
            raw.get("would_require_extended_tests"), "simulated_policy.would_require_extended_tests"
        ),
        "would_require_additional_approval": _boolean(
            raw.get("would_require_additional_approval"), "simulated_policy.would_require_additional_approval"
        ),
        "would_block": _boolean(raw.get("would_block"), "simulated_policy.would_block"),
    }


def _validate_workflow(value: object) -> ShadowWorkflow:
    raw = _mapping(value, "workflow")
    _exact_keys(raw, {"id", "audit_chain_verified"}, "workflow")
    return {
        "id": _string(raw.get("id"), "workflow.id", 240),
        "audit_chain_verified": _boolean(raw.get("audit_chain_verified"), "workflow.audit_chain_verified"),
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
    mode = observation["mode"]
    assessment = observation["assessment"]
    policy = observation["simulated_policy"]
    enforcement = observation["enforcement"]
    factors = assessment["factors"]
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


def observation_from_comment(comment: str) -> ShadowObservation | None:
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
) -> ShadowOutcome:
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
        observation_subject = normalized_observation["subject"]
        matches_observation = (
            observation_subject["repository"] == name
            and observation_subject["pr_number"] == number
            and observation_subject["head_sha"] == head_sha.lower()
        )
    if normalized_observation is not None and not matches_observation:
        raise ValueError("shadow observation does not match the closed pull request")
    source: SourceObservation | None = None
    if normalized_observation is not None:
        assessment = normalized_observation["assessment"]
        policy = normalized_observation["simulated_policy"]
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
        "reviewer_signal": {
            "risk": cast(RiskSignal, risk_signal),
            "utility": cast(UtilitySignal, utility_signal),
        },
        "recognized_labels": labels,
        "source_observation": source,
        "limitations": [
            "PR closure is not evidence of a production incident or rollback outcome.",
            "Reviewer labels are calibration inputs, not authorization for merge enforcement.",
        ],
    }


def validate_outcome(value: Mapping[str, object]) -> ShadowOutcome:
    """Validate and normalize one closure artifact before calibration uses it."""

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
    closure = _mapping(value.get("closure"), "closure")
    _exact_keys(closure, {"merged"}, "closure")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTCOME_KIND,
        "recorded_at": _string(value.get("recorded_at"), "recorded_at", 80),
        "subject": _validate_outcome_subject(value.get("subject")),
        "closure": {"merged": _boolean(closure.get("merged"), "closure.merged")},
        "reviewer_signal": _validate_reviewer_signal(value.get("reviewer_signal")),
        "recognized_labels": _validate_recognized_labels(value.get("recognized_labels")),
        "source_observation": _validate_source_observation(value.get("source_observation")),
        "limitations": _validate_limitations(value.get("limitations")),
    }


def _validate_outcome_subject(value: object) -> OutcomeSubject:
    raw = _mapping(value, "subject")
    _exact_keys(raw, {"repository", "pr_number", "head_sha"}, "subject")
    repository = _string(raw.get("repository"), "subject.repository", 200)
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("subject.repository is invalid")
    head_sha = _string(raw.get("head_sha"), "subject.head_sha", 64)
    if not _SHA.fullmatch(head_sha):
        raise ValueError("subject.head_sha is invalid")
    return {
        "repository": repository,
        "pr_number": _integer(raw.get("pr_number"), "subject.pr_number", minimum=1, maximum=10**9),
        "head_sha": head_sha.lower(),
    }


def _validate_reviewer_signal(value: object) -> ReviewerSignal:
    raw = _mapping(value, "reviewer_signal")
    _exact_keys(raw, {"risk", "utility"}, "reviewer_signal")
    risk = _string(raw.get("risk"), "reviewer_signal.risk", 40)
    utility = _string(raw.get("utility"), "reviewer_signal.utility", 40)
    if risk not in {"confirmed-risk", "false-positive", "not-reviewed"}:
        raise ValueError("reviewer_signal.risk is invalid")
    if utility not in {"useful", "not-useful", "not-reviewed"}:
        raise ValueError("reviewer_signal.utility is invalid")
    return {"risk": cast(RiskSignal, risk), "utility": cast(UtilitySignal, utility)}


def _validate_recognized_labels(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("recognized_labels is invalid")
    labels = cast(list[str], value)
    if labels != sorted(set(labels)):
        raise ValueError("recognized_labels is invalid")
    return labels


def _validate_source_observation(value: object) -> SourceObservation | None:
    if value is None:
        return None
    raw = _mapping(value, "source_observation")
    _exact_keys(raw, {"score", "band", "would_block", "would_require_additional_approval"}, "source_observation")
    band = _string(raw.get("band"), "source_observation.band", 20)
    if band not in _BANDS:
        raise ValueError("source_observation.band is invalid")
    return {
        "score": _integer(raw.get("score"), "source_observation.score", minimum=0, maximum=100),
        "band": cast(RiskBand, band),
        "would_block": _boolean(raw.get("would_block"), "source_observation.would_block"),
        "would_require_additional_approval": _boolean(
            raw.get("would_require_additional_approval"),
            "source_observation.would_require_additional_approval",
        ),
    }


def _validate_limitations(value: object) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise ValueError("limitations is invalid")
    return value


def outcome_comment(outcome: Mapping[str, object]) -> str:
    outcome = validate_outcome(outcome)
    signal = outcome["reviewer_signal"]
    source = outcome["source_observation"]
    source_text = "No matching shadow observation was found; this closure cannot be used for calibration."
    if source is not None:
        source_text = (
            f"Matched shadow score: `{source['score']}/100`; simulated merge block: "
            f"`{source['would_block']}`."
        )
    return (
        f"{OUTCOME_COMMENT_MARKER}\n"
        "## PR Guardian shadow-pilot closure record\n\n"
        f"{source_text}\n\n"
        f"Reviewer risk signal: `{signal['risk']}`. Utility signal: `{signal['utility']}`.\n\n"
        "This is a calibration record only. It does not prove production impact and does not "
        "authorize a blocking rule."
    )


def _simulated_controls(policy: SimulatedPolicy) -> str:
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


def _optional_string(value: object, name: str, maximum: int) -> str | None:
    return None if value is None else _string(value, name, maximum)


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
