# Knowledge ingest runbook

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Purpose** | Index a checked-out repository into a knowledge index |
| **Mutation authority** | Writes only to the knowledge index it is given. It never changes source, IaC, or policy |
| **Code** | [`../ingestion/runner.py`](../ingestion/runner.py), [`../scripts/ingest_repository.py`](../scripts/ingest_repository.py) |
| **Workflow** | [`../.github/workflows/knowledge-ingest.yml`](../.github/workflows/knowledge-ingest.yml) |
| **Design** | [`INGESTION.md`](INGESTION.md) |
| **Production claim** | None. A green run proves the pipeline executes, not that the deployed index is correct |

## What the runner does

`ingest_checkout` walks a checked-out working tree and, for every eligible file, builds the same
`NormalizedEvent` the webhook path builds, then hands it to `IngestionWorker`/`IngestionPipeline`.
The existing chunkers (`PythonASTChunker`, `TextChunker`) and the existing ACL contract apply
unchanged.

* **Eligibility.** A file is ingested when its suffix is in `INGESTIBLE_SUFFIXES` (or its name is
  in `INGESTIBLE_NAMES`), it is under `max_file_bytes` (512 KiB by default), and it decodes as UTF-8.
  `.git`, virtualenvs, caches, `node_modules`, and build output are never walked.
* **ACL.** Indexed chunks carry `repo:<repository>:read` — the same group `ingestion/events.py`
  grants — plus every group passed to `--groups`. An empty group list is refused, because chunks
  with no ACL groups are readable by every caller.
* **Identity vs provenance.** `--branch` is document identity: `document_id` is
  `git:<repository>:<branch>:<path>`, so ingesting a branch again **replaces** its documents.
  `--commit-sha` is provenance only: it appears in `SourceIdentity.commit_sha` and therefore in the
  chunk citation `git:<repository>@<commit>:<path>`. Both are required.
* **Idempotency.** Each file becomes one event whose id is derived from
  `(repository, branch, path, content, acl)` — deliberately *not* the commit sha, or every commit
  would re-ingest every file, and deliberately *including* the ACL, so an access change is never
  swallowed by the ledger. The durable SQLite ledger dedupes, so re-running over an unchanged checkout
  writes nothing and reports `documents: 0` with `duplicates` equal to the file count, and a later
  commit on the same branch re-ingests only the files whose content changed. A file's citation
  therefore names the commit at which its content was last ingested — the commit that content came
  from, not necessarily `HEAD`.
* **Failure isolation.** A file that cannot be read is counted in `failed` and listed by path in
  `failed_paths` in the run output; it does not abort the run. Read failures never reach the
  ledger's dead-letter queue (no event exists for them yet) — the output is the only record, so
  check it.

The runner takes an `Index` instance. It never constructs an Azure client and never reads Azure
configuration — that decision belongs to the caller.

### Run counts

| Key | Meaning |
|---|---|
| `documents` | Documents written to the index by this run |
| `chunks` | Chunks written to the index by this run |
| `skipped` | Files that are not ingestible (unsupported suffix, oversize, or not UTF-8) |
| `failed` | Files that could not be read or that the pipeline rejected |
| `duplicates` | Files whose event id the ledger had already completed |

## Running it locally

```bash
PYTHONPATH=. python scripts/ingest_repository.py \
  --root . \
  --repository "$(git config --get remote.origin.url | sed 's#.*[:/]\([^/]*/[^/]*\)\.git#\1#')" \
  --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --commit-sha "$(git rev-parse HEAD)" \
  --groups engineering \
  --index in-memory \
  --ledger /tmp/ingestion-ledger.db
```

`--index in-memory` runs the whole pipeline in process and prints the counts as JSON. It needs no
dependencies beyond the standard library and writes nothing outside `--ledger`.

Keep the ledger on durable storage if you want incremental behaviour across runs. Re-ingesting
without a ledger is safe — index writes are keyed by `document_id` and replace the document — but
it does redundant work.

## Running it in CI

`knowledge-ingest.yml` runs on every push to `main` and on `workflow_dispatch` (input `index`,
default `in-memory`).

* The **in-memory** job runs unconditionally as a smoke test of the pipeline and uploads the
  counts as an artifact. It proves the pipeline executes; it says nothing about the deployed index.
* The **azure** job runs only for a dispatch with `index: azure`, and inside that job only when the
  configuration below is present. When it is absent the job writes
  `Azure index not configured for this repository — skipped` to the job summary and does nothing
  else.

## What the Azure path needs

`--index azure` fails closed with a `RuntimeError` listing every missing name (exit code 2). It
requires:

| Variable | Meaning |
|---|---|
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint for the target index |
| `AZURE_SEARCH_INDEX` | Index name, created by [`../scripts/create_search_index.py`](../scripts/create_search_index.py) |
| `AZURE_SEARCH_API_KEY` **or** the full identity set | The credential. An API key builds an `AzureKeyCredential`. The alternative is workload identity, which needs **all three** of `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` — `DefaultAzureCredential` cannot federate from a client id alone |

`scripts/ingest_repository.py` itself only checks `AZURE_CLIENT_ID` (it is `DefaultAzureCredential`
that resolves the rest of the identity), so on a hosted GitHub runner the workflow must also sign in
first: `knowledge-ingest.yml` grants `id-token: write` and runs `azure/login@v2` with the same three
values before invoking the CLI. Without that step a federated run passes its own gate and then fails
at token acquisition.

Prefer workload identity. If an API key is used, it must come from a secret store and never from a
checked-in file or a shell history.

The Azure index must already exist with the schema in
[`../ingestion/search_schema.py`](../ingestion/search_schema.py); this runner writes documents, it
does not create or migrate an index.

## Known limitation: deletions do not propagate

`ingest_checkout` only walks the files that are present. A file deleted from the branch keeps its
document in the index until something removes it: this runner emits no `ChangeType.DELETE` and never
prunes documents that have disappeared from the checkout. The pipeline supports deletion
(`IngestionPipeline.apply_changes` handles `ChangeType.DELETE`, and the webhook path in
`ingestion/events.py` emits it for removed paths), so a checkout-side reconciliation pass would be a
separate piece of work — see [`INGESTION.md`](INGESTION.md) on out-of-band reconciliation.

Until that exists, treat a checkout-ingested index as **append/replace only**: content changes and
new files are reflected, deletions are not. An ACL change applied by re-running with different
`--groups` does propagate, because every file's document is rewritten with the new ACL.

## What this runbook does not claim

Running ingestion does not make retrieval correct, does not certify the ACL model against a real
directory, and is not evidence for any promotion decision. Evidence has its own contract in
[`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) and its own registry in
[`evidence/README.md`](evidence/README.md).
