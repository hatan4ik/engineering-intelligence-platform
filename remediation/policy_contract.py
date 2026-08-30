"""Stable remediation-policy reasons and branch coverage requirements.

The Rego bundle remains the authorization implementation. This module is its
reviewed behavioral contract: tests exercise each named branch through OPA and
the local reference evaluator rather than scraping policy source text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyReason(StrEnum):
    AUTHORIZED = "authorized by OPA remediation policy"
    KILL_SWITCH = "service kill switch is enabled"
    POLICY_LEVEL_MISSING = "service autonomy policy carries no reviewed level"
    OUTSIDE_SCOPE = "request is outside service/environment policy scope"
    RUNBOOK_ENVIRONMENT = "runbook is not permitted in this environment"
    BLAST_RADIUS = "blast radius exceeds certified limit"
    AUTONOMY_LEVEL = "service autonomy level is below runbook requirement"
    RUNBOOK_CERTIFICATION = "runbook is not certified for this service"
    HUMAN_APPROVAL = "verified human approval is required"
    ERROR_BUDGET = "error budget exhausted; autonomous mutation disabled"
    CERTIFICATION_ABSENT = "l4-certification: no certification record for this L4 scope"
    EVALUATION_TIME_UNREADABLE = "l4-certification: request carries no readable evaluation time"
    CERTIFICATION_EXPIRY_UNREADABLE = "l4-certification: certification expires_on is not a readable timestamp"
    CERTIFICATION_EXPIRED = "l4-certification: certification has expired"
    SCOPE_MISSING = "l4-certification: request carries no scope hash"
    SCOPE_MISMATCH = "l4-certification: record scope_hash does not match the requested scope"
    INPUTS_HASH_MISSING = "l4-certification: certification carries no material-inputs hash"
    AUDIT_UNAVAILABLE = "audit control unavailable"
    VERIFICATION_UNAVAILABLE = "verification control unavailable"


class RegoDenyBranch(StrEnum):
    KILL_SWITCH = "kill-switch"
    POLICY_LEVEL_MISSING = "policy-level-missing"
    SCOPE_SERVICE = "scope-service"
    SCOPE_ENVIRONMENT = "scope-environment"
    RUNBOOK_ENVIRONMENT = "runbook-environment"
    RUNBOOK_BLAST_RADIUS = "runbook-blast-radius"
    SERVICE_BLAST_RADIUS = "service-blast-radius"
    AUTONOMY_LEVEL = "autonomy-level"
    RUNBOOK_CERTIFICATION = "runbook-certification"
    L3_HUMAN_APPROVAL = "l3-human-approval"
    L4_ERROR_BUDGET = "l4-error-budget"
    L4_CERTIFICATION_ABSENT = "l4-certification-absent"
    L4_EVALUATION_TIME_UNREADABLE = "l4-evaluation-time-unreadable"
    L4_CERTIFICATION_EXPIRY_UNREADABLE = "l4-certification-expiry-unreadable"
    L4_CERTIFICATION_EXPIRED = "l4-certification-expired"
    L4_SCOPE_MISSING = "l4-scope-missing"
    L4_SCOPE_MISMATCH = "l4-scope-mismatch"
    L4_INPUTS_HASH_MISSING = "l4-inputs-hash-missing"
    AUDIT_CONTROL = "audit-control-after-safety-and-certification"
    VERIFICATION_CONTROL = "verification-control"


@dataclass(frozen=True)
class RegoBranchRequirement:
    """A named deny branch and the corpus case that proves it."""

    branch: RegoDenyBranch
    reason: PolicyReason
    case_name: str
    boundary_only: bool = False


REGO_DENY_BRANCH_REQUIREMENTS: tuple[RegoBranchRequirement, ...] = (
    RegoBranchRequirement(RegoDenyBranch.KILL_SWITCH, PolicyReason.KILL_SWITCH, "kill-switch-precedes-all-other-failures"),
    RegoBranchRequirement(RegoDenyBranch.POLICY_LEVEL_MISSING, PolicyReason.POLICY_LEVEL_MISSING, "policy-level-missing", True),
    RegoBranchRequirement(RegoDenyBranch.SCOPE_SERVICE, PolicyReason.OUTSIDE_SCOPE, "scope-service"),
    RegoBranchRequirement(RegoDenyBranch.SCOPE_ENVIRONMENT, PolicyReason.OUTSIDE_SCOPE, "scope-environment"),
    RegoBranchRequirement(RegoDenyBranch.RUNBOOK_ENVIRONMENT, PolicyReason.RUNBOOK_ENVIRONMENT, "runbook-environment"),
    RegoBranchRequirement(RegoDenyBranch.RUNBOOK_BLAST_RADIUS, PolicyReason.BLAST_RADIUS, "runbook-blast-radius"),
    RegoBranchRequirement(RegoDenyBranch.SERVICE_BLAST_RADIUS, PolicyReason.BLAST_RADIUS, "service-blast-radius"),
    RegoBranchRequirement(RegoDenyBranch.AUTONOMY_LEVEL, PolicyReason.AUTONOMY_LEVEL, "autonomy-level"),
    RegoBranchRequirement(RegoDenyBranch.RUNBOOK_CERTIFICATION, PolicyReason.RUNBOOK_CERTIFICATION, "runbook-certification"),
    RegoBranchRequirement(RegoDenyBranch.L3_HUMAN_APPROVAL, PolicyReason.HUMAN_APPROVAL, "l3-human-approval"),
    RegoBranchRequirement(RegoDenyBranch.L4_ERROR_BUDGET, PolicyReason.ERROR_BUDGET, "l4-error-budget"),
    RegoBranchRequirement(RegoDenyBranch.L4_CERTIFICATION_ABSENT, PolicyReason.CERTIFICATION_ABSENT, "l4-certification-absent"),
    RegoBranchRequirement(RegoDenyBranch.L4_EVALUATION_TIME_UNREADABLE, PolicyReason.EVALUATION_TIME_UNREADABLE, "l4-evaluation-time-unreadable"),
    RegoBranchRequirement(RegoDenyBranch.L4_CERTIFICATION_EXPIRY_UNREADABLE, PolicyReason.CERTIFICATION_EXPIRY_UNREADABLE, "l4-certification-expiry-unreadable"),
    RegoBranchRequirement(RegoDenyBranch.L4_CERTIFICATION_EXPIRED, PolicyReason.CERTIFICATION_EXPIRED, "l4-certification-expired"),
    RegoBranchRequirement(RegoDenyBranch.L4_SCOPE_MISSING, PolicyReason.SCOPE_MISSING, "l4-scope-missing"),
    RegoBranchRequirement(RegoDenyBranch.L4_SCOPE_MISMATCH, PolicyReason.SCOPE_MISMATCH, "l4-scope-mismatch"),
    RegoBranchRequirement(RegoDenyBranch.L4_INPUTS_HASH_MISSING, PolicyReason.INPUTS_HASH_MISSING, "l4-inputs-hash-missing"),
    RegoBranchRequirement(RegoDenyBranch.AUDIT_CONTROL, PolicyReason.AUDIT_UNAVAILABLE, "audit-control-after-safety-and-certification"),
    RegoBranchRequirement(RegoDenyBranch.VERIFICATION_CONTROL, PolicyReason.VERIFICATION_UNAVAILABLE, "verification-control"),
)


def branch_requirement(case_name: str) -> RegoBranchRequirement | None:
    """Find the explicit contract requirement for a corpus case name."""

    return next((item for item in REGO_DENY_BRANCH_REQUIREMENTS if item.case_name == case_name), None)
