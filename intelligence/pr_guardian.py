from __future__ import annotations

from dataclasses import dataclass

from .risk import RiskAssessment


@dataclass(frozen=True)
class PRPolicyDecision:
    require_extended_tests: bool
    require_additional_approval: bool
    block_merge: bool


def policy_for(assessment: RiskAssessment) -> PRPolicyDecision:
    score = assessment.score
    return PRPolicyDecision(
        require_extended_tests=score >= 55,
        require_additional_approval=score >= 70,
        block_merge=score >= 90,
    )


def render_markdown(assessment: RiskAssessment) -> str:
    policy = policy_for(assessment)
    factors = "\n".join(f"- **+{f.points}** {f.reason}" for f in assessment.factors) or "- No material risk factors detected"
    controls = []
    if policy.require_extended_tests:
        controls.append("extended test suite")
    if policy.require_additional_approval:
        controls.append("additional approval")
    if policy.block_merge:
        controls.append("merge block pending remediation")
    controls_text = ", ".join(controls) if controls else "standard branch protections"
    return (
        "## Engineering Intelligence — Change Risk\n\n"
        f"**Risk score:** `{assessment.score}/100` ({assessment.band})\n\n"
        f"### Evidence\n{factors}\n\n"
        f"### Required controls\n{controls_text}\n\n"
        "The score is deterministic and evidence-based; an LLM is not used as the policy authority."
    )
