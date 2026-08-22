from __future__ import annotations

from remediation.catalog import AutonomyLevel
from remediation.policy import ServiceAutonomy
from .policy import AutonomyCertification


def certify_l4_policy(policy: ServiceAutonomy, certification: AutonomyCertification) -> None:
    if policy.level is not AutonomyLevel.BOUNDED_AUTONOMOUS:
        raise ValueError("L4 certification requires a bounded-autonomous service policy")
    if (policy.service, policy.environment) != (certification.service, certification.environment):
        raise ValueError("certification does not match service/environment policy scope")
    if certification.runbook_id not in policy.certified_runbooks:
        raise ValueError("certification runbook is not present in service policy")
    if policy.max_blast_radius > certification.max_blast_radius:
        raise ValueError("service policy blast radius exceeds certification evidence")
    if not certification.l4_eligible:
        raise PermissionError("L4 controls incomplete: " + ", ".join(certification.missing_controls))
