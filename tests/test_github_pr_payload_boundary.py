"""GitHub webhook input is narrowed before it enters PR Guardian policy."""

from __future__ import annotations

import pytest

from integrations.github.pr_guardian import normalize_pull_request_event


def _payload() -> dict[str, object]:
    return {
        "action": "opened",
        "number": 7,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {"head": {"sha": "deadbeef"}},
    }


def _replace_repository_with_array(payload: dict[str, object]) -> None:
    payload["repository"] = []


def _replace_number_with_boolean(payload: dict[str, object]) -> None:
    payload["number"] = True


def _clear_repository_name(payload: dict[str, object]) -> None:
    repository = payload["repository"]
    assert isinstance(repository, dict)
    repository["full_name"] = ""


def _remove_head_sha(payload: dict[str, object]) -> None:
    pull_request = payload["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request["head"] = {}


@pytest.mark.parametrize(
    "mutate, message",
    [
        (_replace_repository_with_array, "repository must be an object"),
        (_replace_number_with_boolean, "number must be a positive integer"),
        (_clear_repository_name, "repository.full_name"),
        (_remove_head_sha, "pull_request.head.sha"),
    ],
)
def test_invalid_github_webhook_shapes_are_rejected_at_the_boundary(mutate, message):
    payload = _payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        normalize_pull_request_event(payload)
