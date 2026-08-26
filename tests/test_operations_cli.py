"""The two operational-intelligence CLIs: same composition as the API, no execution."""
import json

import pytest

from operations_fixtures import ADO_FAILED_RUN, COMMON_ALERT, write_evidence_fixture, write_payload
from scripts import correlate_incident, investigate_deployment_failure


class RecordingGitHubClient:
    def __init__(self):
        self.issues = []

    def publish_check(self, **kwargs):  # pragma: no cover - not used by these CLIs
        raise AssertionError("operations CLIs do not publish checks")

    def publish_sticky_comment(self, **kwargs):  # pragma: no cover - not used by these CLIs
        raise AssertionError("operations CLIs do not publish PR comments")

    def ensure_maintenance_issue(self, *, repository, marker, title, body, labels=()):
        self.issues.append({"repository": repository, "marker": marker, "title": title, "body": body})
        return 101


def _base_argv(tmp_path, payload_name, payload):
    fixture = write_evidence_fixture(tmp_path)
    path = write_payload(tmp_path, payload_name, payload)
    return [
        "--payload",
        str(path),
        "--evidence",
        f"fixture:{fixture}",
        "--state-dir",
        str(tmp_path / "state"),
    ]


def test_deployment_cli_prints_analysis_and_proposals_as_json(tmp_path, capsys):
    exit_code = investigate_deployment_failure.main(
        _base_argv(tmp_path, "ado.json", ADO_FAILED_RUN)
    )
    assert exit_code == 0

    report = json.loads(capsys.readouterr().out)
    assert report["workflow_id"] == "deployment-failure:ado:Platform:7:42"
    assert report["analysis"]["deployment_id"] == "ado:Platform:7:42"
    assert report["proposals"]
    assert all(p["requires_human"] is True for p in report["proposals"])
    assert report["executed"] is False


def test_incident_cli_prints_analysis_and_proposals_as_json(tmp_path, capsys):
    exit_code = correlate_incident.main(_base_argv(tmp_path, "alert.json", COMMON_ALERT))
    assert exit_code == 0

    report = json.loads(capsys.readouterr().out)
    assert report["workflow_id"] == "incident:INC-42"
    assert report["service"] == "payments"
    assert report["proposals"]
    assert all(p["requires_human"] is True for p in report["proposals"])


@pytest.mark.parametrize(
    "module,payload_name,payload",
    [
        (investigate_deployment_failure, "ado.json", ADO_FAILED_RUN),
        (correlate_incident, "alert.json", COMMON_ALERT),
    ],
)
def test_publish_github_without_a_token_fails_closed(
    monkeypatch, tmp_path, module, payload_name, payload
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    argv = _base_argv(tmp_path, payload_name, payload) + [
        "--publish",
        "github",
        "--repository",
        "acme/platform",
    ]
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        module.main(argv)


@pytest.mark.parametrize(
    "module,payload_name,payload",
    [
        (investigate_deployment_failure, "ado.json", ADO_FAILED_RUN),
        (correlate_incident, "alert.json", COMMON_ALERT),
    ],
)
def test_publish_github_opens_a_marked_issue_carrying_the_proposals(
    monkeypatch, tmp_path, capsys, module, payload_name, payload
):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    client = RecordingGitHubClient()
    monkeypatch.setattr(module, "_github_client", lambda token: client)

    argv = _base_argv(tmp_path, payload_name, payload) + [
        "--publish",
        "github",
        "--repository",
        "acme/platform",
    ]
    assert module.main(argv) == 0
    capsys.readouterr()

    assert len(client.issues) == 1
    issue = client.issues[0]
    assert issue["repository"] == "acme/platform"
    assert issue["marker"].startswith("<!-- eip-")
    assert "requires human execution" in issue["body"].lower()
