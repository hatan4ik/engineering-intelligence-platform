from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from intelligence.knowledge_decay import KnowledgeDecayFinding, KnowledgeRecord, detect_knowledge_decay


@dataclass(frozen=True)
class KnowledgeMaintenanceItem:
    source_id: str
    action: str
    severity: int
    reason: str


@dataclass(frozen=True)
class KnowledgeMaintenancePlan:
    findings: tuple[KnowledgeDecayFinding, ...]
    items: tuple[KnowledgeMaintenanceItem, ...]
    summary: str


class KnowledgeMaintenancePublisher(Protocol):
    def publish(self, plan: KnowledgeMaintenancePlan) -> None: ...


def plan_knowledge_maintenance(records: list[KnowledgeRecord], *, stale_after_days: int = 180) -> KnowledgeMaintenancePlan:
    findings = detect_knowledge_decay(records, stale_after_days=stale_after_days)
    items: list[KnowledgeMaintenanceItem] = []
    for finding in findings:
        if finding.kind == "stale":
            action = "request-owner-review"
        elif finding.kind == "missing-owner":
            action = "assign-accountable-owner"
        elif finding.kind == "conflict":
            action = "resolve-conflicting-active-revisions"
        else:
            action = "review-knowledge-source"
        items.append(KnowledgeMaintenanceItem(finding.source_id, action, finding.severity, finding.evidence))
    ordered = tuple(sorted(items, key=lambda i: (-i.severity, i.source_id, i.action)))
    return KnowledgeMaintenancePlan(findings, ordered, render_maintenance_plan(ordered))


def render_maintenance_plan(items: Iterable[KnowledgeMaintenanceItem]) -> str:
    items = tuple(items)
    marker = "<!-- eip-knowledge-decay -->"
    if not items:
        return f"{marker}\n## Knowledge Health\n\nNo stale, ownerless, or conflicting knowledge detected."
    lines = [marker, "## Knowledge Health", "", f"Generated **{len(items)}** reviewable maintenance item(s):", ""]
    for item in items:
        lines.append(f"- **S{item.severity}** `{item.source_id}` → `{item.action}` — {item.reason}")
    lines.extend(["", "The agent proposes maintenance work only; it does not silently rewrite organizational truth."])
    return "\n".join(lines)
