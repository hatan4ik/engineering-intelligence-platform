from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


COMMENT_MARKER = "<!-- eip-pr-guardian -->"


@dataclass(frozen=True)
class PullRequestEvent:
    repository: str
    number: int
    head_sha: str
    action: str


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0


class GitHubPRClient(Protocol):
    def list_changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]: ...
    def publish_check(
        self,
        *,
        repository: str,
        head_sha: str,
        name: str,
        conclusion: str,
        title: str,
        summary: str,
    ) -> None: ...
    def publish_comment(self, *, repository: str, pr_number: int, body: str) -> None: ...


def normalize_pull_request_event(payload: dict[str, object]) -> PullRequestEvent:
    try:
        repository = str(payload["repository"]["full_name"])  # type: ignore[index]
        pr = payload["pull_request"]  # type: ignore[index]
        number = int(payload["number"])
        head_sha = str(pr["head"]["sha"])  # type: ignore[index]
        action = str(payload["action"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid GitHub pull_request payload") from exc
    return PullRequestEvent(repository=repository, number=number, head_sha=head_sha, action=action)


class GitHubRestPRClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None) -> object:
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else None

    def list_changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        result = self._request("GET", f"/repos/{repository}/pulls/{pr_number}/files?per_page=100")
        if not isinstance(result, list):
            raise RuntimeError("GitHub files response was not a list")
        return [
            ChangedFile(
                filename=str(item["filename"]),
                status=str(item.get("status", "modified")),
                additions=int(item.get("additions", 0)),
                deletions=int(item.get("deletions", 0)),
            )
            for item in result
        ]

    def publish_check(
        self,
        *,
        repository: str,
        head_sha: str,
        name: str,
        conclusion: str,
        title: str,
        summary: str,
    ) -> None:
        self._request(
            "POST",
            f"/repos/{repository}/check-runs",
            {
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "output": {"title": title, "summary": summary},
            },
        )

    def publish_comment(self, *, repository: str, pr_number: int, body: str) -> None:
        marked_body = f"{COMMENT_MARKER}\n{body}"
        comments = self._request("GET", f"/repos/{repository}/issues/{pr_number}/comments?per_page=100")
        if isinstance(comments, list):
            for comment in reversed(comments):
                if COMMENT_MARKER in str(comment.get("body", "")):
                    comment_id = int(comment["id"])
                    self._request(
                        "PATCH",
                        f"/repos/{repository}/issues/comments/{comment_id}",
                        {"body": marked_body},
                    )
                    return
        self._request("POST", f"/repos/{repository}/issues/{pr_number}/comments", {"body": marked_body})
