import pytest

from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.ledger import SqliteEventLedger
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline
from ingestion.worker import IngestionWorker


def make_event(event_id: str = "evt-1") -> NormalizedEvent:
    source = SourceIdentity("github", "acme/api", "main", "123", "api.py")
    return NormalizedEvent(
        event_id=event_id,
        changes=(
            FileChange(
                source=source,
                change_type=ChangeType.UPSERT,
                content="def ping():\n    return 'pong'\n",
                language="py",
                acl=ACL(groups=("api-team",)),
            ),
        ),
    )


def test_worker_persists_completion_and_deduplicates(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    worker = IngestionWorker(IngestionPipeline(InMemoryIndex()), ledger)
    event = make_event()
    assert worker.handle(event)["duplicate"] is False
    assert worker.handle(event)["duplicate"] is True


class BrokenIndex(InMemoryIndex):
    def replace_document(self, document_id, chunks):
        raise RuntimeError("index down")


def test_worker_moves_failure_to_dlq(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    worker = IngestionWorker(IngestionPipeline(BrokenIndex()), ledger)
    with pytest.raises(RuntimeError, match="index down"):
        worker.handle(make_event())
    assert ledger.dlq_events()[0]["event_id"] == "evt-1"
