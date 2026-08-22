from ingestion.events import NormalizedEvent
from ingestion.ledger import SqliteEventLedger
from ingestion.models import ACL, ChangeType, FileChange, SourceIdentity


def event(event_id: str = "evt-1") -> NormalizedEvent:
    source = SourceIdentity("github", "acme/payments", "main", "abc", "app.py")
    return NormalizedEvent(
        event_id=event_id,
        changes=(
            FileChange(
                source=source,
                change_type=ChangeType.UPSERT,
                content="print('ok')",
                language="py",
                acl=ACL(groups=("payments",)),
            ),
        ),
    )


def test_completed_event_is_seen(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    ledger.start("evt-1")
    assert not ledger.seen("evt-1")
    ledger.complete("evt-1")
    assert ledger.seen("evt-1")


def test_failure_enters_dlq_and_can_be_removed(tmp_path):
    ledger = SqliteEventLedger(tmp_path / "ledger.db")
    item = event()
    ledger.start(item.event_id)
    ledger.fail(item, RuntimeError("search unavailable"))
    rows = ledger.dlq_events()
    assert len(rows) == 1
    assert rows[0]["event_id"] == item.event_id
    assert "search unavailable" in rows[0]["error"]
    ledger.remove_from_dlq(item.event_id)
    assert ledger.dlq_events() == []
