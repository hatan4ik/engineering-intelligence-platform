from orchestration.jobs import SqliteJobQueue
from orchestration.runner import DurableRunner


def test_jobs_resume_after_worker_restart_and_complete_once(tmp_path):
    path = tmp_path / "jobs.db"
    queue = SqliteJobQueue(path)
    assert queue.enqueue(
        job_id="job-1",
        workflow_id="incident:1",
        kind="investigate",
        payload={"service": "payments"},
        not_before=100,
    )
    assert not queue.enqueue(
        job_id="job-1",
        workflow_id="incident:1",
        kind="investigate",
        payload={"service": "payments"},
        not_before=100,
    )

    claimed = queue.claim(lease_seconds=10, now=100)
    assert claimed and claimed.status == "leased"
    assert queue.claim(lease_seconds=10, now=105) is None

    # New process/worker can reclaim the expired lease from the same durable DB.
    restarted = SqliteJobQueue(path)
    reclaimed = restarted.claim(lease_seconds=10, now=111)
    assert reclaimed and reclaimed.job_id == "job-1"

    calls = []
    runner = DurableRunner(
        restarted,
        {"investigate": lambda job: calls.append(job.job_id)},
    )
    # Existing lease is still active.
    assert runner.run_once(now=115) == "idle"
    assert runner.run_once(now=122) == "completed"
    assert calls == ["job-1"]
    assert restarted.get("job-1").status == "completed"


def test_failure_backs_off_and_eventually_dead_letters(tmp_path):
    queue = SqliteJobQueue(tmp_path / "jobs.db")
    queue.enqueue(
        job_id="job-bad",
        workflow_id="drift:1",
        kind="broken",
        payload={},
        max_attempts=2,
        not_before=100,
    )

    def fail(_job):
        raise RuntimeError("dependency unavailable")

    runner = DurableRunner(queue, {"broken": fail}, base_backoff_seconds=5)
    assert runner.run_once(now=100) == "retry"
    first = queue.get("job-bad")
    assert first.status == "queued"
    assert first.not_before == 105
    assert runner.run_once(now=104) == "idle"
    assert runner.run_once(now=105) == "dead_letter"
    final = queue.get("job-bad")
    assert final.status == "dead_letter"
    assert final.attempts == 2
    assert "dependency unavailable" in final.last_error


def test_unknown_handler_fails_closed_and_is_not_completed(tmp_path):
    queue = SqliteJobQueue(tmp_path / "jobs.db")
    queue.enqueue(
        job_id="job-unknown",
        workflow_id="wf-1",
        kind="not-registered",
        payload={},
        max_attempts=1,
        not_before=0,
    )
    runner = DurableRunner(queue, {})
    assert runner.run_once(now=1) == "failed"
    assert queue.get("job-unknown").status == "dead_letter"
