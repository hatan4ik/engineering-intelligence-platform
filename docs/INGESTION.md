# Production Ingestion Architecture

## Flow

`GitHub/Azure DevOps event -> normalize -> load changed files -> attach source metadata + ACL -> chunk -> embed/index -> reconcile deletes -> emit telemetry`

The ingestion plane is incremental: changed files are replaced independently and deletions remove only the source document's chunks. Full-repository reindex is reserved for schema/model migrations or explicit repair.

## Security boundary

Each indexed chunk carries repository ACL metadata. Query-time security trimming must happen in the search layer before evidence is sent to an LLM. The default normalized ACL is a repository-read group identifier; production deployments should map these identifiers to Entra groups/users through a dedicated authorization adapter.

## Chunking

- Python: top-level function/class AST chunks with symbol metadata.
- Invalid Python: safe fallback to text chunking.
- Markdown/YAML/Terraform/other text: bounded paragraph chunks today; language-aware chunkers are extension points.

Chunk IDs include source identity, commit, ordinal/symbol and content hash. Document identity excludes commit so a new version replaces stale chunks for the same branch/path.

## Idempotency and reconciliation

`NormalizedEvent.event_id` protects against duplicate delivery within a pipeline state store. The reference implementation uses an in-memory set; production should persist event IDs in a durable store with TTL. Upsert calls replace all chunks for one document. Delete calls remove all chunks for that document.

## Azure AI Search

`ingestion.azure_search.AzureSearchIndex` performs document-scoped replace/delete and ACL-filtered retrieval. `ingestion.schema.azure_search_fields()` defines the required metadata/search fields. A later vector-index migration can add embeddings without changing the ingestion domain contracts.

## Production follow-ons

- durable event ledger / DLQ / replay
- GitHub App and Azure DevOps file-loader adapters
- Entra ACL resolver and ownership/service metadata resolver
- embedding batcher and vector schema
- rate-limit/backpressure handling
- OpenTelemetry spans around event, load, chunk, embed and index stages
- reindex/migration command with checkpointing
