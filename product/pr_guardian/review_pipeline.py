"""Preparation stage for the PR Guardian review use case.

This module owns the read-only work that turns a GitHub pull-request event
into deterministic risk inputs.  It deliberately does not persist, publish,
or decide enforcement: those are distinct responsibilities of the use case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from company_brain.model import BrainPrincipal
from intelligence.extractors import service_from_path
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision, policy_for
from intelligence.risk import ChangeContext, RiskAssessment, assess_change
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent

from .company_brain import PRGuardianCompanyContext
from .enforcement import (
    is_delivery_control_path,
    is_docs_path,
    is_iac_path,
    is_security_boundary_path,
    is_test_path,
)


class HistoricalFailureProvider(Protocol):
    """Read-only source of similar failed changes for deterministic scoring."""

    def similar_failed_changes(self, *, repository: str, filenames: tuple[str, ...]) -> int: ...


class QualifiedCompanyContextProvider(Protocol):
    """Read-only, qualified Company Brain context used by the PR product."""

    def known_services(self, *, repository: str, principal: BrainPrincipal) -> tuple[str, ...]: ...

    def context_for(
        self,
        *,
        repository: str,
        changed_services: tuple[str, ...],
        principal: BrainPrincipal,
    ) -> PRGuardianCompanyContext: ...


@dataclass(frozen=True)
class PreparedPRReview:
    """The deterministic inputs and result of the read-only review stage."""

    event: PullRequestEvent
    filenames: tuple[str, ...]
    assessment: RiskAssessment
    simulated_policy: PRPolicyDecision
    changed_services: tuple[str, ...]
    company_context: PRGuardianCompanyContext | None
    primary_service: str


class PRReviewPreparer:
    """Collect, qualify, and score one pull-request change without side effects."""

    def __init__(
        self,
        *,
        graph: ServiceGraph | None,
        github: GitHubPRClient,
        history: HistoricalFailureProvider | None = None,
        company_context: QualifiedCompanyContextProvider | None = None,
        principal: BrainPrincipal | None = None,
    ) -> None:
        self._graph = graph
        self._github = github
        self._history = history
        self._company_context = company_context
        self._principal = principal

    def prepare(self, event: PullRequestEvent) -> PreparedPRReview:
        """Build an assessment and simulated policy from authorized context."""

        files = self._github.list_changed_files(event.repository, event.number)
        filenames = tuple(item.filename for item in files)
        known_services = self._known_services(event.repository)
        candidate_changed_services = tuple(
            sorted(
                {
                    service
                    for path in filenames
                    if (service := service_from_path(path, known_services)) is not None
                }
            )
        )
        company_context = self._qualified_context(
            repository=event.repository,
            changed_services=candidate_changed_services,
        )
        graph = company_context.graph if company_context is not None else self._graph
        if graph is None:  # Guarded by construction; makes static safety explicit.
            raise RuntimeError("PR Guardian graph is unavailable")
        changed_services = (
            company_context.changed_services
            if company_context is not None
            else candidate_changed_services
        )
        test_files = [path for path in filenames if is_test_path(path)]
        source_files = [
            path for path in filenames if not is_test_path(path) and not is_docs_path(path)
        ]
        assessment = assess_change(
            graph,
            ChangeContext(
                changed_services=changed_services,
                files_changed=len(files),
                touches_iac=any(is_iac_path(path) for path in filenames),
                touches_identity_or_security=any(
                    is_security_boundary_path(path) for path in filenames
                ),
                touches_delivery_pipeline=any(
                    is_delivery_control_path(path) for path in filenames
                ),
                unmapped_service_change=bool(source_files)
                and (
                    not candidate_changed_services
                    or (company_context is not None and not company_context.qualified)
                ),
                weak_test_evidence=bool(source_files) and not test_files,
                similar_failed_changes=(
                    self._history.similar_failed_changes(
                        repository=event.repository,
                        filenames=filenames,
                    )
                    if self._history is not None
                    else 0
                ),
            ),
        )
        simulated_policy = policy_for(assessment)
        # An unqualified world-model context may surface a risk observation,
        # but it cannot simulate a control.
        if company_context is not None and not company_context.qualified:
            simulated_policy = PRPolicyDecision(False, False, False)
        return PreparedPRReview(
            event=event,
            filenames=filenames,
            assessment=assessment,
            simulated_policy=simulated_policy,
            changed_services=changed_services,
            company_context=company_context,
            primary_service=changed_services[0] if changed_services else "unknown",
        )

    def _known_services(self, repository: str) -> set[str]:
        if self._company_context is not None and self._principal is not None:
            return set(
                self._company_context.known_services(
                    repository=repository,
                    principal=self._principal,
                )
            )
        return set(self._graph.nodes if self._graph is not None else ())

    def _qualified_context(
        self,
        *,
        repository: str,
        changed_services: tuple[str, ...],
    ) -> PRGuardianCompanyContext | None:
        if self._company_context is None or self._principal is None:
            return None
        return self._company_context.context_for(
            repository=repository,
            changed_services=changed_services,
            principal=self._principal,
        )
