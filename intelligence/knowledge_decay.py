from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class KnowledgeRecord:
    source_id: str
    source_type: str
    title: str
    revision: str
    updated_at: datetime
    owner: str | None = None
    supersedes: str | None = None


@dataclass(frozen=True)
class KnowledgeDecayFinding:
    source_id: str
    kind: str
    evidence: str
    severity: int


def detect_knowledge_decay(records: list[KnowledgeRecord], *, stale_after_days: int = 180, now: datetime | None = None) -> tuple[KnowledgeDecayFinding, ...]:
    now = now or datetime.now(timezone.utc)
    findings: list[KnowledgeDecayFinding] = []
    by_title: dict[str, list[KnowledgeRecord]] = {}
    for record in records:
        by_title.setdefault(record.title.strip().lower(), []).append(record)
        age = (now - record.updated_at).days
        if age > stale_after_days:
            findings.append(KnowledgeDecayFinding(record.source_id, "stale", f"{record.title} has not been updated for {age} days", 2))
        if not record.owner:
            findings.append(KnowledgeDecayFinding(record.source_id, "missing-owner", f"{record.title} has no accountable owner", 2))
    for title, versions in by_title.items():
        active = [r for r in versions if not r.supersedes]
        revisions = {r.revision for r in active}
        if len(active) > 1 and len(revisions) > 1:
            for record in active:
                findings.append(KnowledgeDecayFinding(record.source_id, "conflict", f"multiple active revisions exist for {title}", 4))
    return tuple(findings)
