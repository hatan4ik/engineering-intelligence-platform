from ingestion.events import azure_devops_push_event, github_push_event
from ingestion.models import ChangeType


def loader(repo: str, commit: str, path: str) -> str:
    return f"# {repo} {commit} {path}\ndef loaded():\n    return 'ok'\n"


def test_github_event_normalizes_upsert_delete_and_acl():
    payload = {
        "delivery_id": "d1",
        "ref": "refs/heads/main",
        "after": "abc",
        "repository": {"full_name": "org/repo"},
        "commits": [{"added": ["a.py"], "modified": ["b.md"], "removed": ["old.py"]}],
    }
    event = github_push_event(payload, loader)
    assert event.event_id == "d1"
    by_path = {c.source.path: c for c in event.changes}
    assert by_path["a.py"].change_type == ChangeType.UPSERT
    assert by_path["old.py"].change_type == ChangeType.DELETE
    assert by_path["old.py"].content is None
    assert by_path["a.py"].acl.groups == ("repo:org/repo:read",)


def test_ado_event_normalizes_repository_identity():
    payload = {
        "id": "ado-event",
        "resource": {
            "repository": {"name": "repo", "project": {"name": "project"}},
            "refUpdates": [{"name": "refs/heads/main"}],
            "commits": [{
                "commitId": "123",
                "changes": [
                    {"changeType": "edit", "item": {"path": "/svc/app.py"}},
                    {"changeType": "delete", "item": {"path": "/svc/old.py"}},
                ],
            }],
        },
    }
    event = azure_devops_push_event(payload, loader)
    assert event.event_id == "ado-event"
    assert all(c.source.repository == "project/repo" for c in event.changes)
    assert event.changes[0].acl.groups == ("repo:project/repo:read",)
