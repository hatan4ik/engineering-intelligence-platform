"""Recorded HTTP contract tests for GitHubRestPRClient.

Verifies schema conformance for pull request file diffs, check-run creation,
sticky comment lifecycle, and resilient error classification.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from integrations.github.pr_guardian import (
    COMMENT_MARKER,
    ChangedFile,
    GitHubAPIError,
    GitHubRestPRClient,
)
from resilience.dependencies import DependencyBoundary, DependencyLimits


def _mock_http_response(status: int = 200, payload: object = None) -> MagicMock:
    response = MagicMock()
    response.status = status
    data = json.dumps(payload or {}).encode("utf-8")
    response.read.return_value = data
    response.__enter__.return_value = response
    return response


def test_contract_list_changed_files_parses_github_diff_payload() -> None:
    recorded_diff_payload = [
        {
            "sha": "bbcd538c8e72b8c175046e27cc8f9070763a5680",
            "filename": "infra/terraform/main.tf",
            "status": "modified",
            "additions": 42,
            "deletions": 7,
            "changes": 49,
            "blob_url": "https://github.com/octocat/Hello-World/blob/6dcb09b5b57875f334f61aebed695e2e4193db5e/file1.txt",
            "raw_url": "https://github.com/octocat/Hello-World/raw/6dcb09b5b57875f334f61aebed695e2e4193db5e/file1.txt",
            "contents_url": "https://api.github.com/repos/octocat/Hello-World/contents/file1.txt?ref=6dcb09b5b57875f334f61aebed695e2e4193db5e",
            "patch": "@@ -132,7 +132,7 @@ module \"network\" {",
        },
        {
            "sha": "bba3523c8e72b8c175046e27cc8f9070763a5681",
            "filename": "docs/architecture.md",
            "status": "added",
            "additions": 15,
            "deletions": 0,
            "changes": 15,
        },
    ]

    client = GitHubRestPRClient(token="ghp_test_token")
    with patch("urllib.request.urlopen", return_value=_mock_http_response(200, recorded_diff_payload)):
        files = client.list_changed_files("acme/payments", 42)

    assert len(files) == 2
    assert files[0] == ChangedFile(
        filename="infra/terraform/main.tf",
        status="modified",
        additions=42,
        deletions=7,
    )
    assert files[1] == ChangedFile(
        filename="docs/architecture.md",
        status="added",
        additions=15,
        deletions=0,
    )


def test_contract_publish_check_formats_github_check_runs_schema() -> None:
    client = GitHubRestPRClient(token="ghp_test_token")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_http_response(201, {"id": 12345})
        client.publish_check(
            repository="acme/payments",
            head_sha="deadbeef42",
            name="PR Guardian (shadow)",
            conclusion="neutral",
            title="Risk Assessment Complete",
            summary="Identified low risk change with zero blockers.",
        )

        assert mock_urlopen.call_count == 1
        request = mock_urlopen.call_args[0][0]
        assert request.get_method() == "POST"
        assert request.full_url == "https://api.github.com/repos/acme/payments/check-runs"

        sent_payload = json.loads(request.data.decode("utf-8"))
        assert sent_payload["name"] == "PR Guardian (shadow)"
        assert sent_payload["head_sha"] == "deadbeef42"
        assert sent_payload["conclusion"] == "neutral"
        assert sent_payload["status"] == "completed"
        assert sent_payload["output"]["title"] == "Risk Assessment Complete"
        assert sent_payload["output"]["summary"] == "Identified low risk change with zero blockers."


def test_contract_publish_check_upserts_a_durable_external_delivery_identity() -> None:
    client = GitHubRestPRClient(token="ghp_test_token")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            _mock_http_response(
                200,
                {"check_runs": [{"id": 12345, "external_id": "delivery:pr-guardian-42:check"}]},
            ),
            _mock_http_response(200, {"id": 12345}),
        ]
        client.publish_check(
            repository="acme/payments",
            head_sha="deadbeef42",
            name="PR Guardian (shadow)",
            conclusion="neutral",
            title="Risk Assessment Complete",
            summary="Identified low risk change with zero blockers.",
            external_id="delivery:pr-guardian-42:check",
        )

    assert mock_urlopen.call_count == 2
    lookup = mock_urlopen.call_args_list[0][0][0]
    assert lookup.get_method() == "GET"
    assert lookup.full_url.endswith(
        "/commits/deadbeef42/check-runs?check_name=PR%20Guardian%20%28shadow%29&per_page=100"
    )
    patch_request = mock_urlopen.call_args_list[1][0][0]
    assert patch_request.get_method() == "PATCH"
    assert patch_request.full_url == "https://api.github.com/repos/acme/payments/check-runs/12345"
    patch_payload = json.loads(patch_request.data.decode("utf-8"))
    assert patch_payload["external_id"] == "delivery:pr-guardian-42:check"
    assert "head_sha" not in patch_payload


def test_contract_publish_check_creates_when_no_external_delivery_exists() -> None:
    client = GitHubRestPRClient(token="ghp_test_token")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            _mock_http_response(200, {"check_runs": []}),
            _mock_http_response(201, {"id": 12345}),
        ]
        client.publish_check(
            repository="acme/payments",
            head_sha="deadbeef42",
            name="PR Guardian (shadow)",
            conclusion="neutral",
            title="Risk Assessment Complete",
            summary="Identified low risk change with zero blockers.",
            external_id="delivery:pr-guardian-42:check",
        )

    create = mock_urlopen.call_args_list[1][0][0]
    assert create.get_method() == "POST"
    created_payload = json.loads(create.data.decode("utf-8"))
    assert created_payload["head_sha"] == "deadbeef42"
    assert created_payload["external_id"] == "delivery:pr-guardian-42:check"


def test_contract_publish_comment_creates_new_when_no_existing_marker() -> None:
    client = GitHubRestPRClient(token="ghp_test_token")

    with patch("urllib.request.urlopen") as mock_urlopen:
        # Call 1: GET /user
        # Call 2: GET /repos/acme/payments/issues/42/comments
        # Call 3: POST /repos/acme/payments/issues/42/comments
        mock_urlopen.side_effect = [
            _mock_http_response(200, {"login": "test-bot"}),
            _mock_http_response(200, [{"id": 1, "body": "Standard user comment"}]),
            _mock_http_response(201, {"id": 2, "body": f"Notice {COMMENT_MARKER}"}),
        ]

        client.publish_comment(
            repository="acme/payments",
            pr_number=42,
            body=f"Notice {COMMENT_MARKER}",
        )

        assert mock_urlopen.call_count == 3
        post_request = mock_urlopen.call_args_list[2][0][0]
        assert post_request.get_method() == "POST"
        assert post_request.full_url == "https://api.github.com/repos/acme/payments/issues/42/comments"
        sent_body = json.loads(post_request.data.decode("utf-8"))["body"]
        assert COMMENT_MARKER in sent_body


def test_contract_error_classification_and_circuit_breaker() -> None:
    limits = DependencyLimits(max_in_flight=2, failure_threshold=2, recovery_seconds=60)
    boundary = DependencyBoundary("test-github", limits)
    client = GitHubRestPRClient(token="ghp_test_token", dependency=boundary)

    # 404 HTTP Error
    fp = io.BytesIO(b'{"message": "Not Found"}')
    error_404 = urllib.error.HTTPError(
        url="https://api.github.com",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=fp,
    )

    with patch("urllib.request.urlopen", side_effect=error_404):
        with pytest.raises(GitHubAPIError) as exc_info:
            client.list_changed_files("acme/non-existent", 1)
        assert exc_info.value.status == 404

    # 503 / Network Failure (trips the circuit breaker on repeated failures)
    network_err = urllib.error.URLError(reason="Connection refused")
    with patch("urllib.request.urlopen", side_effect=network_err):
        with pytest.raises(GitHubAPIError) as exc1:
            client.list_changed_files("acme/payments", 1)
        assert exc1.value.status == 503

        with pytest.raises(GitHubAPIError) as exc2:
            client.list_changed_files("acme/payments", 1)
        assert exc2.value.status == 503

    # Circuit breaker is now open
    with pytest.raises(GitHubAPIError) as open_exc:
        client.list_changed_files("acme/payments", 1)
    assert open_exc.value.status == 503
    assert "circuit is open" in str(open_exc.value)
