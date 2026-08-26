# M3 Production Ingestion

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | implemented reference paths at the stated milestone; not deployed |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../../docs/CURRENT-POSITION.md) |


## Implemented
- GitHub and Azure DevOps push normalization
- stable source/document identity
- Python AST-aware chunking + fallback chunking
- ACL metadata propagation and query-time trimming contract
- incremental replacement/delete reconciliation
- Azure AI Search adapter and schema foundation
- durable SQLite event ledger and DLQ
- durable worker lifecycle
- DLQ replay helper
- durable source-lifecycle catalog
- complete-manifest reconciliation for changed ACL/content/revision, source deletion, and missing-index repair
- GitHub/Azure DevOps file loaders
- pluggable ACL resolver
- deterministic embedding/vector enrichment contract
- regression tests for idempotency, ACL isolation, stale chunks, deletion, DLQ and embeddings

## Production adapters still required
- Entra/repository ACL resolver backed by authoritative provider APIs
- Azure OpenAI embedding adapter + configured vector dimensions/index profiles
- durable shared event ledger and source catalog for multi-worker deployment (PostgreSQL/Cosmos/queue-backed)
- webhook signature/token validation at ingress
- OTel metrics/spans, rate limiting, retry/backoff and queue backpressure
- scheduled provider manifest loader, tree attestation/reindex job, and provider contract tests

## Safety invariant
Unauthorized source material is excluded before retrieval/synthesis. Model output is never used to decide access rights.
