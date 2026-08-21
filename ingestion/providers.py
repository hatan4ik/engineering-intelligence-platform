from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .models import SourceDocument


class FileLoader(Protocol):
    def load(self, *, repo: str, path: str, ref: str) -> str: ...


@dataclass
class GitHubFileLoader:
    token: str
    api_url: str = "https://api.github.com"

    def load(self, *, repo: str, path: str, ref: str) -> str:
        quoted = urllib.parse.quote(path, safe="/")
        url = f"{self.api_url}/repos/{repo}/contents/{quoted}?ref={urllib.parse.quote(ref)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.load(response)
        if payload.get("encoding") != "base64":
            raise ValueError("GitHub content response is not base64 encoded")
        return base64.b64decode(payload["content"]).decode("utf-8")


@dataclass
class AzureDevOpsFileLoader:
    organization_url: str
    project: str
    token: str

    def load(self, *, repo: str, path: str, ref: str) -> str:
        params = urllib.parse.urlencode(
            {
                "path": path,
                "versionDescriptor.version": ref,
                "includeContent": "true",
                "api-version": "7.1",
            }
        )
        url = (
            f"{self.organization_url.rstrip('/')}/{urllib.parse.quote(self.project)}/"
            f"_apis/git/repositories/{urllib.parse.quote(repo)}/items?{params}"
        )
        basic = base64.b64encode(f":{self.token}".encode()).decode()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
        with urllib.request.urlopen(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
        if "application/json" in content_type:
            payload = json.loads(body)
            if "content" not in payload:
                raise ValueError("Azure DevOps response did not contain file content")
            return payload["content"]
        return body.decode("utf-8")


def load_source_document(loader: FileLoader, source: SourceDocument) -> SourceDocument:
    return SourceDocument(
        provider=source.provider,
        repo=source.repo,
        path=source.path,
        ref=source.ref,
        commit_sha=source.commit_sha,
        content=loader.load(repo=source.repo, path=source.path, ref=source.commit_sha or source.ref),
        acl_groups=source.acl_groups,
        acl_users=source.acl_users,
        owner=source.owner,
        service=source.service,
    )
