"""Advisory and selective-enforcement behaviour on the real PR path.

The evaluation job is never the gate: it always exits 0.  Only the trusted
publisher may turn a repository-owned enforcement decision into a failing check.
"""

from datetime import date

import pytest

from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import ChangedFile, PullRequestEvent
from intelligence.graph import ServiceGraph, ServiceNode
from product.architecture_review import DEFAULT_ARCHITECTURE_RULES
from product.pr_guardian.config import default_shadow_config, parse_repository_config
from product.pr_guardian.enforcement import KILL_SWITCH_ENV
from product.pr_guardian_service import PRGuardianService
from product.pr_guardian_shadow import validate_observation
from scripts.publish_pr_guardian_shadow import publish_observation
from scripts.run_pr_guardian import evaluate_pull_request
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


NOW = date(2026, 8, 26)
HIGH_RISK_FILES = [
    ChangedFile("infra/payments/main.tf", "modified", 40, 2),
    ChangedFile("services/payments/identity_auth.py", "modified", 60, 10),
]


class FakeGitHub:
    def __init__(self, files):
        self.files = list(files)
        self.checks = []
        self.comments = []
        self.sticky = []

    def list_changed_files(self, repository, pr_number):
        return list(self.files)

    def publish_check(self, **kwargs):
        self.checks.append(kwargs)

    def publish_comment(self, **kwargs):
        self.comments.append(kwargs)

    def publish_sticky_comment(self, **kwargs):
        self.sticky.append(kwargs)


class FakeContents:
    def __init__(self, contents):
        self.contents = dict(contents)
        self.requested = []

    def read_changed_file(self, path):
        self.requested.append(path)
        return self.contents.get(path)


def graph():
    g = ServiceGraph()
    g.add(ServiceNode(name="payments", tier=1, dependencies=("identity",)))
    g.add(ServiceNode(name="identity", tier=1))
    return g


def repository_config(mode, *, threshold=50, waivers=()):
    payload = {
        "mode": mode,
        "service_ids": ["payments"],
        "service_owners": ["octocat"],
        "policy_version": "pr-policy-2026-08",
    }
    if mode == "enforce":
        payload["enforcement"] = {
            "rule": "iac-change-without-test-evidence-at-high-risk",
            "threshold": threshold,
            "approved_by": "octocat",
            "approved_on": "2026-08-01",
            "expires_on": "2026-12-31",
            "waivers": list(waivers),
        }
    return parse_repository_config(payload, repository="acme/platform", now=NOW)


def build_service(tmp_path, config, files=HIGH_RISK_FILES, environ=None):
    github = FakeGitHub(files)
    audit = SqliteAuditLog(tmp_path / "audit.db")
    service = PRGuardianService(
        graph=graph(),
        github=github,
        workflows=ControlPlaneWorkflows(SqliteStateStore(tmp_path / "state.db"), audit),
        config=config,
        environ=environ if environ is not None else {},
    )
    return service, github, audit


def event():
    return PullRequestEvent("acme/platform", 42, "deadbeef", "opened")


def test_shadow_mode_publishing_is_unchanged(tmp_path):
    service, github, _ = build_service(tmp_path, default_shadow_config("acme/platform"))

    result = service.evaluate(event())

    assert result.mode == "shadow"
    assert github.checks[0]["name"] == "Engineering Intelligence / PR Guardian (shadow)"
    assert github.checks[0]["conclusion"] == "neutral"
    assert github.checks[0]["title"].startswith("Shadow risk:")
    assert result.enforcement.would_block is False


def test_advisory_mode_publishes_a_neutral_check_with_an_advisory_title(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("advisory"))

    result = service.evaluate(event())

    assert result.mode == "advisory"
    assert github.checks[0]["conclusion"] == "neutral"
    assert "Advisory" in github.checks[0]["title"]
    assert github.checks[0]["name"] == "Engineering Intelligence / PR Guardian (advisory)"


def test_enforce_mode_fails_the_check_only_when_the_rule_fires(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("enforce"))

    result = service.evaluate(event())

    assert result.enforcement.would_block is True
    assert result.conclusion == "failure"
    assert github.checks[0]["conclusion"] == "failure"


def test_enforce_mode_stays_neutral_when_the_rule_does_not_fire(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("enforce", threshold=99))

    result = service.evaluate(event())

    assert result.enforcement.would_block is False
    assert github.checks[0]["conclusion"] == "neutral"


def test_kill_switch_downgrades_an_enforcing_repository_to_neutral(tmp_path):
    service, github, _ = build_service(
        tmp_path, repository_config("enforce"), environ={KILL_SWITCH_ENV: "true"}
    )

    result = service.evaluate(event())

    assert result.enforcement.reason == "kill-switch"
    assert github.checks[0]["conclusion"] == "neutral"


def test_a_config_for_another_repository_is_refused(tmp_path):
    service, _, _ = build_service(tmp_path, repository_config("enforce"))

    with pytest.raises(ValueError, match="repository"):
        service.evaluate(PullRequestEvent("acme/other", 1, "abcd", "opened"))


def test_a_non_shadow_mode_cannot_come_from_a_flag_without_a_config(tmp_path):
    with pytest.raises(ValueError, match="repository configuration"):
        PRGuardianService(
            graph=graph(),
            github=FakeGitHub([]),
            workflows=ControlPlaneWorkflows(
                SqliteStateStore(tmp_path / "state.db"), SqliteAuditLog(tmp_path / "audit.db")
            ),
            mode="enforce",
        )


# --- observation transfer record ---------------------------------------------


def test_observation_carries_mode_enforcement_and_architecture(tmp_path):
    service, _, audit = build_service(tmp_path, repository_config("enforce"))
    contents = FakeContents({
        "infra/payments/main.tf": "public_network_access_enabled = true\n",
    })

    observation = evaluate_pull_request(
        event(), service=service, audit=audit, contents=contents, rules=DEFAULT_ARCHITECTURE_RULES
    )

    assert observation["mode"] == "enforce"
    assert observation["enforcement"]["would_block"] is True
    assert observation["enforcement"]["rule"] == "iac-change-without-test-evidence-at-high-risk"
    violations = observation["architecture"]["violations"]
    assert [item["path"] for item in violations] == ["infra/payments/main.tf"]
    assert observation["architecture"]["summary"]
    assert validate_observation(observation) == observation


def test_architecture_findings_never_change_the_check_conclusion(tmp_path):
    service, _, audit = build_service(tmp_path, repository_config("advisory"))
    contents = FakeContents({
        "infra/payments/main.tf": "public_network_access_enabled = true\n",
    })

    observation = evaluate_pull_request(
        event(), service=service, audit=audit, contents=contents
    )

    assert observation["architecture"]["violations"]
    assert observation["mode"] == "advisory"
    assert observation["enforcement"]["would_block"] is False


def test_a_legacy_observation_without_the_new_sections_still_validates():
    legacy = {
        "schema_version": 1,
        "kind": "pr-guardian-shadow-observation",
        "mode": "shadow",
        "observed_at": "2026-08-26T12:00:00+00:00",
        "subject": {
            "repository": "acme/platform",
            "pr_number": 42,
            "head_sha": "deadbeef",
            "action": "synchronize",
        },
        "assessment": {"score": 10, "band": "low", "factors": []},
        "changed_services": [],
        "simulated_policy": {
            "would_require_extended_tests": False,
            "would_require_additional_approval": False,
            "would_block": False,
        },
        "workflow": {"id": "pr:acme/platform:42", "audit_chain_verified": True},
    }

    normalized = validate_observation(legacy)

    assert normalized["enforcement"] == {
        "would_block": False,
        "reason": "mode-not-enforcing",
        "rule": None,
        "waived_by": None,
    }
    assert normalized["architecture"]["violations"] == []


# --- trusted publisher -------------------------------------------------------


class FakePublisherClient:
    def __init__(self):
        self.checks = []
        self.comments = []

    def publish_check(self, **kwargs):
        self.checks.append(kwargs)

    def publish_sticky_comment(self, **kwargs):
        self.comments.append(kwargs)


def enforcing_observation(tmp_path, contents=None):
    service, _, audit = build_service(tmp_path, repository_config("enforce"))
    return evaluate_pull_request(
        event(),
        service=service,
        audit=audit,
        contents=contents or FakeContents({}),
    )


def test_publisher_fails_the_check_when_the_trusted_config_agrees(tmp_path):
    observation = enforcing_observation(tmp_path)
    client = FakePublisherClient()

    conclusion = publish_observation(
        observation,
        config=repository_config("enforce"),
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
    )

    assert conclusion == "failure"
    assert client.checks[0]["conclusion"] == "failure"


def test_publisher_refuses_to_fail_when_the_trusted_config_is_only_advisory(tmp_path):
    observation = enforcing_observation(tmp_path)
    client = FakePublisherClient()

    conclusion = publish_observation(
        observation,
        config=repository_config("advisory"),
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
    )

    assert conclusion == "neutral"
    assert client.checks[0]["conclusion"] == "neutral"
    assert "not enforcing" in client.comments[0]["body"].lower()


def test_publisher_renders_architecture_findings_into_the_sticky_comment(tmp_path):
    observation = enforcing_observation(
        tmp_path,
        contents=FakeContents({"infra/payments/main.tf": "public_network_access_enabled = true\n"}),
    )
    client = FakePublisherClient()

    publish_observation(
        observation,
        config=repository_config("enforce"),
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
    )

    body = client.comments[0]["body"]
    assert "eip-architecture-guard" in body
    assert "public_network_access_enabled = true" in body


def test_publisher_refuses_an_observation_for_another_repository(tmp_path):
    observation = enforcing_observation(tmp_path)

    with pytest.raises(RuntimeError, match="repository"):
        publish_observation(
            observation,
            config=repository_config("enforce"),
            repository="acme/other",
            client=FakePublisherClient(),
            environ={},
            now=NOW,
        )


def test_published_check_identity_follows_the_trusted_config_not_the_artifact(tmp_path):
    observation = enforcing_observation(tmp_path)
    client = FakePublisherClient()

    publish_observation(
        observation,
        config=repository_config("advisory"),
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
    )

    assert client.checks[0]["name"] == "Engineering Intelligence / PR Guardian (advisory)"
    assert "Advisory" in client.checks[0]["title"]
