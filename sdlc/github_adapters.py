from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .github_checks import COMMENT_MARKER, CheckRun
from .github_events import ChangedFile, parse_changed_files


def _request(url: str, token: str, *, method: str = "GET", body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


@dataclass
class GitHubDiffProvider:
    token: str
    api_url: str = "https://api.github.com"

    def changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        page = 1
        while True:
            url = (
                f"{self.api_url}/repos/{repository}/pulls/{pr_number}/files"
                f"?per_page=100&page={page}"
            )
            rows = _request(url, self.token)
            if not isinstance(rows, list) or not rows:
                break
            files.extend(parse_changed_files(rows))
            if len(rows) < 100:
                break
            page += 1
        return files


@dataclass
class GitHubCheckPublisher:
    token: str
    api_url: str = "https://api.github.com"

    def publish(self, check: CheckRun) -> None:
        _request(
            f"{self.api_url}/repos/{check.repository}/check-runs",
            self.token,
            method="POST",
            body={
                "name": check.name,
                "head_sha": check.head_sha,
                "status": "completed",
                "conclusion": check.conclusion,
                "output": {"title": check.title, "summary": check.summary},
            },
        )


@dataclass
class GitHubCommentPublisher:
    """Upserts a single marker-tagged PR comment instead of stacking new ones."""

    token: str
    api_url: str = "https://api.github.com"

    def publish_comment(self, repository: str, pr_number: int, body: str) -> None:
        base = f"{self.api_url}/repos/{repository}/issues/{pr_number}/comments"
        existing = _request(f"{base}?per_page=100", self.token)
        marker_comment = next(
            (c for c in existing if COMMENT_MARKER in str(c.get("body", ""))),
            None,
        ) if isinstance(existing, list) else None
        if marker_comment is not None:
            _request(
                f"{self.api_url}/repos/{repository}/issues/comments/{marker_comment['id']}",
                self.token,
                method="PATCH",
                body={"body": body},
            )
        else:
            _request(base, self.token, method="POST", body={"body": body})
