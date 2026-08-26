# Security Threat Model

## Primary threats
1. Prompt injection through retrieved code, tickets or documentation (The Confused Deputy).
2. Cross-repository or cross-team data exfiltration.
3. Secret/PII leakage through ingestion, prompts or logs.
4. Hallucinated remediation presented as fact.
5. Excessive agent permissions and confused-deputy behavior.
6. Model/token abuse causing cost or availability impact.
7. Poisoned or stale knowledge influencing decisions.
8. Automation loops causing repeated harmful mutations.
9. Stale or replayed human approvals authorizing a changed plan.
10. Retrieval/index poisoning altering evidence presented to operators.
11. Retention, residency, or deletion failures exposing engineering knowledge beyond its approved lifecycle.

## Required controls
- Authenticate every caller with Entra ID; authorize before retrieval.
- Preserve repository/document ACLs as retrieval filters.
- Scan/redact secrets and sensitive data before embedding and logging.
- **Inject a deterministic Guardrail SLM before the primary model to block prompt injection and prevent Confused Deputy approvals.**
- Treat retrieved content as data, never as trusted instructions.
- Require citations/evidence for operational recommendations.
- Separate reasoning from mutation: a deterministic policy decision boundary authorizes actions.
- Use managed identities/workload identity and least-privilege scopes.
- Rate limit, quota and meter by user/team/agent.
- Add freshness/ownership/provenance metadata and source-quality weighting.
- Record data classification, approved purpose, retention, residency, legal-hold, and deletion/reconciliation behavior for every source before real-data ingestion.
- Bound retries and autonomous action counts.
- Bind approval tokens to the exact workflow/plan and expiration time.
- Maintain immutable audit records and emergency kill switches.
- Require independent verification and rollback/escalation for every autonomous mutation.

## Autonomy levels
- **L0 Observe:** collect/correlate only.
- **L1 Recommend:** evidence-backed recommendation; no mutation.
- **L2 Human execute:** system prepares an exact action and rollback; a human executes it.
- **L3 Approve and execute:** authenticated human approval authorizes an allow-listed deterministic runbook.
- **L4 Bounded autonomous:** only explicitly certified service + environment + runbook combinations may execute automatically within policy, blast-radius, error-budget, time and retry limits.
- **L5 Unrestricted autonomy:** intentionally unsupported and out of scope.

Autonomy is granted per service/action/environment, never globally to an agent or model.
