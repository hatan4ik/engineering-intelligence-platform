# Production Ingestion Architecture

## Flow

`GitHub/Azure DevOps event -> normalize -> load changed files -> attach source metadata + ACL -> chunk -> index -> source catalog -> reconcile -> emit telemetry`

The ingestion plane is incremental: changed files are replaced independently and deletions remove only the source document's chunks. Full-repository reindex is reserved for schema/model migrations or explicit repair.

## Security boundary

Each indexed chunk carries repository ACL metadata. Query-time security trimming must happen in the search layer before evidence is sent to an LLM. The default normalized ACL is a repository-read group identifier; production deployments should map these identifiers to Entra groups/users through a dedicated authorization adapter.

## Chunking

- Python: top-level function/class AST chunks with symbol metadata.
- Invalid Python: safe fallback to text chunking.
- Markdown/YAML/Terraform/other text: bounded paragraph chunks today; language-aware chunkers are extension points.

Chunk IDs include source identity, commit, ordinal/symbol and content hash. Document identity excludes commit so a new version replaces stale chunks for the same branch/path.

## Idempotency and reconciliation

`NormalizedEvent.event_id` is owned by the durable worker ledger (`SqliteEventLedger` in the
reference implementation), not by process-local pipeline state. Upsert calls replace all chunks
for one document. Delete calls remove all chunks for that document. The pipeline retains a small
in-memory duplicate guard only for direct local use; it is not the worker authority.

**The "Stale RAG" Problem & Out-of-Band Reconciliation:**
Event-driven ingestion via webhooks is insufficient at massive scale due to dropped events. If the
vector index drifts from the source repository, the AI can hallucinate based on outdated code.
`SqliteSourceCatalog` is the reference source-of-truth projection for document lifecycle, and
`SourceReconciler` compares one complete authorized manifest with that catalog. It re-indexes
content, revision, ownership, or ACL changes; tombstones catalog documents absent from the source;
and repairs a missing indexed document. It rejects mixed-scope or duplicate manifests.

The current reconciler is source-only and deterministic. A scheduled provider manifest loader,
cryptographic tree attestation, managed multi-worker catalog, retention policy, and operational
source SLAs remain future work.

## Azure AI Search

`ingestion.azure_search.AzureSearchIndex` performs document-scoped replace/delete, document
presence checks used by reconciliation, and ACL-filtered retrieval.
`ingestion.schema.azure_search_fields()` defines the required metadata/search fields. A later
vector-index migration can add embeddings without changing the ingestion domain contracts.

## Production follow-ons

- GitHub App and Azure DevOps file-loader adapters
- Entra ACL resolver and ownership/service metadata resolver
- embedding batcher and vector schema
- rate-limit/backpressure handling
- OpenTelemetry spans around event, load, chunk, embed and index stages
- scheduled provider manifests, tree attestation, and managed multi-worker source catalog
- reindex/migration command with checkpointing, retention, and source-SLA reporting
