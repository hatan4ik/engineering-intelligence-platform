"""Advisory and selective-enforcement behaviour on the real PR path.

The evaluation job is never the gate: it always exits 0.  Only the trusted
publisher may turn a repository-owned enforcement decision into a failing check.
"""

import json
from datetime import date

import pytest

from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import ChangedFile, PullRequestEvent
from intelligence.graph import ServiceGraph, ServiceNode
from product.architecture_review import DEFAULT_ARCHITECTURE_RULES, FileContent
from product.pr_guardian.config import default_shadow_config, parse_repository_config
from product.pr_guardian.enforcement import KILL_SWITCH_ENV
from product.pr_guardian_service import PRGuardianService
from product.pr_guardian_shadow import validate_observation
from scripts.publish_pr_guardian_shadow import (
    UntrustedEvaluation,
    publish_observation,
    publish_untrusted_evaluation,
    trusted_observation,
)
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
    def __init__(self, contents, skips=()):
        self.contents = dict(contents)
        self.skips = dict(skips)
        self.requested = []

    def read_changed_file(self, path):
        self.requested.append(path)
        if path in self.contents:
            return FileContent.available(self.contents[path])
        return FileContent.unavailable(self.skips.get(path, "content unavailable"))


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

    result = service.evaluate(event(), now=NOW)

    assert result.mode == "shadow"
    assert github.checks[0]["name"] == "Engineering Intelligence / PR Guardian (shadow)"
    assert github.checks[0]["conclusion"] == "neutral"
    assert github.checks[0]["title"].startswith("Shadow risk:")
    assert result.enforcement.would_block is False


def test_advisory_mode_publishes_a_neutral_check_with_an_advisory_title(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("advisory"))

    result = service.evaluate(event(), now=NOW)

    assert result.mode == "advisory"
    assert github.checks[0]["conclusion"] == "neutral"
    assert "Advisory" in github.checks[0]["title"]
    assert github.checks[0]["name"] == "Engineering Intelligence / PR Guardian (advisory)"


def test_enforce_mode_fails_the_check_only_when_the_rule_fires(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("enforce"))

    result = service.evaluate(event(), now=NOW)

    assert result.enforcement.would_block is True
    assert result.conclusion == "failure"
    assert github.checks[0]["conclusion"] == "failure"


def test_enforce_mode_stays_neutral_when_the_rule_does_not_fire(tmp_path):
    service, github, _ = build_service(tmp_path, repository_config("enforce", threshold=99))

    result = service.evaluate(event(), now=NOW)

    assert result.enforcement.would_block is False
    assert github.checks[0]["conclusion"] == "neutral"


def test_kill_switch_downgrades_an_enforcing_repository_to_neutral(tmp_path):
    service, github, _ = build_service(
        tmp_path, repository_config("enforce"), environ={KILL_SWITCH_ENV: "true"}
    )

    result = service.evaluate(event(), now=NOW)

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
        event(),
        service=service,
        audit=audit,
        contents=contents,
        rules=DEFAULT_ARCHITECTURE_RULES,
        now=NOW,
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
        event(), service=service, audit=audit, contents=contents, now=NOW
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
        now=NOW,
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


# --- one rendering path: the comment states this mode's real authority -------


def comment_body(tmp_path, config, **kwargs):
    service, github, _ = build_service(tmp_path, config, **kwargs)
    service.evaluate(event(), now=NOW)
    return github.comments[0]["body"]


def test_shadow_comment_wording_is_unchanged(tmp_path):
    body = comment_body(tmp_path, default_shadow_config("acme/platform"))

    assert "## Engineering Intelligence — PR Guardian shadow observation" in body
    assert (
        "**Advisory only.** This result cannot approve, block, or otherwise change merge status."
        in body
    )
    assert "### Simulated policy" in body


def test_advisory_comment_states_a_non_blocking_certified_scope(tmp_path):
    body = comment_body(tmp_path, repository_config("advisory"))

    assert "Advisory — non-blocking check for this repository's certified scope" in body
    assert "does not change merge status" in body
    assert "cannot approve, block" not in body


def test_enforce_comment_names_the_rule_and_says_it_would_block(tmp_path):
    body = comment_body(tmp_path, repository_config("enforce"))

    assert "## Engineering Intelligence — PR Guardian enforcement check" in body
    assert "iac-change-without-test-evidence-at-high-risk" in body
    assert "would block this pull request" in body
    assert "cannot approve, block, or otherwise change merge status" not in body


def test_enforce_comment_says_it_does_not_block_when_the_rule_did_not_fire(tmp_path):
    body = comment_body(tmp_path, repository_config("enforce", threshold=99))

    assert "does not block this pull request" in body
    assert "the enforcement rule's condition was not met" in body
    assert "cannot approve, block, or otherwise change merge status" not in body


def test_enforce_comment_names_the_owner_who_waived_the_change(tmp_path):
    waived = repository_config("enforce", waivers=[{
        "path_glob": "infra/*",
        "reason": "Frozen legacy stack; owner accepts the risk until Q4.",
        "owner": "octocat",
        "expires_on": "2026-10-01",
    }])

    body = comment_body(tmp_path, waived)

    assert "Waiver applied by:** `octocat`" in body
    assert "does not block this pull request" in body


def test_publisher_comment_discloses_the_conclusion_it_actually_published(tmp_path):
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

    body = client.comments[0]["body"]
    assert "**Published check conclusion:** `neutral`" in body
    assert "the trusted repository configuration is not enforcing this pull request" in body


# --- Architecture Guard must not claim a clean review it never performed -----


def test_architecture_section_carries_reviewed_and_skipped_counts(tmp_path):
    service, _, audit = build_service(tmp_path, repository_config("advisory"))
    contents = FakeContents(
        {"infra/payments/main.tf": "public_network_access_enabled = true\n"},
        skips={"services/payments/identity_auth.py": "too-large"},
    )

    observation = evaluate_pull_request(
        event(), service=service, audit=audit, contents=contents, now=NOW
    )

    architecture = observation["architecture"]
    assert architecture["reviewed"] == 1
    assert architecture["skipped"] == [
        {"path": "services/payments/identity_auth.py", "reason": "too-large"}
    ]
    assert "1 file(s) could not be reviewed" in architecture["summary"]


def test_architecture_summary_says_it_did_not_run_when_nothing_was_reviewed(tmp_path):
    service, _, audit = build_service(tmp_path, repository_config("advisory"))

    observation = evaluate_pull_request(
        event(), service=service, audit=audit, contents=FakeContents({}), now=NOW
    )

    architecture = observation["architecture"]
    assert architecture["reviewed"] == 0
    assert architecture["violations"] == []
    summary = architecture["summary"]
    assert "did not run" in summary
    assert "No architecture policy violations detected" not in summary


def test_architecture_says_nothing_was_in_scope_when_no_rule_matched(tmp_path):
    service, _, audit = build_service(
        tmp_path, repository_config("advisory"), files=[ChangedFile("README.md", "modified", 1, 1)]
    )

    observation = evaluate_pull_request(
        event(), service=service, audit=audit, contents=FakeContents({}), now=NOW
    )

    architecture = observation["architecture"]
    assert architecture["reviewed"] == 0
    assert architecture["skipped"] == []
    assert "in scope" in architecture["summary"]


def test_the_rendered_comment_never_claims_a_clean_review_that_did_not_happen(tmp_path):
    observation = enforcing_observation(tmp_path)
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
    assert "Architecture Guard did not run" in body
    assert "No architecture policy violations detected" not in body


# --- an untrusted or absent artifact must still publish something honest -----


def write_artifact(tmp_path, payload):
    path = tmp_path / "pr-guardian-shadow-result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("make_payload", "fragment"),
    [
        (lambda o: "not json at all", "could not be parsed"),
        (lambda o: [1, 2, 3], "not a JSON object"),
        (lambda o: {"kind": "something-else"}, "did not validate"),
        (lambda o: {**o, "subject": {**o["subject"], "repository": "acme/other"}}, "repository"),
    ],
)
def test_an_untrusted_artifact_is_refused_with_a_reason(tmp_path, make_payload, fragment):
    good = enforcing_observation(tmp_path)
    payload = make_payload(good)
    path = tmp_path / "pr-guardian-shadow-result.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        write_artifact(tmp_path, payload)

    with pytest.raises(UntrustedEvaluation, match=fragment):
        trusted_observation(path, repository="acme/platform", head_sha="deadbeef")


def test_a_missing_artifact_is_refused_with_a_reason(tmp_path):
    with pytest.raises(UntrustedEvaluation, match="no evaluation artifact"):
        trusted_observation(
            tmp_path / "absent.json", repository="acme/platform", head_sha="deadbeef"
        )


def test_a_head_sha_that_does_not_match_the_workflow_run_is_refused(tmp_path):
    good = enforcing_observation(tmp_path)
    path = write_artifact(tmp_path, good)

    with pytest.raises(UntrustedEvaluation, match="head SHA"):
        trusted_observation(path, repository="acme/platform", head_sha="feedface")


def test_an_untrusted_evaluation_publishes_a_neutral_check_that_says_so():
    client = FakePublisherClient()

    conclusion = publish_untrusted_evaluation(
        repository="acme/platform",
        head_sha="deadbeef",
        pr_number=42,
        client=client,
        mode="enforce",
        reason="no evaluation artifact was produced",
    )

    assert conclusion == "neutral"
    assert client.checks[0]["conclusion"] == "neutral"
    assert "could not be trusted" in client.checks[0]["summary"]
    assert "no evaluation artifact was produced" in client.checks[0]["summary"]
    assert "could not be trusted" in client.comments[0]["body"]


def test_an_untrusted_evaluation_publishes_the_check_even_without_a_pr_number():
    client = FakePublisherClient()

    publish_untrusted_evaluation(
        repository="acme/platform",
        head_sha="deadbeef",
        pr_number=None,
        client=client,
        mode="shadow",
        reason="the artifact did not validate",
    )

    assert client.checks and not client.comments


# --- an unreadable repository configuration must lapse, not crash -----------


def test_an_unreadable_repository_config_publishes_neutral_and_discloses_it(tmp_path):
    observation = enforcing_observation(tmp_path)
    client = FakePublisherClient()

    conclusion = publish_observation(
        observation,
        config=default_shadow_config("acme/platform"),
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
        config_error="enforcement.expires_on (2026-01-01) has passed",
    )

    assert conclusion == "neutral"
    assert "expires_on" in client.comments[0]["body"]


def test_a_lapsed_owner_approval_publishes_neutral_rather_than_failing_the_run(tmp_path):
    observation = enforcing_observation(tmp_path)
    lapsed = parse_repository_config(
        {
            "mode": "enforce",
            "service_ids": ["payments"],
            "service_owners": ["octocat"],
            "policy_version": "pr-policy-2026-08",
            "enforcement": {
                "rule": "iac-change-without-test-evidence-at-high-risk",
                "threshold": 50,
                "approved_by": "octocat",
                "approved_on": "2026-08-01",
                "expires_on": "2026-08-25",
            },
        },
        repository="acme/platform",
        now=NOW,
        require_unexpired=False,
    )
    client = FakePublisherClient()

    conclusion = publish_observation(
        observation,
        config=lapsed,
        repository="acme/platform",
        client=client,
        environ={},
        now=NOW,
    )

    assert conclusion == "neutral"
    assert "approval for enforcement has expired" in client.comments[0]["body"]
