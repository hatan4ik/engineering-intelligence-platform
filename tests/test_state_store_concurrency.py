"""Concurrency invariants for the authoritative state store and audit log.

These prove the compare-and-swap and chain-integrity properties the control
plane relies on, under real threaded contention against one SQLite file.
"""
from __future__ import annotations

import threading

from state.audit import SqliteAuditLog
from state.models import AuditEvent, WorkflowRecord, WorkflowStatus
from state.store import SqliteStateStore, VersionConflict


def _workflow(wid: str = "wf-1") -> WorkflowRecord:
    return WorkflowRecord(
        workflow_id=wid,
        service_id="payments",
        environment="prod",
        kind="remediation",
        status=WorkflowStatus.PLANNED,
        correlation_id="corr-1",
        plan_hash="sha256:abc",
    )


def test_compare_and_swap_admits_exactly_one_racing_writer(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    base = store.put_workflow(_workflow())  # version 1

    results: list[str] = []
    barrier = threading.Barrier(8)

    def attempt() -> None:
        barrier.wait()
        try:
            store.put_workflow(
                _workflow(),  # any transition off version 1
                expected_version=base.version,
            )
            results.append("ok")
        except VersionConflict:
            results.append("conflict")

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Real CAS: exactly one writer wins version 1 -> 2; the rest see the conflict.
    assert results.count("ok") == 1, results
    assert results.count("conflict") == 7, results
    assert store.get_workflow("wf-1").version == 2


def test_concurrent_audit_appends_keep_a_single_verifiable_chain(tmp_path):
    audit = SqliteAuditLog(tmp_path / "audit.db")
    barrier = threading.Barrier(12)

    def append(i: int) -> None:
        barrier.wait()
        audit.append(
            AuditEvent(
                event_id=f"evt-{i}",
                correlation_id="corr",
                actor="agent:test",
                action="write",
                resource="wf-1",
                payload={"i": i},
            )
        )

    threads = [threading.Thread(target=append, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No forked chain: every event links to a unique predecessor and verify passes.
    assert audit.verify_chain()
