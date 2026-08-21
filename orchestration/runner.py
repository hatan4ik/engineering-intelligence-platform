from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .jobs import Job, SqliteJobQueue

JobHandler = Callable[[Job], None]


@dataclass
class DurableRunner:
    queue: SqliteJobQueue
    handlers: Mapping[str, JobHandler]
    lease_seconds: int = 60
    base_backoff_seconds: float = 5.0

    def run_once(self, *, now: float | None = None) -> str:
        job = self.queue.claim(lease_seconds=self.lease_seconds, now=now)
        if job is None:
            return "idle"
        handler = self.handlers.get(job.kind)
        if handler is None:
            self.queue.fail(
                job.job_id,
                KeyError(f"no handler registered for job kind {job.kind}"),
                base_backoff_seconds=self.base_backoff_seconds,
                now=now,
            )
            return "failed"
        try:
            handler(job)
        except Exception as exc:
            updated = self.queue.fail(
                job.job_id,
                exc,
                base_backoff_seconds=self.base_backoff_seconds,
                now=now,
            )
            return "dead_letter" if updated.status == "dead_letter" else "retry"
        self.queue.complete(job.job_id)
        return "completed"
