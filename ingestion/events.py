from __future__ import annotations

from dataclasses import dataclass

from .models import ACL, ChangeType, FileChange, SourceIdentity


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    changes: tuple[FileChange, ...]


def github_push_event(payload: dict, file_loader) -> NormalizedEvent:
    repo = payload["repository"]["full_name"]
    ref = payload.get("ref", "refs/heads/main")
    branch = ref.rsplit("/", 1)[-1]
    commit = payload.get("after") or "unknown"
    event_id = payload.get("delivery_id") or f"github:{repo}:{commit}"
    changed: dict[str, ChangeType] = {}
    for c in payload.get("commits", []):
        for path in c.get("added", []) + c.get("modified", []):
            changed[path] = ChangeType.UPSERT
        for path in c.get("removed", []):
            changed[path] = ChangeType.DELETE

    changes: list[FileChange] = []
    for path, change_type in sorted(changed.items()):
        content = None if change_type == ChangeType.DELETE else file_loader(repo, commit, path)
        language = path.rsplit(".", 1)[-1].lower() if "." in path else None
        changes.append(FileChange(
            source=SourceIdentity("github", repo, branch, commit, path),
            change_type=change_type,
            content=content,
            language=language,
            acl=ACL(groups=(f"repo:{repo}:read",)),
        ))
    return NormalizedEvent(event_id=event_id, changes=tuple(changes))


def azure_devops_push_event(payload: dict, file_loader) -> NormalizedEvent:
    resource = payload["resource"]
    repo = resource["repository"]["name"]
    project = resource["repository"].get("project", {}).get("name", "default")
    repo_id = f"{project}/{repo}"
    ref = resource.get("refUpdates", [{}])[0].get("name", "refs/heads/main")
    branch = ref.rsplit("/", 1)[-1]
    commit = resource.get("commits", [{}])[-1].get("commitId", "unknown")
    event_id = payload.get("id") or f"ado:{repo_id}:{commit}"
    changes: list[FileChange] = []
    for c in resource.get("commits", []):
        for change in c.get("changes", []):
            path = change["item"]["path"].lstrip("/")
            ctype = str(change.get("changeType", "edit")).lower()
            change_type = ChangeType.DELETE if "delete" in ctype else ChangeType.UPSERT
            content = None if change_type == ChangeType.DELETE else file_loader(repo_id, commit, path)
            language = path.rsplit(".", 1)[-1].lower() if "." in path else None
            changes.append(FileChange(
                source=SourceIdentity("azure-devops", repo_id, branch, commit, path),
                change_type=change_type,
                content=content,
                language=language,
                acl=ACL(groups=(f"repo:{repo_id}:read",)),
            ))
    return NormalizedEvent(event_id=event_id, changes=tuple(changes))
