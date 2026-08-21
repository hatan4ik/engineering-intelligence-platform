# Authoritative State and Audit Boundary

The Engineering Intelligence Platform separates **authoritative operational state** from **retrieval projections**.

## Authoritative state

The authoritative store owns:

- service ownership, tier, dependencies and SLO metadata;
- workflow lifecycle, correlation IDs and plan hashes;
- autonomy configuration references;
- optimistic versions used to reject stale writers/approvals.

Azure AI Search is explicitly **not** authoritative for these objects. Search indexes may be rebuilt from source systems and metadata stores.

## Audit history

Every decision/action emits an append-only audit event containing actor, correlation ID, resource, action and evidence payload. Local tests use a SHA-256 hash chain to detect mutation. Production must preserve the event contract and add immutable/WORM retention.

## Consistency requirements

1. Workflow updates use compare-and-swap / optimistic concurrency.
2. Stale plans cannot overwrite newer workflow state.
3. Approvals bind to exact plan hashes and workflow IDs.
4. Audit corruption fails closed.
5. Search/index failures cannot mutate authoritative state.
6. Audit sink failure puts the execution plane into read-only/recommend-only degraded mode.

## Backends

`SqliteStateStore` and `SqliteAuditLog` are deterministic local/CI implementations. Production adapters should target a private managed database plus immutable audit storage while preserving the same contracts.
