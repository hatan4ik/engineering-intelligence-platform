# Production Proof Plan

| | |
|---|---|
| **Status** | Target promotion plan; not itself evidence that a gate has passed |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |
| **Operational requirements** | [`../architecture/NFR.md`](../architecture/NFR.md) |

The Engineering Intelligence Platform must not be described as production-ready merely because
the reference implementation and CI are green. Production readiness is earned from external
integration evidence, sustained operation, failure drills and measured control-plane behavior.
Each result must be retained using the evidence contract; a CI artifact alone is insufficient.

## Required proof sequence

1. **Production-like integration environment**
   - real Entra application/service principals and group claims
   - private Azure AI Search/OpenAI/Key Vault paths
   - real GitHub/Azure DevOps source events
   - real Azure Monitor/App Insights/OTel evidence
   - Cosmos/authoritative state backend and immutable audit export
   - isolated AKS environment with representative workload topology

2. **Shadow mode**
   - PR Guardian, Incident Intelligence, Drift and risk run against real events
   - no automatic production mutation
   - capture recommendation acceptance, correctness, false-positive and false-negative outcomes

3. **L2 recommendation/corrective-work mode**
   - Architecture Guard and Drift may create reviewable checks/issues/PR plans
   - humans execute production changes
   - compare predicted risk and RCA hypotheses with actual outcomes

4. **L3 supervised remediation pilot**
   - one service + one environment + one certified runbook at a time
   - plan-bound approval required
   - OPA decision required
   - digital-twin replay required for configured risk classes
   - independent verification and rollback/escalation required

5. **Minimum soak**
   - at least 168 continuous hours of production-like operation before readiness review
   - longer soak for sparse-event services; elapsed time alone is not enough
   - no unresolved audit gaps or failed safety drills

## Evidence gates

The readiness evaluator requires evidence for:

- real source integration
- Entra production authentication
- private network path
- HA authoritative state backend
- backup/restore drill
- immutable audit export
- adversarial/security suite
- control-plane SLO measurement
- production-like soak
- rollback drill
- kill-switch drill
- independent verification
- L3 certification report
- >=99% observed control-plane success rate in the evaluation window
- 100% successful audit-write requirement for authorized/denied action decisions

## Promotion rule

A green CI build proves the repository is internally consistent. It does **not** prove production readiness.

`reference implementation -> integration environment -> shadow evidence -> L2 -> L3 pilot -> soak -> readiness review -> narrowly scoped L4 evaluation`

L4 remains service/environment/runbook-specific. There is no platform-wide blanket L4 certification and unrestricted L5 autonomy remains unsupported.
