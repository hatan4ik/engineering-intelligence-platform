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

# --- scoped L4 certification -------------------------------------------------

l4_input := object.union(base_input, {
  "policy": object.union(base_input.policy, {"level": 4}),
  "autonomy_level": "L4",
  "now": "2026-08-26T00:00:00Z",
  "scope": {"scope_hash": "scope-aaa"},
  "certification": {
    "scope_hash": "scope-aaa",
    "inputs_hash": "inputs-bbb",
    "expires_on": "2026-11-01T00:00:00Z"
  }
})

test_allow_l4_with_a_matching_unexpired_certification if {
  result := decision with input as l4_input
  result.allowed == true
}

test_deny_l4_without_a_certification if {
  candidate := object.remove(l4_input, {"certification"})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: no certification record for this L4 scope"
}

test_deny_l4_with_a_null_certification if {
  candidate := object.union(l4_input, {"certification": null})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: no certification record for this L4 scope"
}

test_deny_l4_with_an_expired_certification if {
  candidate := object.union(l4_input, {
    "certification": object.union(l4_input.certification, {"expires_on": "2026-08-25T00:00:00Z"})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: certification has expired"
}

test_deny_l4_when_the_expiry_is_unreadable if {
  candidate := object.union(l4_input, {
    "certification": object.union(l4_input.certification, {"expires_on": "whenever"})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: certification expires_on is not a readable timestamp"
}

test_deny_l4_when_the_evaluation_time_is_unreadable if {
  candidate := object.union(l4_input, {"now": ""})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: request carries no readable evaluation time"
}

test_deny_l4_when_the_certification_is_for_another_scope if {
  candidate := object.union(l4_input, {
    "certification": object.union(l4_input.certification, {"scope_hash": "scope-zzz"})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: record scope_hash does not match the requested scope"
}

test_deny_l4_when_the_request_carries_no_scope_hash if {
  candidate := object.union(l4_input, {"scope": {"scope_hash": "  "}})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: request carries no scope hash"
}

test_deny_l4_without_a_material_inputs_hash if {
  candidate := object.union(l4_input, {
    "certification": object.union(l4_input.certification, {"inputs_hash": ""})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: certification carries no material-inputs hash"
}

test_l3_is_never_asked_for_a_certification if {
  candidate := object.union(base_input, {"autonomy_level": "L3"})
  result := decision with input as candidate
  result.allowed == true
}

test_the_error_budget_control_outranks_the_certification_check if {
  candidate := object.union(l4_input, {
    "request": object.union(l4_input.request, {"error_budget_remaining": 0})
  })
  result := decision with input as candidate
  result.allowed == false
  result.reason == "error budget exhausted; autonomous mutation disabled"
}

# --- the declared autonomy_level is a claim, not an authority ----------------

l4_policy_no_declared_level := object.union(base_input, {
  "policy": object.union(base_input.policy, {"level": 4}),
  "now": "2026-08-26T00:00:00Z",
  "scope": {"scope_hash": "scope-aaa"}
})

test_deny_a_level_four_policy_with_no_declared_level_and_no_certification if {
  result := decision with input as l4_policy_no_declared_level
  result.allowed == false
  result.reason == "l4-certification: no certification record for this L4 scope"
}

test_allow_a_level_four_policy_with_no_declared_level_and_a_valid_certification if {
  candidate := object.union(l4_policy_no_declared_level, {
    "certification": {
      "scope_hash": "scope-aaa",
      "inputs_hash": "inputs-bbb",
      "expires_on": "2026-11-01T00:00:00Z"
    }
  })
  result := decision with input as candidate
  result.allowed == true
}

test_deny_a_level_four_policy_that_understates_its_level if {
  candidate := object.union(l4_policy_no_declared_level, {"autonomy_level": "L2"})
  result := decision with input as candidate
  result.allowed == false
  result.reason == "l4-certification: no certification record for this L4 scope"
}

test_the_sanctioned_supervised_downgrade_is_not_asked_for_a_certification if {
  candidate := object.union(l4_policy_no_declared_level, {"autonomy_level": "L3"})
  result := decision with input as candidate
  result.allowed == true
}

test_a_level_three_policy_with_no_declared_level_is_not_asked_for_a_certification if {
  result := decision with input as base_input
  result.allowed == true
}
