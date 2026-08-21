# Security Threat Model

## Primary threats
1. Prompt injection through retrieved code, tickets or documentation.
2. Cross-repository or cross-team data exfiltration.
3. Secret/PII leakage through ingestion, prompts or logs.
4. Hallucinated remediation presented as fact.
5. Excessive agent permissions and confused-deputy behavior.
6. Model/token abuse causing cost or availability impact.
7. Poisoned or stale knowledge influencing decisions.
8. Automation loops causing repeated harmful mutations.

## Required controls
- Authenticate every caller with Entra ID; authorize before retrieval.
- Preserve repository/document ACLs as retrieval filters.
- Scan/redact secrets and sensitive data before embedding and logging.
- Treat retrieved content as data, never as trusted instructions.
- Require citations/evidence for operational recommendations.
- Separate reasoning from mutation: policy engine authorizes actions.
- Use managed identities and least-privilege scopes.
- Rate limit, quota and meter by user/team/agent.
- Add freshness/ownership metadata and source-quality weighting.
- Bound retries and autonomous action counts.
- Maintain immutable audit records and emergency kill switch.

## Autonomy tiers
- Tier 0: answer/summarize only.
- Tier 1: recommend action.
- Tier 2: create PR/ticket/runbook proposal.
- Tier 3: execute low-risk non-production remediation.
- Tier 4: execute allow-listed reversible production remediation with policy approval.
- Tier 5: broader supervised autonomy only after evidence from prior tiers.