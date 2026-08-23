from __future__ import annotations

from dataclasses import dataclass

from .drift import DriftFinding


SAFE_PATCH_FIELDS = frozenset({"image", "replicas", "cpu_limit", "memory_limit"})


@dataclass(frozen=True)
class DriftCorrection:
    field: str
    desired: object
    observed: object
    patchable: bool
    rationale: str


@dataclass(frozen=True)
class DriftCorrectionPlan:
    resource_id: str
    service: str
    environment: str
    source_path: str | None
    source_revision: str | None
    corrections: tuple[DriftCorrection, ...]

    @property
    def requires_human_design(self) -> bool:
        return any(not item.patchable for item in self.corrections)

    @property
    def patchable(self) -> bool:
        return bool(self.corrections) and not self.requires_human_design and bool(self.source_path)


def build_correction_plan(
    findings: tuple[DriftFinding, ...],
    *,
    source_path: str | None,
    source_revision: str | None = None,
) -> DriftCorrectionPlan | None:
    if not findings:
        return None
    first = findings[0]
    for finding in findings:
        if (
            finding.resource_id != first.resource_id
            or finding.service != first.service
            or finding.environment != first.environment
        ):
            raise ValueError("correction plan findings must belong to one resource")

    corrections = tuple(
        DriftCorrection(
            field=finding.field,
            desired=finding.desired,
            observed=finding.observed,
            patchable=finding.field in SAFE_PATCH_FIELDS,
            rationale=(
                "desired-state field can be changed through a reviewable configuration PR"
                if finding.field in SAFE_PATCH_FIELDS
                else "field requires architecture/security review; no automatic source edit is permitted"
            ),
        )
        for finding in findings
    )
    return DriftCorrectionPlan(
        resource_id=first.resource_id,
        service=first.service,
        environment=first.environment,
        source_path=source_path,
        source_revision=source_revision,
        corrections=corrections,
    )


def render_correction_markdown(plan: DriftCorrectionPlan) -> str:
    lines = [
        "## Engineering Intelligence — Drift Correction Plan",
        "",
        f"- Resource: `{plan.resource_id}`",
        f"- Service: `{plan.service}`",
        f"- Environment: `{plan.environment}`",
        f"- Desired-state source: `{plan.source_path or 'unknown'}`",
    ]
    if plan.source_revision:
        lines.append(f"- Source revision: `{plan.source_revision}`")
    lines.extend(["", "| Field | Desired | Observed | Review path |", "|---|---|---|---|"])
    for item in plan.corrections:
        review = "configuration PR" if item.patchable else "human architecture/security review"
        lines.append(f"| `{item.field}` | `{item.desired!r}` | `{item.observed!r}` | {review} |")
    lines.extend([
        "",
        "This plan restores the declared desired state. It does **not** authorize a production mutation.",
    ])
    return "\n".join(lines)
