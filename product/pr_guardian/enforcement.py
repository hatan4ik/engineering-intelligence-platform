"""The only code path that may ever fail a PR Guardian check.

Everything here is a pure function of a repository-owned configuration, a
deterministic risk assessment, the changed file list, and the clock.  There is
no model, no learned threshold, and no platform-side override that can turn
blocking on: ``enforcement_decision`` returns ``would_block=False`` unless the
repository's own configuration says ``enforce`` *and* the one selected rule's
condition holds *and* no owner waiver covers the change.

Two independent off switches exist:

* ``EIP_PR_GUARDIAN_KILL_SWITCH=true`` in the environment of either the
  evaluation job or the trusted publisher, which forces a non-blocking result;
* the mandatory ``expires_on`` in the owner approval, after which enforcement
  lapses until a human re-approves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from fnmatch import fnmatch
from typing import Iterable, Literal, Mapping, assert_never

from intelligence.risk import RiskAssessment

from .contracts import EnforcementRule, ProductMode, RepositoryConfig


PublishConclusion = Literal["neutral", "failure"]


class EnforcementReason(StrEnum):
    KILL_SWITCH = "kill-switch"
    MODE_NOT_ENFORCING = "mode-not-enforcing"
    APPROVAL_EXPIRED = "enforcement-approval-expired"
    CONDITION_NOT_MET = "rule-condition-not-met"
    WAIVED = "waived-by-owner"
    CONDITION_MET = "rule-condition-met"
    CONTEXT_UNQUALIFIED = "company-brain-context-unqualified"
    OBSERVATION_NOT_ENFORCING = "observation-mode-not-enforcing"
    CONFIG_NOT_ENFORCING = "repository-config-not-enforcing"
    RULE_MISMATCH = "rule-does-not-match-repository-config"
    THRESHOLD_NOT_MET = "score-below-configured-threshold"
    ENFORCED = "enforced-by-repository-config"


KILL_SWITCH_ENV = "EIP_PR_GUARDIAN_KILL_SWITCH"

REASON_KILL_SWITCH = EnforcementReason.KILL_SWITCH.value
REASON_MODE_NOT_ENFORCING = EnforcementReason.MODE_NOT_ENFORCING.value
REASON_APPROVAL_EXPIRED = EnforcementReason.APPROVAL_EXPIRED.value
REASON_CONDITION_NOT_MET = EnforcementReason.CONDITION_NOT_MET.value
REASON_WAIVED = EnforcementReason.WAIVED.value
REASON_CONDITION_MET = EnforcementReason.CONDITION_MET.value
REASON_CONTEXT_UNQUALIFIED = EnforcementReason.CONTEXT_UNQUALIFIED.value

# Publisher-side reasons for declining to turn an observation into a failure.
REASON_OBSERVATION_NOT_ENFORCING = EnforcementReason.OBSERVATION_NOT_ENFORCING.value
REASON_CONFIG_NOT_ENFORCING = EnforcementReason.CONFIG_NOT_ENFORCING.value
REASON_RULE_MISMATCH = EnforcementReason.RULE_MISMATCH.value
REASON_THRESHOLD_NOT_MET = EnforcementReason.THRESHOLD_NOT_MET.value
REASON_ENFORCED = EnforcementReason.ENFORCED.value

# The risk factor that must be present for each rule, and the predicate that
# identifies the files the rule is actually about.  A waiver has to cover every
# one of those files, not merely one of them.
_WEAK_TEST_EVIDENCE_FACTOR = "weak-test-evidence"


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in lowered
        or lowered.startswith("test")
        or lowered.endswith(("_test.py", ".spec.ts", ".test.ts", ".spec.js", ".test.js"))
    )


def is_docs_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".md", ".rst", ".txt")) or lowered.startswith("docs/")


def is_iac_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".tf", ".tfvars")) or lowered.startswith(
        ("infra/", "terraform/", "helm/", "k8s/")
    )


def is_delivery_control_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith((".github/workflows/", "pipelines/", "azure-pipelines")) or lowered.endswith(
        ("azure-pipelines.yml", "jenkinsfile")
    )


def is_security_boundary_path(path: str) -> bool:
    lowered = path.lower()
    markers = (
        "iam", "rbac", "identity", "auth", "security", "policy", "keyvault",
        "key_vault", "networkpolicy",
    )
    return any(marker in lowered for marker in markers)


_RULE_TRIGGERS = {
    EnforcementRule.IAC_CHANGE_WITHOUT_TEST_EVIDENCE: ("infrastructure-change", is_iac_path),
    EnforcementRule.SECURITY_CHANGE_WITHOUT_TEST_EVIDENCE: (
        "security-boundary-change",
        is_security_boundary_path,
    ),
}


@dataclass(frozen=True)
class EnforcementDecision:
    """Why a change would or would not be blocked, in transferable form."""

    would_block: bool
    reason: EnforcementReason | str
    rule: str | None = None
    waived_by: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "would_block": self.would_block,
            "reason": str(self.reason),
            "rule": self.rule,
            "waived_by": self.waived_by,
        }


@dataclass(frozen=True)
class PublishDecision:
    """The conclusion the trusted publisher is willing to stand behind."""

    conclusion: PublishConclusion | str
    reason: EnforcementReason | str


_EMPTY_ENV: Mapping[str, str] = {}


def kill_switch_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Only the exact string ``true`` disables enforcement, case-insensitively.

    Pure dependency injection: defaults to an empty mapping rather than reading
    ambient process environment.
    """
    source = _EMPTY_ENV if environ is None else environ
    return str(source.get(KILL_SWITCH_ENV, "")).strip().lower() == "true"


def enforcement_decision(
    config: RepositoryConfig,
    assessment: RiskAssessment,
    changed_files: Iterable[str],
    now: date | datetime,
    *,
    environ: Mapping[str, str] | None = None,
) -> EnforcementDecision:
    """Decide whether one change meets the repository's single blocking rule."""
    today = now.date() if isinstance(now, datetime) else now
    policy = config.enforcement
    rule = None if policy is None else str(policy.rule)

    if kill_switch_enabled(environ):
        return EnforcementDecision(False, REASON_KILL_SWITCH, rule)
    if config.mode is not ProductMode.ENFORCE or policy is None:
        return EnforcementDecision(False, REASON_MODE_NOT_ENFORCING)
    if not policy.is_active_on(today):
        return EnforcementDecision(False, REASON_APPROVAL_EXPIRED, rule)

    factor_name, matches_path = _RULE_TRIGGERS[policy.rule]
    factors = {factor.name for factor in assessment.factors}
    triggering = tuple(path for path in changed_files if matches_path(path))
    condition_met = (
        assessment.score >= policy.threshold
        and factor_name in factors
        and _WEAK_TEST_EVIDENCE_FACTOR in factors
        and bool(triggering)
    )
    if not condition_met:
        return EnforcementDecision(False, REASON_CONDITION_NOT_MET, rule)

    for waiver in policy.waivers:
        if not waiver.is_active_on(today):
            continue
        # A waiver excuses a change only when it covers every file the rule
        # fired on; a partial match leaves un-waived risk in the same change.
        if all(fnmatch(path, waiver.path_glob) for path in triggering):
            return EnforcementDecision(False, REASON_WAIVED, rule, waiver.owner)

    return EnforcementDecision(True, REASON_CONDITION_MET, rule)


def publishable_conclusion(
    observation: Mapping[str, object],
    config: RepositoryConfig,
    *,
    environ: Mapping[str, str] | None = None,
    now: date | datetime | None = None,
) -> PublishDecision:
    """Re-derive the publishable conclusion from the *trusted* configuration.

    The observation arrives from a workflow that ran with a read-only token on
    an untrusted pull request.  This constrains the *escalation* direction only:
    a ``failure`` requires the trusted default-branch configuration to name the
    same enforcing rule and a score that clears its threshold, and any
    disagreement degrades to ``neutral``.

    It does **not** stop a pull request from suppressing a block on itself.  The
    evaluation workflow is ``pull_request``-triggered, so its definition comes
    from the pull-request head; an author who edits
    ``.github/workflows/pr-guardian.yml`` can upload an artifact reporting
    ``would_block: false``, which publishes ``neutral``.  Enforcing repositories
    must require Code Owner review on ``.github/workflows/`` and ``.eip/``; see
    docs/PR-GUARDIAN-REPOSITORY-CONFIG.md.
    """
    today = _today(now)
    enforcement = observation.get("enforcement")
    if not isinstance(enforcement, Mapping):
        return PublishDecision("neutral", REASON_OBSERVATION_NOT_ENFORCING)

    if observation.get("mode") != ProductMode.ENFORCE.value:
        return PublishDecision("neutral", REASON_OBSERVATION_NOT_ENFORCING)
    if enforcement.get("would_block") is not True:
        return PublishDecision("neutral", str(enforcement.get("reason") or REASON_CONDITION_NOT_MET))
    if kill_switch_enabled(environ):
        return PublishDecision("neutral", REASON_KILL_SWITCH)
    if config.mode is not ProductMode.ENFORCE or config.enforcement is None:
        return PublishDecision("neutral", REASON_CONFIG_NOT_ENFORCING)
    if enforcement.get("rule") != str(config.enforcement.rule):
        return PublishDecision("neutral", REASON_RULE_MISMATCH)
    # Re-derive the one part of the rule condition the record still carries.
    # A forged `would_block: true` cannot fail a check unless the score the
    # observation reports actually clears the configured threshold.
    assessment = observation.get("assessment")
    score = assessment.get("score") if isinstance(assessment, Mapping) else None
    if type(score) is not int or score < config.enforcement.threshold:
        return PublishDecision("neutral", REASON_THRESHOLD_NOT_MET)
    if not config.enforcement.is_active_on(today):
        return PublishDecision("neutral", REASON_APPROVAL_EXPIRED)
    return PublishDecision("failure", REASON_ENFORCED)


def explain(reason: EnforcementReason | str) -> str:
    """Exhaustively format human explanations for each enforcement reason."""
    try:
        typed = EnforcementReason(reason)
    except ValueError:
        return str(reason)

    match typed:
        case EnforcementReason.KILL_SWITCH:
            return "the operator kill switch is engaged"
        case EnforcementReason.MODE_NOT_ENFORCING:
            return "this repository has not enabled enforcement"
        case EnforcementReason.APPROVAL_EXPIRED:
            return "the service-owner approval for enforcement has expired"
        case EnforcementReason.CONDITION_NOT_MET:
            return "the enforcement rule's condition was not met"
        case EnforcementReason.WAIVED:
            return "a service owner recorded a waiver covering every affected file"
        case EnforcementReason.CONDITION_MET:
            return "the enforcement rule's condition was met"
        case EnforcementReason.CONTEXT_UNQUALIFIED:
            return (
                "the Company Brain context was insufficient, stale, or conflicted for a control decision"
            )
        case EnforcementReason.OBSERVATION_NOT_ENFORCING:
            return "the evaluation was not enforcing"
        case EnforcementReason.CONFIG_NOT_ENFORCING:
            return (
                "the trusted repository configuration is not enforcing this pull request"
            )
        case EnforcementReason.RULE_MISMATCH:
            return (
                "the evaluated rule does not match the rule in the trusted repository configuration"
            )
        case EnforcementReason.THRESHOLD_NOT_MET:
            return (
                "the reported risk score does not reach the threshold in the trusted "
                "repository configuration"
            )
        case EnforcementReason.ENFORCED:
            return "the repository configuration enforces this rule"
        case _ as unreachable:
            assert_never(unreachable)


def _today(now: date | datetime | None) -> date:
    if now is None:
        return datetime.now(timezone.utc).date()
    return now.date() if isinstance(now, datetime) else now
