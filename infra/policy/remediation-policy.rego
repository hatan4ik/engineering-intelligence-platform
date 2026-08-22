package engineering_intelligence.remediation

import rego.v1

policy_revision := "eip-remediation-v1"

decision := {"allowed": false, "reason": deny_reason, "policy_revision": policy_revision} if {
  deny_reason != ""
}

decision := {"allowed": true, "reason": "authorized by OPA remediation policy", "policy_revision": policy_revision} if {
  deny_reason == ""
}

# Ordered precedence guarantees exactly one deterministic reason even when
# several controls fail simultaneously.
deny_reason := "service kill switch is enabled" if {
  input.policy.kill_switch == true
} else := "request is outside service/environment policy scope" if {
  input.request.service != input.policy.service
} else := "request is outside service/environment policy scope" if {
  input.request.environment != input.policy.environment
} else := "runbook is not permitted in this environment" if {
  not input.request.environment in input.runbook.environments
} else := "blast radius exceeds certified limit" if {
  input.request.blast_radius > input.runbook.max_blast_radius
} else := "blast radius exceeds certified limit" if {
  input.request.blast_radius > input.policy.max_blast_radius
} else := "service autonomy level is below runbook requirement" if {
  input.policy.level < input.runbook.required_level
} else := "runbook is not certified for this service" if {
  not input.runbook.id in input.policy.certified_runbooks
} else := "verified human approval is required" if {
  input.policy.level == 3
  input.request.approval_verified != true
} else := "error budget exhausted; autonomous mutation disabled" if {
  input.policy.level >= 4
  input.request.error_budget_remaining <= 0
} else := "audit control unavailable" if {
  input.control.audit_available != true
} else := "verification control unavailable" if {
  input.control.verification_defined != true
} else := ""
