import pytest

from ingestion.ledger import SqliteEventLedger
from ingestion.models import IngestionEvent, SourceDocument
from ingestion.pipeline import InMemoryIndex, IngestionProcessor
from ingestion.worker import IngestionWorker


def make_event(event_id="evt-1"):
    return IngestionEvent(
        event_id=event_id,
        action="upsert",
        document=SourceDocument(
            provider="github", repo="acme/api", path="api.py", ref="main",
            commit_sha="123", content="def ping():\n    return 'pong'\n",
            acl_groups=("api-team",),
        ),
    )


def test_worker_persists_completion_and_deduplicates(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    worker = IngestionWorker(IngestionProcessor(InMemoryIndex()), ledger)
    event = make_event()
    assert worker.handle(event) == "indexed"
    assert worker.handle(event) == "duplicate"


class BrokenIndex(InMemoryIndex):
    def replace_document(self, document_id, chunks):
        raise RuntimeError("index down")


def test_worker_moves_failure_to_dlq(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    worker = IngestionWorker(IngestionProcessor(BrokenIndex()), ledger)
    with pytest.raises(RuntimeError, match="index down"):
        worker.handle(make_event())
    assert ledger.dlq_events()[0]["event_id"] == "evt-1"
