from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from resilience.dependencies import DependencyBoundary, DependencyLimits, DependencyUnavailable


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


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"GitHub pull_request {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"GitHub pull_request {label} must be a non-blank string")
    return value.strip()


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"GitHub pull_request {label} must be a positive integer")
    return value


def normalize_pull_request_event(payload: Mapping[str, object]) -> PullRequestEvent:
    """Narrow an untrusted GitHub webhook object to the product event contract."""

    repository = _object(payload.get("repository"), "repository")
    pull_request = _object(payload.get("pull_request"), "pull_request")
    head = _object(pull_request.get("head"), "pull_request.head")
    return PullRequestEvent(
        repository=_text(repository.get("full_name"), "repository.full_name"),
        number=_positive_int(payload.get("number"), "number"),
        head_sha=_text(head.get("sha"), "pull_request.head.sha"),
        action=_text(payload.get("action"), "action"),
    )


class GitHubRestPRClient:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com",
        *,
        timeout_seconds: float = 20.0,
        dependency: DependencyBoundary | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._dependency = dependency or DependencyBoundary(
            "github-rest",
            DependencyLimits(max_in_flight=8, failure_threshold=3, recovery_seconds=30),
        )
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
        def send() -> object:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                raise GitHubAPIError(
                    f"GitHub API {method} {path} failed: {exc.code}: {detail}", exc.code
                ) from exc
            except (OSError, urllib.error.URLError) as exc:
                raise GitHubAPIError(
                    f"GitHub API {method} {path} is unavailable: {type(exc).__name__}", 503
                ) from exc
            try:
                return json.loads(raw) if raw else None
            except json.JSONDecodeError as exc:
                raise GitHubAPIError(
                    f"GitHub API {method} {path} returned invalid JSON", 503
                ) from exc

        try:
            return self._dependency.call(send, is_transient=_transient_github_error)
        except DependencyUnavailable as exc:
            raise GitHubAPIError(
                f"GitHub API {method} {path} is unavailable: {exc.reason}", 503
            ) from exc

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


def _transient_github_error(error: Exception) -> bool:
    """Count only retryable GitHub failure classes toward the circuit breaker."""

    return isinstance(error, GitHubAPIError) and (
        error.status == 429 or error.status >= 500
    )
