from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class KnowledgeDecayKind(StrEnum):
    """The bounded set of knowledge-health conditions this detector can report."""

    STALE = "stale"
    MISSING_OWNER = "missing-owner"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class KnowledgeRecord:
    source_id: str
    source_type: str
    title: str
    revision: str
    updated_at: datetime | None
    owner: str | None = None
    supersedes: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_id, "source_id"),
            (self.source_type, "source_type"),
            (self.title, "title"),
            (self.revision, "revision"),
        ):
            if not isinstance(value, str) or not value.strip() or "\n" in value:
                raise ValueError(f"knowledge record {label} is invalid")
        if self.updated_at is not None and (
            self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None
        ):
            raise ValueError("knowledge record updated_at must include a timezone")
        optional_fields: tuple[tuple[str | None, str], ...] = (
            (self.owner, "owner"),
            (self.supersedes, "supersedes"),
        )
        for optional_value, label in optional_fields:
            if optional_value is not None and (
                not isinstance(optional_value, str) or not optional_value.strip() or "\n" in optional_value
            ):
                raise ValueError(f"knowledge record {label} is invalid")


@dataclass(frozen=True)
class KnowledgeDecayFinding:
    source_id: str
    kind: KnowledgeDecayKind
    evidence: str
    severity: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip() or "\n" in self.source_id:
            raise ValueError("knowledge decay source_id is invalid")
        if not isinstance(self.kind, KnowledgeDecayKind):
            raise ValueError("knowledge decay kind is invalid")
        if not isinstance(self.evidence, str) or not self.evidence.strip() or "\n" in self.evidence:
            raise ValueError("knowledge decay evidence is invalid")
        if type(self.severity) is not int or not 1 <= self.severity <= 5:
            raise ValueError("knowledge decay severity must be in [1, 5]")


def detect_knowledge_decay(
    records: list[KnowledgeRecord], *, stale_after_days: int = 180, now: datetime | None = None
) -> tuple[KnowledgeDecayFinding, ...]:
    """Find reviewable knowledge-health conditions without changing any source."""

    if type(stale_after_days) is not int or stale_after_days < 0:
        raise ValueError("stale_after_days must be a non-negative integer")
    reference_time = now or datetime.now(timezone.utc)
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise ValueError("knowledge decay now must include a timezone")
    reference_time = reference_time.astimezone(timezone.utc)
    findings: list[KnowledgeDecayFinding] = []
    by_title: dict[tuple[str, str], list[KnowledgeRecord]] = {}
    for record in sorted(records, key=lambda item: item.source_id):
        title_key = (record.source_type.strip().lower(), record.title.strip().lower())
        by_title.setdefault(title_key, []).append(record)
        if record.updated_at is not None:
            age = (reference_time - record.updated_at.astimezone(timezone.utc)).days
            if age > stale_after_days:
                findings.append(
                    KnowledgeDecayFinding(
                        record.source_id,
                        KnowledgeDecayKind.STALE,
                        f"{record.title} has not been updated for {age} days",
                        2,
                    )
                )
        if not record.owner:
            findings.append(
                KnowledgeDecayFinding(
                    record.source_id,
                    KnowledgeDecayKind.MISSING_OWNER,
                    f"{record.title} has no accountable owner",
                    2,
                )
            )
    for (source_type, title), versions in sorted(by_title.items()):
        active = [r for r in versions if not r.supersedes]
        revisions = {r.revision for r in active}
        if len(active) > 1 and len(revisions) > 1:
            for record in sorted(active, key=lambda item: item.source_id):
                findings.append(
                    KnowledgeDecayFinding(
                        record.source_id,
                        KnowledgeDecayKind.CONFLICT,
                        f"multiple active {source_type} revisions exist for {title}",
                        4,
                    )
                )
    return tuple(sorted(findings, key=lambda item: (item.source_id, item.kind.value, item.evidence)))
