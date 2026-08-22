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
        files: list[ChangedFile] = []
        page = 1
        while True:
            result = self._request(
                "GET", f"/repos/{repository}/pulls/{pr_number}/files?per_page=100&page={page}"
            )
            if not isinstance(result, list):
                raise RuntimeError("GitHub files response was not a list")
            files.extend(
                ChangedFile(
                    filename=str(item["filename"]),
                    status=str(item.get("status", "modified")),
                    additions=int(item.get("additions", 0)),
                    deletions=int(item.get("deletions", 0)),
                )
                for item in result
            )
            if len(result) < 100:
                return files
            page += 1

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

    def publish_sticky_comment(
        self,
        *,
        repository: str,
        pr_number: int,
        marker: str,
        body: str,
    ) -> None:
        if not marker.startswith("<!-- eip-") or not marker.endswith(" -->"):
            raise ValueError("sticky marker must be an EIP HTML marker")
        marked_body = body if marker in body else f"{marker}\n{body}"
        comments = self._request("GET", f"/repos/{repository}/issues/{pr_number}/comments?per_page=100")
        if isinstance(comments, list):
            for comment in reversed(comments):
                if marker in str(comment.get("body", "")):
                    comment_id = int(comment["id"])
                    self._request(
                        "PATCH",
                        f"/repos/{repository}/issues/comments/{comment_id}",
                        {"body": marked_body},
                    )
                    return
        self._request("POST", f"/repos/{repository}/issues/{pr_number}/comments", {"body": marked_body})

    def publish_comment(self, *, repository: str, pr_number: int, body: str) -> None:
        self.publish_sticky_comment(
            repository=repository,
            pr_number=pr_number,
            marker=COMMENT_MARKER,
            body=body,
        )

    def ensure_maintenance_issue(
        self,
        *,
        repository: str,
        marker: str,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> int:
        if not marker.startswith("<!-- eip-") or not marker.endswith(" -->"):
            raise ValueError("issue marker must be an EIP HTML marker")
        marked_body = body if marker in body else f"{marker}\n{body}"
        issues = self._request("GET", f"/repos/{repository}/issues?state=open&per_page=100")
        if isinstance(issues, list):
            for issue in issues:
                # Pull requests appear in the issues API; do not repurpose one.
                if "pull_request" in issue:
                    continue
                if marker in str(issue.get("body", "")):
                    number = int(issue["number"])
                    self._request(
                        "PATCH",
                        f"/repos/{repository}/issues/{number}",
                        {"title": title, "body": marked_body, "labels": list(labels)},
                    )
                    return number
        created = self._request(
            "POST",
            f"/repos/{repository}/issues",
            {"title": title, "body": marked_body, "labels": list(labels)},
        )
        if not isinstance(created, dict) or "number" not in created:
            raise RuntimeError("GitHub issue creation did not return an issue number")
        return int(created["number"])
