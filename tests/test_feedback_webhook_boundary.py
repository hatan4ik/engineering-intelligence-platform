"""Terminal GitHub events are typed before becoming product feedback."""

from __future__ import annotations

import pytest

from feedback.outcome_capture import normalize_github_pr_outcome


def _payload() -> dict[str, object]:
    return {
        "action": "closed",
        "number": 7,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {"merged": True, "labels": []},
    }


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("number", True, "repository or PR number"),
        ("merged", "true", "merged must be a boolean"),
        ("labels", {}, "labels must be an array"),
    ],
)
def test_malformed_terminal_fields_are_rejected(field, value, message):
    payload = _payload()
    if field == "number":
        payload[field] = value
    else:
        pull_request = payload["pull_request"]
        assert isinstance(pull_request, dict)
        pull_request[field] = value

    with pytest.raises(ValueError, match=message):
        normalize_github_pr_outcome(payload)
