# Operating Model

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | intended governance; not evidence that the roles are staffed |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


## Executive ownership
Executive sponsor: VP Engineering / CTO. Program owner: AI Platform / Engineering Intelligence lead.

## Engineering Intelligence Council
Monthly cross-functional governance with Platform, SRE, Security, Architecture, Developer Experience and FinOps.

Responsibilities: approve new data sources, autonomy tiers, production runbooks, model changes, KPI gates and risk exceptions.

## Core team
- AI Platform Architect
- Platform/DevOps engineers
- Retrieval/evaluation engineer
- Security/Governance lead
- SRE/Observability representative
- FinOps partner
- Product/Developer Experience owner

## Release gates
Every new agent or autonomous capability must demonstrate functional tests, retrieval/evaluation quality, security review, cost envelope, rollback path, observability and a named owner.

## Decision rights
LLM/agents may classify, summarize and recommend. Deterministic policy decides whether a mutation is permitted. Service owners retain accountability for high-impact production changes.