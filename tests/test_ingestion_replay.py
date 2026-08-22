from ingestion.events import NormalizedEvent
from ingestion.index import InMemoryIndex
from ingestion.ledger import SqliteEventLedger
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity
from ingestion.pipeline import IngestionPipeline
from ingestion.replay import DLQReplayer
from ingestion.worker import IngestionWorker


def test_dlq_replay_succeeds_after_transient_failure(tmp_path):
    source = SourceIdentity("github", "acme/api", "main", "abc", "api.py")
    event = NormalizedEvent(
        event_id="evt-1",
        changes=(FileChange(source=source, change_type=ChangeType.UPSERT, content="def ping():\n    return 'pong'\n", language="py", acl=ACL(groups=("api",))),),
    )

    class FailingIndex(InMemoryIndex):
        fail = True
        def replace_document(self, document_id, chunks):
            if self.fail:
                raise RuntimeError("transient")
            return super().replace_document(document_id, chunks)

    index = FailingIndex()
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    worker = IngestionWorker(IngestionPipeline(index), ledger)
    try:
        worker.handle(event)
    except RuntimeError:
        pass
    assert len(ledger.dlq_events()) == 1

    index.fail = False
    result = DLQReplayer(ledger, worker).replay_all()
    assert result == {"replayed": 1, "failed": 0}
    assert ledger.dlq_events() == []
