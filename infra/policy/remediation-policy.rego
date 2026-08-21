package engineering_intelligence.remediation

default allow := false

# Example: production automation is limited to low-risk, reversible,
# explicitly allow-listed runbooks. Expand only through reviewed policy.
allow if {
  input.environment == "production"
  input.risk == "low"
  input.reversible == true
  input.runbook in {"restart_workload", "rollback_last_release", "rotate_expired_certificate"}
  input.audit_enabled == true
  input.verification_defined == true
}

allow if {
  input.environment != "production"
  input.risk != "high"
  input.reversible == true
  input.audit_enabled == true
}
