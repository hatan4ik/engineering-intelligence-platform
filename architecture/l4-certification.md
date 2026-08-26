# L4 Bounded-Autonomy Certification

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering + Security |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | certification rules; no service is certified |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


L4 is not a global platform mode and not a model capability. Certification is scoped to:

`service + environment + runbook + blast-radius budget`

A service/action becomes L4 eligible only after recorded exercises demonstrate the control plane fails safely.

## Mandatory evidence

- rollback exercised successfully;
- kill switch exercised successfully;
- verification is independent from the mutation path;
- security review complete;
- error-budget exhaustion blocks autonomous mutation;
- policy outage forces fail-closed behavior;
- audit outage forces fail-closed behavior;
- observed blast radius remains within the certified budget;
- minimum successful exercise count is met.

## Exercise types

The reference suite records successful remediation, verification/rollback, kill switch, policy outage, audit outage and error-budget exhaustion. Each result carries an evidence reference suitable for linking to CI/chaos run artifacts.

## Promotion rule

`L3 production approval -> repeated supervised exercises -> certification evidence -> L4 for one service/runbook scope`

Any material runbook, dependency, policy, verification signal or blast-radius change invalidates the prior assurance and requires recertification.

L5 unrestricted autonomy remains explicitly unsupported.
