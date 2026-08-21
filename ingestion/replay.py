from __future__ import annotations

import json
from dataclasses import dataclass

from .events import NormalizedEvent
from .ledger import SqliteEventLedger
from .models import ACL, ChangeType, FileChange, SourceIdentity
from .worker import IngestionWorker


def _event_from_payload(payload: str) -> NormalizedEvent:
    raw = json.loads(payload)
    changes: list[FileChange] = []
    for item in raw["changes"]:
        source = item["source"]
        acl = item.get("acl") or {}
        changes.append(
            FileChange(
                source=SourceIdentity(
                    provider=source["provider"],
                    repository=source["repository"],
                    branch=source["branch"],
                    commit_sha=source["commit_sha"],
                    path=source["path"],
                ),
                change_type=ChangeType(item["change_type"]),
                content=item.get("content"),
                language=item.get("language"),
                owner=item.get("owner"),
                service=item.get("service"),
                acl=ACL(groups=tuple(acl.get("groups", ())), users=tuple(acl.get("users", ()))),
            )
        )
    return NormalizedEvent(event_id=raw["event_id"], changes=tuple(changes))


@dataclass
class DLQReplayer:
    ledger: SqliteEventLedger
    worker: IngestionWorker

    def replay_all(self) -> dict[str, int]:
        replayed = failed = 0
        for row in list(self.ledger.dlq_events()):
            event = _event_from_payload(row["payload"])
            try:
                self.worker.handle(event)
                self.ledger.remove_from_dlq(event.event_id)
                replayed += 1
            except Exception:
                failed += 1
        return {"replayed": replayed, "failed": failed}
