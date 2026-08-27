import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from feedback.pr_guardian_shadow import build_shadow_report
from intelligence.risk import RiskAssessment, RiskFactor
from integrations.github.pr_guardian import (
    INSTALLATION_TOKEN_LOGIN,
    GitHubRestPRClient,
    PullRequestEvent,
)
from product.pr_guardian_shadow import closure_outcome, observation_from_assessment

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _observation(*, pr_number: int, sha: str, score: int, would_block: bool, repository: str):
    return observation_from_assessment(
        event=PullRequestEvent(repository, pr_number, sha, "synchronize"),
        assessment=RiskAssessment(
            score=score,
            band="critical" if score >= 75 else "moderate",
            blast_radius=("payments",),
            factors=(RiskFactor("security-boundary-change", 20, "identity controls changed"),),
        ),
        workflow_id=f"pr:{repository}:{pr_number}",
        changed_services=("payments",),
        would_require_extended_tests=True,
        would_require_additional_approval=would_block,
        would_block=would_block,
        audit_chain_verified=True,
        observed_at="2026-08-26T12:00:00+00:00",
    )


def _record(
    *,
    pr_number: int,
    score: int,
    would_block: bool,
    label: str | None,
    repository: str = "acme/platform",
):
    sha = f"{pr_number:08x}"
    labels = [] if label is None else [{"name": f"eip-pr-guardian/{label}"}]
    payload = {
        "action": "closed",
        "number": pr_number,
        "repository": {"full_name": repository},
        "pull_request": {"head": {"sha": sha}, "merged": True, "labels": labels},
    }
    return closure_outcome(
        payload=payload,
        observation=_observation(
            pr_number=pr_number,
            sha=sha,
            score=score,
            would_block=would_block,
            repository=repository,
        ),
        recorded_at="2026-08-26T12:30:00+00:00",
    )


def _promotion_ready_records():
    """30 joined records: precision 0.80, recall 1.00, 20 confirmed risks."""
    records = []
    number = 1
    for _ in range(20):
        records.append(_record(pr_number=number, score=90, would_block=True, label="confirmed-risk"))
        number += 1
    for _ in range(5):
        records.append(_record(pr_number=number, score=90, would_block=True, label="false-positive"))
        number += 1
    for _ in range(5):
        records.append(_record(pr_number=number, score=20, would_block=False, label="false-positive"))
        number += 1
    return records


def test_report_is_shadow_only_and_names_the_first_unmet_requirement():
    report = build_shadow_report([_record(pr_number=1, score=90, would_block=True, label="confirmed-risk")])
    readiness = report["promotion_readiness"]
    assert readiness["decision"] == "shadow-only"
    assert readiness["unmet_requirements"][0] == "minimum_joined_observations"
    assert "minimum_joined_observations" in readiness["next_review"]


def test_report_becomes_an_advisory_candidate_but_never_authorizes_blocking():
    report = build_shadow_report(_promotion_ready_records())
    readiness = report["promotion_readiness"]
    assert readiness["unmet_requirements"] == []
    assert readiness["decision"] == "advisory-candidate"
    assert readiness["blocking_authorized"] is False
    assert readiness["next_review"] == "human evidence review of the promotion packet"


def test_empty_input_reports_zero_records_without_fabricating_a_decision():
    report = build_shadow_report([])
    assert report["sample"]["closure_records"] == 0
    assert report["promotion_readiness"]["decision"] == "shadow-only"
    assert report["promotion_readiness"]["next_review"] == "no closure records yet"
    assert report["promotion_readiness"]["blocking_authorized"] is False


def test_calibration_section_is_a_recommendation_only():
    records = [
        _record(pr_number=1, score=90, would_block=True, label="confirmed-risk"),
        _record(pr_number=2, score=80, would_block=True, label="confirmed-risk"),
        _record(pr_number=3, score=70, would_block=True, label="false-positive"),
        _record(pr_number=4, score=20, would_block=False, label="false-positive"),
        _record(pr_number=5, score=30, would_block=False, label=None),
        _record(
            pr_number=6,
            score=60,
            would_block=True,
            label="confirmed-risk",
            repository="acme/checkout",
        ),
    ]
    calibration = build_shadow_report(records)["calibration"]
    assert calibration["applied"] is False
    assert calibration["note"] == (
        "Threshold changes are reviewed product decisions; this section is a recommendation only."
    )
    # The unreviewed record (pr 5) is excluded from every sample count.
    assert calibration["global"]["sample_size"] == 5
    assert 40 <= calibration["global"]["suggested_high_threshold"] <= 75
    assert set(calibration["per_service"]) == {"acme/platform", "acme/checkout"}
    assert calibration["per_service"]["acme/platform"]["sample_size"] == 4
    assert calibration["per_service"]["acme/checkout"]["sample_size"] == 1
    assert calibration["per_service"]["acme/checkout"]["suggested_high_threshold"] == 50
    assert calibration["per_service"]["acme/checkout"]["changed_from_default"] is False
    assert calibration["disposition_mapping"] == {
        "confirmed-risk": "failed",
        "false-positive": "not-failed",
    }
    # The section states which disposition the calibrator counts as a failure
    # sample, so a suggested threshold cannot be read in the wrong direction.
    assert calibration["failure_samples_from"] == "confirmed-risk"
    # pr 1, 2 and 6 are the confirmed risks; pr 5 is unreviewed and excluded.
    assert calibration["global"]["failed_samples"] == 3


def test_calibration_threshold_tracks_confirmed_risk_scores():
    """A confirmed risk is a failed sample: the threshold must land above the false positives.

    Twenty confirmed risks score 60 and ten false positives score 55, so the only
    threshold with both full recall and full precision is 60. Under the inverted
    mapping no threshold clears the precision floor and the calibrator would fall
    back to the default 50 with zero confirmed risks counted as failures.
    """
    records = []
    for number in range(1, 21):
        records.append(_record(pr_number=number, score=60, would_block=True, label="confirmed-risk"))
    for number in range(21, 31):
        records.append(_record(pr_number=number, score=55, would_block=True, label="false-positive"))
    calibration = build_shadow_report(records)["calibration"]
    assert calibration["global"]["sample_size"] == 30
    assert calibration["global"]["failed_samples"] == 20
    assert calibration["global"]["suggested_high_threshold"] == 60
    assert calibration["global"]["changed_from_default"] is True
    assert calibration["per_service"]["acme/platform"]["suggested_high_threshold"] == 60
    assert calibration["applied"] is False


def test_calibration_section_is_empty_without_reviewed_records():
    calibration = build_shadow_report([_record(pr_number=1, score=90, would_block=True, label=None)])["calibration"]
    assert calibration["global"]["sample_size"] == 0
    assert calibration["per_service"] == {}
    assert calibration["applied"] is False


def test_summarize_script_exits_zero_on_an_empty_input_set(tmp_path):
    empty = tmp_path / "outcomes"
    empty.mkdir()
    output = tmp_path / "pr-guardian-shadow-report.json"
    result = subprocess.run(
        [sys.executable, "scripts/summarize_pr_guardian_shadow.py", str(empty), "--output", str(output)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPOSITORY_ROOT), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sample"]["closure_records"] == 0
    assert report["promotion_readiness"]["decision"] == "shadow-only"
    assert report["promotion_readiness"]["next_review"] == "no closure records yet"


def test_installation_token_falls_back_to_the_actions_bot_login(monkeypatch):
    """A GitHub App installation token cannot call GET /user; 403 must not break the client."""
    requested: list[str] = []

    def fake_urlopen(request, timeout=None):
        requested.append(request.full_url)
        if request.full_url.endswith("/user"):
            raise urllib.error.HTTPError(
                request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message":"Resource not accessible"}')
            )
        body = json.dumps(
            [
                {"id": 1, "body": "<!-- eip-pr-guardian-shadow --> forged", "user": {"login": "attacker"}},
                {
                    "id": 2,
                    "body": "<!-- eip-pr-guardian-shadow --> authentic",
                    "user": {"login": INSTALLATION_TOKEN_LOGIN},
                },
            ]
        ).encode()

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return body

        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = GitHubRestPRClient("installation-token")
    assert client._authenticated_login() == INSTALLATION_TOKEN_LOGIN
    assert (
        client.latest_comment_with_marker(
            repository="acme/platform",
            pr_number=42,
            marker="<!-- eip-pr-guardian-shadow -->",
        )
        == "<!-- eip-pr-guardian-shadow --> authentic"
    )
    # The fallback is cached: GET /user is attempted exactly once.
    assert sum(1 for url in requested if url.endswith("/user")) == 1
