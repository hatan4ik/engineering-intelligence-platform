"""The Cosmos audit adapter must reproduce SQLite hash-chain semantics exactly."""
from __future__ import annotations

import pytest

from state.audit import AuditConflict, SqliteAuditLog
from state.cosmos_audit import CosmosAuditLog
from state.models import AuditEvent
from tests.test_state_factory import FakeContainer


def events() -> tuple[AuditEvent, ...]:
    return tuple(
        AuditEvent(
            event_id=f"evt-{index}",
            correlation_id="corr-payments-42",
            actor="agent:remediation-executor",
            action="finish-remediation",
            resource="remediation:payments-42",
            payload={"step": index, "status": "succeeded"},
            occurred_at=f"2026-08-26T12:0{index}:00+00:00",
        )
        for index in range(5)
    )


def test_cosmos_chain_matches_sqlite_over_the_same_event_sequence(tmp_path):
    sqlite_log = SqliteAuditLog(tmp_path / "audit.db")
    cosmos_log = CosmosAuditLog(FakeContainer())

    sequence = events()
    sqlite_chain = [sqlite_log.append(event) for event in sequence]
    cosmos_chain = [cosmos_log.append(event) for event in sequence]

    assert [e.event_hash for e in cosmos_chain] == [e.event_hash for e in sqlite_chain]
    assert [e.previous_hash for e in cosmos_chain] == [e.previous_hash for e in sqlite_chain]
    assert cosmos_chain[0].previous_hash is None
    assert cosmos_chain[1].previous_hash == cosmos_chain[0].event_hash
    assert cosmos_log.last_hash() == sqlite_log.last_hash()


def test_duplicate_delivery_returns_the_stored_event_without_forking_the_chain(tmp_path):
    sqlite_log = SqliteAuditLog(tmp_path / "audit.db")
    cosmos_log = CosmosAuditLog(FakeContainer())
    event = events()[0]

    for log in (sqlite_log, cosmos_log):
        first = log.append(event)
        replayed = log.append(event)
        assert replayed.event_hash == first.event_hash
        assert replayed.previous_hash == first.previous_hash

    assert cosmos_log.event_count() == 1
    assert cosmos_log.last_hash() == sqlite_log.last_hash()


def test_reusing_an_event_id_for_different_content_is_an_audit_conflict(tmp_path):
    sqlite_log = SqliteAuditLog(tmp_path / "audit.db")
    cosmos_log = CosmosAuditLog(FakeContainer())
    original = events()[0]
    forged = AuditEvent(
        event_id=original.event_id,
        correlation_id=original.correlation_id,
        actor="human:attacker",
        action=original.action,
        resource=original.resource,
        payload={"step": 0, "status": "succeeded"},
        occurred_at=original.occurred_at,
    )

    for log in (sqlite_log, cosmos_log):
        log.append(original)
        with pytest.raises(AuditConflict):
            log.append(forged)


def test_cosmos_audit_requires_explicit_configuration():
    with pytest.raises(RuntimeError) as excinfo:
        CosmosAuditLog.from_environment({"EIP_CONTROL_PLANE_MODE": "temporal"})
    assert "EIP_COSMOS_AUDIT_CONTAINER" in str(excinfo.value)
