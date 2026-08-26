from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


COMMENT_MARKER = "<!-- eip-pr-guardian -->"

# A GitHub App installation token — the token GitHub Actions injects as
# ``github.token`` — cannot call ``GET /user``; that call is only available to a
# user-to-server or personal access token.  Comments written with an
# installation token are authored by this login, so it is the identity the
# sticky-comment lookups must compare against when ``GET /user`` is refused.
INSTALLATION_TOKEN_LOGIN = "github-actions[bot]"


class GitHubAPIError(RuntimeError):
    """A GitHub REST call failed, carrying the HTTP status for callers."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


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
        self._actor_login: str | None = None

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
            raise GitHubAPIError(
                f"GitHub API {method} {path} failed: {exc.code}: {detail}", exc.code
            ) from exc
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
        actor_login = self._authenticated_login()
        comments = self._request("GET", f"/repos/{repository}/issues/{pr_number}/comments?per_page=100")
        if isinstance(comments, list):
            for comment in reversed(comments):
                author = comment.get("user")
                author_login = str(author.get("login", "")) if isinstance(author, dict) else ""
                if marker in str(comment.get("body", "")) and author_login == actor_login:
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

    def latest_comment_with_marker(
        self,
        *,
        repository: str,
        pr_number: int,
        marker: str,
    ) -> str | None:
        if not marker.startswith("<!-- eip-") or not marker.endswith(" -->"):
            raise ValueError("comment marker must be an EIP HTML marker")
        actor_login = self._authenticated_login()
        comments = self._request("GET", f"/repos/{repository}/issues/{pr_number}/comments?per_page=100")
        if not isinstance(comments, list):
            raise RuntimeError("GitHub comments response was not a list")
        for comment in reversed(comments):
            body = str(comment.get("body", ""))
            author = comment.get("user")
            author_login = str(author.get("login", "")) if isinstance(author, dict) else ""
            if marker in body and author_login == actor_login:
                return body
        return None

    def _authenticated_login(self) -> str:
        """Return the login that authors this client's comments.

        Falls back to the Actions bot identity when ``GET /user`` is refused,
        which is what an installation token does.  The fallback is cached like
        any other resolved login so every marker comparison uses one identity.
        """
        if self._actor_login is not None:
            return self._actor_login
        try:
            actor = self._request("GET", "/user")
        except GitHubAPIError as exc:
            if exc.status not in (401, 403):
                raise
            self._actor_login = INSTALLATION_TOKEN_LOGIN
            return self._actor_login
        if not isinstance(actor, dict) or not str(actor.get("login", "")):
            raise RuntimeError("GitHub authenticated-user response did not include a login")
        self._actor_login = str(actor["login"])
        return self._actor_login

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
