from threading import Event, Thread

import pytest

from resilience.dependencies import (
    DependencyBoundary,
    DependencyLimits,
    DependencyState,
    DependencyUnavailable,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _transient(error: Exception) -> bool:
    return isinstance(error, OSError)


def test_circuit_opens_after_bounded_transient_failures_then_recovers_with_one_probe():
    clock = Clock()
    boundary = DependencyBoundary(
        "example-api",
        DependencyLimits(max_in_flight=2, failure_threshold=2, recovery_seconds=10),
        clock=clock,
    )

    for _ in range(2):
        with pytest.raises(OSError):
            boundary.call(lambda: (_ for _ in ()).throw(OSError("down")), is_transient=_transient)
    assert boundary.health().state is DependencyState.OPEN

    with pytest.raises(DependencyUnavailable, match="circuit is open"):
        boundary.call(lambda: "never", is_transient=_transient)

    clock.now += 10
    assert boundary.call(lambda: "recovered", is_transient=_transient) == "recovered"
    health = boundary.health()
    assert health.state is DependencyState.CLOSED
    assert health.consecutive_transient_failures == 0


def test_non_transient_response_error_does_not_open_a_healthy_circuit():
    boundary = DependencyBoundary("example-api", DependencyLimits(failure_threshold=1))

    with pytest.raises(ValueError):
        boundary.call(lambda: (_ for _ in ()).throw(ValueError("bad request")), is_transient=_transient)

    assert boundary.health().state is DependencyState.CLOSED
    assert boundary.health().consecutive_transient_failures == 0


def test_bulkhead_rejects_a_second_in_flight_call_without_blocking():
    entered = Event()
    release = Event()
    boundary = DependencyBoundary("example-api", DependencyLimits(max_in_flight=1))

    def first_call() -> None:
        boundary.call(lambda: (entered.set(), release.wait())[1], is_transient=_transient)

    thread = Thread(target=first_call)
    thread.start()
    assert entered.wait(timeout=1)
    try:
        with pytest.raises(DependencyUnavailable, match="in-flight capacity"):
            boundary.call(lambda: "never", is_transient=_transient)
    finally:
        release.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_a_late_success_cannot_close_a_circuit_opened_by_another_request():
    entered = Event()
    release = Event()
    boundary = DependencyBoundary(
        "example-api",
        DependencyLimits(max_in_flight=2, failure_threshold=1, recovery_seconds=10),
    )

    def slow_success() -> None:
        boundary.call(
            lambda: (entered.set(), release.wait())[1],
            is_transient=_transient,
        )

    thread = Thread(target=slow_success)
    thread.start()
    assert entered.wait(timeout=1)
    try:
        with pytest.raises(OSError):
            boundary.call(
                lambda: (_ for _ in ()).throw(OSError("dependency down")),
                is_transient=_transient,
            )
        assert boundary.health().state is DependencyState.OPEN
    finally:
        release.set()
        thread.join(timeout=1)
    assert not thread.is_alive()
    assert boundary.health().state is DependencyState.OPEN
