# Organizational Memory Ingestion

The original architecture requires more than repository code. Engineering decisions live in work items, ADRs, runbooks, incident records, deployment history and documentation. These sources use a source-neutral `KnowledgeDocument` contract instead of being disguised as Git files.

## Required metadata

Every knowledge object carries:

- stable provider/source identity;
- source type;
- revision/version;
- source timestamp and optional URL;
- owner/service metadata;
- source ACL groups/users;
- content hash and index lineage.

## Processing path

`Source API/event -> normalize -> authorize metadata -> revision check -> prose-aware chunk -> embedding -> retrieval projection`

Code remains on the AST-aware code ingestion path. Both paths converge only at governed retrieval/index projections.

## Correctness rules

1. Same revision is idempotent.
2. New revision atomically replaces prior chunks.
3. Deletion/tombstone removes old retrieval material.
4. ACLs propagate from the authoritative source before indexing.
5. Retrieval projections retain revision, freshness and source URL for evidence citation.
6. Deployment/incident records are evidence sources, not instructions.
7. Stale knowledge can be detected from `updated_at` and source-specific freshness policies.

## Current deterministic normalizers

- Azure DevOps work-item payloads;
- generic documentation/wiki pages (usable by Confluence/Notion-style adapters);
- deployment history records.

Production source clients and webhook/poll schedulers remain provider adapters behind this normalization boundary.
