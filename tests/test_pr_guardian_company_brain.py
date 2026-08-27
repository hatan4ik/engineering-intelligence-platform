import asyncio
from datetime import datetime, timedelta, timezone

from company_brain import (
    BrainEntity,
    BrainEvidence,
    BrainPrincipal,
    BrainProvenance,
    CompanyBrainWorldModel,
    EntityKind,
    RelationshipKind,
    SqliteCompanyBrainStore,
)
from company_brain.model import BrainRelationship
from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import ChangedFile, PullRequestEvent
from product.pr_guardian.company_brain import PRGuardianWorldModelAdapter
from product.pr_guardian.contracts import FindingAction
from product.pr_guardian.store import PRGuardianStoreError, SqlitePRGuardianStore
from product.pr_guardian_service import PRGuardianService
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


TENANT = "tenant-acme"


class FakeGitHub:
    def __init__(self, files: list[ChangedFile]) -> None:
        self.files = files
        self.checks: list[dict[str, object]] = []
        self.comments: list[dict[str, object]] = []

    def list_changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        return self.files

    def publish_check(self, **kwargs: object) -> None:
        self.checks.append(kwargs)

    def publish_comment(self, **kwargs: object) -> None:
        self.comments.append(kwargs)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _provenance(record_id: str, observed_at: datetime) -> BrainProvenance:
    return BrainProvenance(
        source_system="github",
        source_record_id=record_id,
        source_revision="1",
        observed_at=observed_at,
        event_id=f"event:{record_id}:{int(observed_at.timestamp())}",
    )


def _seed(store: SqliteCompanyBrainStore, *, observed_at: datetime) -> None:
    def entity(entity_id: str, kind: EntityKind, label: str, attributes: tuple[tuple[str, str], ...] = ()) -> None:
        store.put_entity(
            TENANT,
            BrainEntity(entity_id, kind, label, attributes),
            provenance=_provenance(entity_id, observed_at),
        )

    def evidence(evidence_id: str, kind: str = "repository-change") -> None:
        store.put_evidence(
            TENANT,
            BrainEvidence(
                evidence_id=evidence_id,
                source_kind=kind,
                citation=f"knowledge://{evidence_id}",
                revision="1",
                acl_groups=("engineering",),
            ),
            provenance=_provenance(evidence_id, observed_at),
        )

    def relate(source: str, target: str, kind: RelationshipKind, evidence_id: str) -> None:
        relationship = BrainRelationship(source, target, kind, (evidence_id,))
        store.put_relationship(
            TENANT,
            relationship,
            provenance=_provenance(f"{source}:{kind.value}:{target}", observed_at),
        )

    entity("repository:github:acme/platform", EntityKind.REPOSITORY, "acme/platform")
    entity("service:payments", EntityKind.SERVICE, "payments", (("tier", "1"),))
    entity("service:checkout", EntityKind.SERVICE, "checkout", (("tier", "2"),))
    entity("owner:payments", EntityKind.OWNER, "team-payments")
    evidence("evidence:membership")
    evidence("evidence:dependency")
    evidence("evidence:owner", "adr")
    relate("service:payments", "repository:github:acme/platform", RelationshipKind.BELONGS_TO, "evidence:membership")
    relate("service:checkout", "repository:github:acme/platform", RelationshipKind.BELONGS_TO, "evidence:membership")
    relate("service:checkout", "service:payments", RelationshipKind.DEPENDS_ON, "evidence:dependency")
    relate("owner:payments", "service:payments", RelationshipKind.OWNS, "evidence:owner")


def _adapter(store: SqliteCompanyBrainStore) -> PRGuardianWorldModelAdapter:
    return PRGuardianWorldModelAdapter(CompanyBrainWorldModel(store, TENANT))


def test_world_model_adapter_builds_a_qualified_graph_and_context_fingerprint(tmp_path):
    store = SqliteCompanyBrainStore(tmp_path / "brain.db")
    _seed(store, observed_at=_now())
    adapter = _adapter(store)
    principal = BrainPrincipal(groups=("engineering",))

    context = adapter.context_for(
        repository="acme/platform",
        changed_services=("payments",),
        principal=principal,
    )

    assert adapter.known_services(repository="acme/platform", principal=principal) == ("checkout", "payments")
    assert context.qualified is True
    assert context.changed_services == ("payments",)
    assert context.blast_radius == ("checkout", "payments")
    assert context.graph.nodes["checkout"].dependencies == ("payments",)
    assert context.context_version.startswith("world-model:v1:")
    assert context.evidence.references[0].authorized is True


def test_pr_guardian_persists_qualified_finding_and_neutralizes_unqualified_context(tmp_path):
    brain = SqliteCompanyBrainStore(tmp_path / "brain.db")
    findings = SqlitePRGuardianStore(tmp_path / "findings.db")
    _seed(brain, observed_at=_now())
    github = FakeGitHub(
        [
            ChangedFile("services/payments/auth.py", "modified", 20, 1),
            ChangedFile("infra/payments/rbac.tf", "modified", 10, 1),
        ]
    )
    service = PRGuardianService(
        graph=None,
        github=github,
        workflows=ControlPlaneWorkflows(
            SqliteStateStore(tmp_path / "state.db"), SqliteAuditLog(tmp_path / "audit.db")
        ),
        company_context=_adapter(brain),
        principal=BrainPrincipal(groups=("engineering",)),
        findings=findings,
        policy_version="pr-policy-test",
    )

    result = asyncio.run(service.evaluate(PullRequestEvent("acme/platform", 7, "deadbeef", "opened")))

    assert result.company_context is not None and result.company_context.qualified is True
    assert result.finding is not None
    assert result.finding.context_qualified is True
    assert result.finding.simulated_action is FindingAction.ADDITIONAL_APPROVAL
    assert findings.finding(result.finding.finding_id) == result.finding
    assert result.would_block is False

    stale_brain = SqliteCompanyBrainStore(tmp_path / "stale-brain.db")
    _seed(stale_brain, observed_at=_now() - timedelta(days=46))
    neutral = PRGuardianService(
        graph=None,
        github=github,
        workflows=ControlPlaneWorkflows(
            SqliteStateStore(tmp_path / "stale-state.db"), SqliteAuditLog(tmp_path / "stale-audit.db")
        ),
        company_context=_adapter(stale_brain),
        principal=BrainPrincipal(groups=("engineering",)),
        findings=findings,
        policy_version="pr-policy-test",
    )

    unqualified = asyncio.run(neutral.evaluate(PullRequestEvent("acme/platform", 8, "feedface", "opened")))

    assert unqualified.company_context is not None and unqualified.company_context.qualified is False
    assert unqualified.finding is not None
    assert unqualified.finding.context_qualified is False
    assert unqualified.finding.simulated_action is FindingAction.NONE
    assert unqualified.would_block is False
    assert "insufficient for a simulated control" in github.comments[-1]["body"]


def test_durable_finding_and_outcome_records_are_idempotent_and_immutable(tmp_path):
    brain = SqliteCompanyBrainStore(tmp_path / "brain.db")
    _seed(brain, observed_at=_now())
    context = _adapter(brain).context_for(
        repository="acme/platform",
        changed_services=("payments",),
        principal=BrainPrincipal(groups=("engineering",)),
    )
    from product.pr_guardian.contracts import FindingOutcome, PRFinding, ReviewerRiskDisposition, ReviewerUtilityDisposition

    finding = PRFinding(
        finding_id="pr:acme/platform:1:deadbeef:risk",
        repository="acme/platform",
        pr_number=1,
        head_sha="deadbeef",
        severity="high",
        summary="A qualified finding.",
        correlation_id="corr-1",
        policy_version="pr-policy-test",
        context_version=context.context_version,
        context_qualified=True,
        simulated_action=FindingAction.ADDITIONAL_APPROVAL,
        evidence=context.evidence,
    )
    store = SqlitePRGuardianStore(tmp_path / "findings.db")

    assert store.record_finding(finding) is True
    assert store.record_finding(finding) is False
    outcome = FindingOutcome(
        finding_id=finding.finding_id,
        reviewer_risk=ReviewerRiskDisposition.CONFIRMED_RISK,
        reviewer_utility=ReviewerUtilityDisposition.USEFUL,
        recorded_by="reviewer:alice",
    )
    assert store.record_outcome(outcome) is True
    assert store.record_outcome(outcome) is False
    assert store.outcomes_for_finding(finding.finding_id) == (outcome,)

    conflicting = PRFinding(
        **{**finding.__dict__, "summary": "A conflicting rewrite."},
    )
    try:
        store.record_finding(conflicting)
    except PRGuardianStoreError:
        pass
    else:
        raise AssertionError("immutable finding conflict was accepted")
