"""L2 proposals: an exact proposed action plus its rollback path, for a human to execute.

The autonomy ladder in ``architecture/design.md`` puts this module at L2. L1
recommends with evidence; L2 turns that recommendation into something a human can
act on directly -- a revert PR with a named commit range, an allow-listed runbook
with its rollback runbook, or a ticket. Nothing here executes, schedules, or
authorizes anything: every proposal carries ``requires_human`` and it is a module
constant that callers cannot override.

The runbook identifiers below are *copied* from ``remediation/catalog.py``
(``default_catalog``). The ``remediation`` package is deliberately not part of the
API image closure (see ``app/import_closure.py`` and ``.dockerignore``), so this
module must not import it. ``tests/test_l2_proposals.py`` imports the real catalog
and asserts these identifiers still exist there, so the copy cannot drift silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable, Literal, Mapping, Sequence

from intelligence.deployment_failures import DeploymentFailureAnalysis
from intelligence.incidents import (
    EvidenceEvent,
    EvidenceKind,
    Hypothesis,
    IncidentAnalysis,
)

ProposalKind = Literal["runbook", "corrective-pr", "ticket"]

#: L2 never executes. This is a constant, not a policy input.
REQUIRES_HUMAN: Final[Literal[True]] = True

#: Attribute keys that may carry the commit a deployment shipped.
_COMMIT_KEYS: Final[tuple[str, ...]] = (
    "commit",
    "commit_sha",
    "sourceVersion",
    "source_version",
)

#: Attribute keys that may carry the last known-good commit for a deployment.
_LAST_GOOD_KEYS: Final[tuple[str, ...]] = (
    "last_good_commit",
    "previous_commit",
    "previousCommit",
)


@dataclass(frozen=True)
class AllowListedRunbook:
    """One entry copied from ``remediation.catalog.default_catalog``."""

    runbook_id: str
    description: str
    rollback_runbook_id: str | None


# failure class -> allow-listed runbook. Source: remediation/catalog.py.
ALLOW_LISTED_RUNBOOKS: Final[Mapping[str, AllowListedRunbook]] = {
    "crashloop": AllowListedRunbook(
        "aks.restart.crashloop",
        "Restart a bounded deployment after CrashLoopBackOff evidence",
        None,
    ),
    "readiness-regression": AllowListedRunbook(
        "aks.rollback.readiness",
        "Rollback a deployment when readiness regressed after a release",
        "aks.rollout.redo",
    ),
    "oomkilled": AllowListedRunbook(
        "aks.restart.oom",
        "Restart a bounded deployment after OOMKilled evidence while preserving resource policy",
        None,
    ),
    "deployment-regression": AllowListedRunbook(
        "aks.rollout.undo",
        "Undo the current Kubernetes deployment rollout",
        "aks.rollout.redo",
    ),
}


@dataclass(frozen=True)
class L2Proposal:
    """A proposed action a human executes. Construction cannot clear ``requires_human``."""

    kind: ProposalKind
    title: str
    exact_action: str
    rollback_path: str
    evidence_refs: tuple[str, ...] = ()

    @property
    def requires_human(self) -> Literal[True]:
        return REQUIRES_HUMAN

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "title": self.title,
            "exact_action": self.exact_action,
            "rollback_path": self.rollback_path,
            "evidence_refs": list(self.evidence_refs),
            "requires_human": self.requires_human,
        }


def proposals_to_dicts(proposals: Iterable[L2Proposal]) -> list[dict[str, object]]:
    return [proposal.to_dict() for proposal in proposals]


def build_proposals(
    analysis: IncidentAnalysis | DeploymentFailureAnalysis,
    *,
    service: str,
    environment: str,
    evidence: Sequence[EvidenceEvent] = (),
) -> tuple[L2Proposal, ...]:
    """Turn an L1 analysis into L2 proposals. Pure: no I/O, no execution, no state.

    ``evidence`` supplies the event timeline for a :class:`DeploymentFailureAnalysis`,
    which carries only derived facts. For an :class:`IncidentAnalysis` it defaults to
    the analysis timeline.
    """

    timeline = tuple(evidence) or _analysis_timeline(analysis)
    hypotheses = tuple(analysis.hypotheses)
    subject = _subject(analysis)

    proposals: list[L2Proposal] = []

    revert = _corrective_pr(
        timeline,
        service=service,
        environment=environment,
        subject=subject,
        anchor_id=_anchor_deployment_id(analysis),
    )
    if revert is not None:
        proposals.append(revert)

    runbook = _runbook(
        hypotheses, service=service, environment=environment, subject=subject
    )
    if runbook is not None:
        proposals.append(runbook)

    if not proposals:
        proposals.append(
            _ticket(
                hypotheses,
                timeline,
                service=service,
                environment=environment,
                subject=subject,
            )
        )

    return tuple(proposals)


def _analysis_timeline(
    analysis: IncidentAnalysis | DeploymentFailureAnalysis,
) -> tuple[EvidenceEvent, ...]:
    return tuple(getattr(analysis, "timeline", ()))


def _anchor_deployment_id(
    analysis: IncidentAnalysis | DeploymentFailureAnalysis,
) -> str | None:
    """The deployment the analysis is about, when it is about one.

    ``investigate_deployment_failure`` anchors the whole analysis on the incoming
    deployment id. A revert proposal must be anchored on the same event: the
    evidence window also contains deployments made *after* the failure (a hotfix,
    an attempted rollback), and reverting to the newest one would tell the
    operator to revert the fix. ``IncidentAnalysis`` has no such anchor.
    """

    deployment_id = getattr(analysis, "deployment_id", None)
    return str(deployment_id) if deployment_id else None


def _subject(analysis: IncidentAnalysis | DeploymentFailureAnalysis) -> str:
    deployment_id = _anchor_deployment_id(analysis)
    return f"deployment {deployment_id}" if deployment_id else "the incident"


def _attribute(event: EvidenceEvent, keys: Iterable[str]) -> str | None:
    attributes = dict(event.attributes)
    for key in keys:
        value = attributes.get(key)
        if value:
            return str(value)
    return None


def _corrective_pr(
    timeline: Sequence[EvidenceEvent],
    *,
    service: str,
    environment: str,
    subject: str,
    anchor_id: str | None = None,
) -> L2Proposal | None:
    """Propose a revert only when the evidence names an exact commit range.

    ``anchor_id`` is the deployment the analysis is about. When it matches an event
    in the timeline that event is the one to revert, whatever was deployed after it.
    Only the incident path, which has no anchor, falls back to the newest deployment.
    """

    deployments = sorted(
        (
            e
            for e in timeline
            if e.kind is EvidenceKind.DEPLOYMENT and e.service == service
        ),
        key=lambda e: e.timestamp,
    )
    if not deployments:
        return None

    if anchor_id:
        index = next(
            (i for i, e in enumerate(deployments) if e.id == anchor_id),
            None,
        )
        if index is None:
            # The anchor is not in the evidence. Guessing from a later deployment
            # would name the wrong commit range, so propose no revert at all.
            return None
    else:
        index = len(deployments) - 1
    current = deployments[index]
    current_commit = _attribute(current, _COMMIT_KEYS)
    if not current_commit:
        return None

    last_good_commit = _attribute(current, _LAST_GOOD_KEYS)
    last_good_event = None
    if last_good_commit is None:
        # Only deployments that preceded the anchor can be "last known good".
        for candidate in reversed(deployments[:index]):
            commit = _attribute(candidate, _COMMIT_KEYS)
            if commit and commit != current_commit:
                last_good_commit, last_good_event = commit, candidate
                break
    if not last_good_commit:
        return None

    commit_range = f"{last_good_commit}..{current_commit}"
    evidence_refs = (current.id,) + (
        (last_good_event.id,) if last_good_event is not None else ()
    )
    return L2Proposal(
        kind="corrective-pr",
        title=f"Revert {service} in {environment} to last known-good commit {last_good_commit}",
        exact_action=(
            f"On the {service} repository default branch run "
            f"`git revert --no-commit {commit_range}`, commit the result on a branch named "
            f"`revert/{service}-{current_commit[:7]}`, and open a pull request that cites {subject}. "
            "Do not merge without service-owner review."
        ),
        rollback_path=(
            f"Close the revert pull request without merging. If it was already merged, revert the "
            f"revert commit and redeploy {current_commit}, which is the release the pipeline "
            "already produced."
        ),
        evidence_refs=evidence_refs,
    )


def _failure_class(hypotheses: Sequence[Hypothesis]) -> str | None:
    """Mirror the precedence in ``remediation/planner.py``: specific classes beat generic rollback."""

    for hypothesis in hypotheses:
        title = hypothesis.title.lower()
        if "crashloopbackoff" in title:
            return "crashloop"
        if "readiness regression" in title:
            return "readiness-regression"
        if "oomkilled" in title or "memory pressure" in title:
            return "oomkilled"
    for hypothesis in hypotheses:
        title = hypothesis.title.lower()
        if "deployment" in title and ("incident" in title or "failure" in title):
            return "deployment-regression"
    return None


def _runbook(
    hypotheses: Sequence[Hypothesis], *, service: str, environment: str, subject: str
) -> L2Proposal | None:
    failure_class = _failure_class(hypotheses)
    if failure_class is None:
        return None
    entry = ALLOW_LISTED_RUNBOOKS.get(failure_class)
    if entry is None:
        return None

    matched = next(
        (h for h in hypotheses if _failure_class((h,)) == failure_class),
        None,
    )
    evidence_refs = tuple(matched.evidence_ids) if matched is not None else ()
    rollback = (
        f"Run allow-listed runbook `{entry.rollback_runbook_id}` for {service} in {environment}."
        if entry.rollback_runbook_id
        else (
            f"The runbook is reversible by re-deploying the current revision of {service} in "
            f"{environment}; capture `kubectl rollout history` before running it so the prior "
            "revision is recoverable."
        )
    )
    return L2Proposal(
        kind="runbook",
        title=f"Allow-listed runbook `{entry.runbook_id}` for {service} in {environment}",
        exact_action=(
            f"A human operator runs allow-listed runbook `{entry.runbook_id}` "
            f"({entry.description}) against {service} in {environment}, citing {subject}. "
            "This platform does not run it: the runbook's live preconditions must be confirmed "
            "by the operator before execution."
        ),
        rollback_path=rollback,
        evidence_refs=evidence_refs,
    )


def _ticket(
    hypotheses: Sequence[Hypothesis],
    timeline: Sequence[EvidenceEvent],
    *,
    service: str,
    environment: str,
    subject: str,
) -> L2Proposal:
    evidence_refs = tuple(dict.fromkeys([e.id for e in timeline]))
    headline = (
        hypotheses[0].title
        if hypotheses
        else "no evidence-backed hypothesis was reached"
    )
    return L2Proposal(
        kind="ticket",
        title=f"Investigate {service} in {environment}: {headline}",
        exact_action=(
            f"Open an investigation ticket for {service} ({environment}) covering {subject}, "
            "attaching the evidence timeline and hypotheses from this analysis. No corrective "
            "change and no allow-listed runbook matched the evidence, so none is proposed."
        ),
        rollback_path=(
            "Not applicable: no change is proposed. Close the ticket if the evidence turns out "
            "to be a false signal."
        ),
        evidence_refs=evidence_refs,
    )
