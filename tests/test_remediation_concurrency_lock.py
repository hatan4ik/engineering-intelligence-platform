from __future__ import annotations

from datetime import datetime, timedelta, timezone


from remediation.catalog import AutonomyLevel, default_catalog
from remediation.concurrency_lock import (
    InMemoryConcurrencyLockManager,
    LockLease,
    LockoutRefusal,
)
from remediation.executor import execute_control_loop
from remediation.policy import ActionRequest, ServiceAutonomy


class _TestAdapter:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.verified: list[str] = []
        self.rolled_back: list[str] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.executed.append(runbook_id)
        return f"exec-{runbook_id}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        self.verified.append(signal)
        return True

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        self.rolled_back.append(rollback_id)
        return f"rollback-{rollback_id}"


def test_concurrency_lock_manager_acquires_and_releases_isolated_lease() -> None:
    manager = InMemoryConcurrencyLockManager()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    lease, refusal = manager.acquire(
        "payments-service",
        ("postgres-db", "redis-cache"),
        ttl_seconds=60.0,
        now=now,
    )

    assert refusal is None
    assert isinstance(lease, LockLease)
    assert lease.service_id == "payments-service"
    assert "postgres-db" in lease.locked_services
    assert "redis-cache" in lease.locked_services
    assert len(manager.active_leases(now=now)) == 1

    released = manager.release(lease)
    assert released is True
    assert len(manager.active_leases(now=now)) == 0


def test_concurrency_lock_manager_rejects_overlapping_blast_radius() -> None:
    manager = InMemoryConcurrencyLockManager()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    lease1, refusal1 = manager.acquire(
        "order-service",
        ("shared-db", "auth-service"),
        ttl_seconds=120.0,
        now=now,
    )
    assert lease1 is not None
    assert refusal1 is None

    # Attempt concurrent remediation on inventory-service which shares "shared-db"
    lease2, refusal2 = manager.acquire(
        "inventory-service",
        ("shared-db", "warehouse-api"),
        ttl_seconds=60.0,
        now=now,
    )

    assert lease2 is None
    assert isinstance(refusal2, LockoutRefusal)
    assert refusal2.conflicting_service == "shared-db"
    assert refusal2.active_lease_id == lease1.lease_id
    assert "shared-db" in refusal2.reason


def test_concurrency_lock_manager_allows_disjoint_services() -> None:
    manager = InMemoryConcurrencyLockManager()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    lease1, refusal1 = manager.acquire("frontend", ("cdn",), now=now)
    lease2, refusal2 = manager.acquire("analytics", ("data-lake",), now=now)

    assert lease1 is not None and refusal1 is None
    assert lease2 is not None and refusal2 is None
    assert len(manager.active_leases(now=now)) == 2


def test_concurrency_lock_manager_prunes_expired_leases() -> None:
    manager = InMemoryConcurrencyLockManager()
    start = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    lease, _ = manager.acquire("billing", ("db",), ttl_seconds=30.0, now=start)
    assert lease is not None

    after_expiry = start + timedelta(seconds=35.0)
    assert len(manager.active_leases(now=after_expiry)) == 0

    # Can now acquire on the same scope
    lease2, refusal2 = manager.acquire("billing", ("db",), ttl_seconds=30.0, now=after_expiry)
    assert lease2 is not None
    assert refusal2 is None


def test_execute_control_loop_defers_when_blast_radius_is_locked() -> None:
    manager = InMemoryConcurrencyLockManager()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    # Pre-lock database dependency
    existing_lease, _ = manager.acquire("checkout-service", ("orders-db",), ttl_seconds=120.0, now=now)
    assert existing_lease is not None

    catalog = default_catalog()
    policy = ServiceAutonomy("orders-api", "stage", AutonomyLevel.APPROVE_AND_EXECUTE, ("aks.restart.workload",), 5)
    request = ActionRequest("orders-api", "stage", "aks.restart.workload", blast_radius=1)
    adapter = _TestAdapter()

    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=adapter,
        approval_verified=True,
        concurrency_lock_manager=manager,
        impacted_services=("orders-db",),
        now=now,
    )

    assert result.status == "deferred"
    assert result.error is not None
    assert "concurrency-lockout" in result.error
    assert "orders-db" in result.error
    assert len(adapter.executed) == 0


def test_execute_control_loop_acquires_and_releases_lock_on_completion() -> None:
    manager = InMemoryConcurrencyLockManager()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    catalog = default_catalog()
    policy = ServiceAutonomy("orders-api", "stage", AutonomyLevel.APPROVE_AND_EXECUTE, ("aks.restart.workload",), 5)
    request = ActionRequest("orders-api", "stage", "aks.restart.workload", blast_radius=1)
    adapter = _TestAdapter()

    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=adapter,
        approval_verified=True,
        concurrency_lock_manager=manager,
        impacted_services=("isolated-cache",),
        now=now,
    )

    assert result.status == "succeeded"
    assert result.verified is True
    # Verify lease was cleanly released in finally block
    assert len(manager.active_leases(now=now)) == 0
