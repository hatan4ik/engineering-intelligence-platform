package engineering_intelligence.remediation

import rego.v1

default decision := {"allowed": false, "reason": "denied by default", "policy_revision": "eip-remediation-v1"}

decision := {"allowed": false, "reason": reason, "policy_revision": "eip-remediation-v1"} if {
  reason := deny_reason
}

decision := {"allowed": true, "reason": "authorized by OPA remediation policy", "policy_revision": "eip-remediation-v1"} if {
  not deny_reason
}

deny_reason := "service kill switch is enabled" if input.policy.kill_switch == true

deny_reason := "request is outside service/environment policy scope" if {
  input.request.service != input.policy.service
} else := "request is outside service/environment policy scope" if {
  input.request.environment != input.policy.environment
}

deny_reason := "runbook is not permitted in this environment" if {
  not input.request.environment in input.runbook.environments
}

deny_reason := "blast radius exceeds certified limit" if {
  input.request.blast_radius > input.runbook.max_blast_radius
} else := "blast radius exceeds certified limit" if {
  input.request.blast_radius > input.policy.max_blast_radius
}

deny_reason := "service autonomy level is below runbook requirement" if {
  input.policy.level < input.runbook.required_level
}

deny_reason := "runbook is not certified for this service" if {
  not input.runbook.id in input.policy.certified_runbooks
}

deny_reason := "verified human approval is required" if {
  input.policy.level == 3
  input.request.approval_verified != true
}

deny_reason := "error budget exhausted; autonomous mutation disabled" if {
  input.policy.level >= 4
  input.request.error_budget_remaining <= 0
}

deny_reason := "audit control unavailable" if input.control.audit_available != true

deny_reason := "verification control unavailable" if input.control.verification_defined != true
