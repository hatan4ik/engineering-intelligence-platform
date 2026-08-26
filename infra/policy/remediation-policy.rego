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
} else := "l4-certification: no certification record for this L4 scope" if {
  is_l4
  # object.get always yields a value, so this is true for both a missing key
  # and an explicit null -- an undefined ref would silently skip the rule.
  not is_object(object.get(input, "certification", null))
} else := "l4-certification: request carries no readable evaluation time" if {
  is_l4
  not evaluated_at
} else := "l4-certification: certification expires_on is not a readable timestamp" if {
  is_l4
  not certification_expiry
} else := "l4-certification: certification has expired" if {
  is_l4
  certification_expiry <= evaluated_at
} else := "l4-certification: request carries no scope hash" if {
  is_l4
  trim_space(object.get(input, ["scope", "scope_hash"], "")) == ""
} else := "l4-certification: record scope_hash does not match the requested scope" if {
  is_l4
  input.certification.scope_hash != input.scope.scope_hash
} else := "l4-certification: certification carries no material-inputs hash" if {
  is_l4
  trim_space(object.get(input, ["certification", "inputs_hash"], "")) == ""
} else := "audit control unavailable" if {
  input.control.audit_available != true
} else := "verification control unavailable" if {
  input.control.verification_defined != true
} else := ""


# --- scoped L4 certification -------------------------------------------------
#
# architecture/l4-certification.md scopes certification to
# service + environment + runbook + blast-radius budget. The executor sends the
# scope hash of the request it is making and the certification it holds; OPA is
# a separate authorization boundary and refuses an uncertified L4 mutation on
# its own, without trusting that the caller already checked.
#
# OPA cannot recompute the material-inputs hash (it would have to reproduce the
# executor's canonical JSON of the runbook definition), so it checks that one is
# present and bound to the right scope; the executor compares it against the
# inputs it can actually see.

# The declared autonomy_level is a claim, not an authority. A declared "L4"
# always counts; the one sanctioned downgrade ("L3", a supervised exercise of an
# L4 scope) does not; anything else -- an absent field, an understated level --
# falls back to the reviewed service policy level, so the bundle can never be
# talked out of asking for a certification. Mirrors AutonomyContext.is_l4 in
# remediation/opa_policy.py.
declared_level := upper(trim_space(object.get(input, "autonomy_level", "")))

is_l4 if {
  declared_level == "L4"
}

is_l4 if {
  declared_level != "L4"
  declared_level != "L3"
  input.policy.level >= 4
}

# Undefined -- not an error -- when the timestamp is missing or unparseable, so
# the guard rules above deny instead of the comparison silently not firing.
evaluated_at := time.parse_rfc3339_ns(input.now)

certification_expiry := time.parse_rfc3339_ns(input.certification.expires_on)
