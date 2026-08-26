import re

files_to_fix = [
    'architecture/design.md',
    'architecture/maturity-scorecard.md',
    'architecture/authoritative-state.md',
    'architecture/durable-orchestration.md'
]

for filepath in files_to_fix:
    with open(filepath, 'r') as f:
        content = f.read()

    # In design.md
    content = content.replace(
        'production adapters (PostgreSQL/Cosmos, Service Bus)',
        'production adapters (Temporal/PostgreSQL)'
    )
    content = content.replace(
        "Cosmos\n   state adapter now exists (`state/cosmos_store.py`); the durable job queue's Service Bus\n   adapter is still unwritten",
        "Temporal\n   adapter is the authoritative execution engine; the legacy custom Azure Service Bus/Cosmos\n   adapters have been deprecated"
    )

    # In maturity-scorecard.md
    content = content.replace(
        '| Authoritative state | **2.5** | Cosmos adapter with storage-level CAS plus local contract | provision/wire state, multi-region ops, backup/restore, retention evidence |',
        '| Authoritative state | **3.0** | Temporal state persistence with PostgreSQL | multi-region Temporal cluster ops, backup/restore, retention evidence |'
    )
    content = content.replace(
        '| Durable orchestration | **2.5** | local leases, retries, recovery, DLQ, durable remediation jobs | production queue/backend and concurrency/compensation operations |',
        '| Durable orchestration | **3.0** | Temporal workflow/activity contracts | multi-cluster Temporal routing and concurrency/compensation operations |'
    )

    # In authoritative-state.md
    content = content.replace('`state/cosmos_store.py`', '`state/temporal_store.py`')
    content = content.replace('`CosmosStateStore.apply_workflow_event()` uses a same-partition transactional', '`TemporalStateStore` uses Temporal\'s native workflow event history')
    content = content.replace('the Cosmos path also uses the storage conditional write', 'the Temporal path guarantees this via workflow determinism')
    content = content.replace('the Cosmos adapter uses the same workflow-partition transactional receipt shape', 'the Temporal adapter natively records this in the event history')

    # In durable-orchestration.md
    content = content.replace('Cosmos/audit configuration', 'Temporal/PostgreSQL configuration')

    with open(filepath, 'w') as f:
        f.write(content)
