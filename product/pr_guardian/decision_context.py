"""Safe GitHub presentation for a bounded Company Brain decision context.

GitHub comments are readable by the repository audience, while Company Brain
evidence is authorized for an individual principal.  This renderer therefore
shows only counts, qualification state, and limitations.  It never publishes a
source locator or a relationship label learned from ACL-filtered evidence.
"""

from __future__ import annotations

from .company_brain import PRGuardianCompanyContext


def render_decision_context(context: PRGuardianCompanyContext) -> str:
    """Render a non-authorizing, repository-safe explanation for a PR review."""

    decision_context = context.decision_context
    qualification = "qualified" if decision_context.qualified else "limited"
    lines = [
        "### Company Brain decision context",
        "",
        "This is a bounded explanation for this review. It cannot approve, block, or change merge status.",
        "",
        f"- **Qualification:** `{qualification}`",
        (
            "- **PR scope:** "
            f"`{len(context.changed_services)}` mapped service(s); "
            f"`{len(context.blast_radius)}` service(s) in the deterministic blast-radius calculation."
        ),
        (
            "- **Qualified relationship support:** "
            f"`{len(decision_context.relationships)}` fresh, authorized relationship(s)."
        ),
        (
            "- **Evidence inventory:** "
            f"`{len(decision_context.evidence.references)}` authorized evidence pointer(s) retained with the finding."
        ),
        f"- **Context version:** `{decision_context.context_version}`",
        (
            "- **Citation visibility:** Individual source locations and relationship details are omitted "
            "because a GitHub comment cannot enforce Company Brain's per-reader access controls."
        ),
    ]
    if not decision_context.qualified:
        lines.extend(
            (
                "",
                "> Company Brain context is insufficient for a simulated control. This observation remains neutral.",
            )
        )
    if decision_context.limitations:
        lines.extend(("", "#### Limitations"))
        lines.extend(f"- {limitation}" for limitation in decision_context.limitations)
    return "\n".join(lines)
