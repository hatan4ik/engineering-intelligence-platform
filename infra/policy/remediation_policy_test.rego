package engineering_intelligence.remediation

import rego.v1

base_input := {
  "runbook": {
    "id": "aks.rollout.undo",
    "environments": ["dev", "stage", "prod"],
    "max_blast_radius": 10,
    "required_level": 3
  },
  "policy": {
    "service": "payments",
    "environment": "prod",
    "level": 3,
    "certified_runbooks": ["aks.rollout.undo"],
    "max_blast_radius": 5,
    "kill_switch": false
  },
  "request": {
    "service": "payments",
    "environment": "prod",
    "runbook_id": "aks.rollout.undo",
    "blast_radius": 2,
    "approval_verified": true,
    "error_budget_remaining": 1.0
  },
  "control": {
    "audit_available": true,
    "verification_defined": true
  }
}

test_allow_certified_l3 if {
  result := decision with input as base_input
  result.allowed == true
}

test_deny_l3_without_verified_approval if {
  candidate := object.union(base_input, {"request": object.union(base_input.request, {"approval_verified": false})})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "verified human approval is required"
}

test_kill_switch_has_deterministic_precedence if {
  candidate := object.union(base_input, {
    "policy": object.union(base_input.policy, {"kill_switch": true}),
    "request": object.union(base_input.request, {"service": "wrong", "approval_verified": false})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "service kill switch is enabled"
}

test_l4_denied_when_error_budget_exhausted if {
  candidate := object.union(base_input, {
    "policy": object.union(base_input.policy, {"level": 4}),
    "request": object.union(base_input.request, {"error_budget_remaining": 0})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "error budget exhausted; autonomous mutation disabled"
}

test_deny_when_audit_unavailable if {
  candidate := object.union(base_input, {"control": {"audit_available": false, "verification_defined": true}})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "audit control unavailable"
}
