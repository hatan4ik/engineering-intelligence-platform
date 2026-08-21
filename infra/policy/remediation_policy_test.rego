package eip.remediation

test_allow_nonprod {
  allow with input as {"environment":"dev","reversible":true,"runbook":"restart_deployment"}
}

test_deny_prod_without_approval {
  not allow with input as {"environment":"prod","reversible":true,"runbook":"restart_deployment"}
}
