from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from orchestration.jobs import Job


class SenderLike(Protocol):
    def send_messages(self, message: Any) -> None: ...
    def schedule_messages(self, message: Any, schedule_time_utc: datetime) -> Any: ...


class ReceiverLike(Protocol):
    def receive_messages(self, *, max_message_count: int, max_wait_time: float) -> list[Any]: ...
    def complete_message(self, message: Any) -> None: ...
    def dead_letter_message(self, message: Any, *, reason: str, error_description: str) -> None: ...


class ServiceBusJobQueue:
    """Azure Service Bus PeekLock durable queue implementing the local Job contract.

    A claimed message is retained in `_inflight` only until settlement. Worker
    process loss intentionally leaves the message unsettled; Service Bus lock expiry
    then redelivers it. Retry attempts are rescheduled with exponential backoff and
    poison jobs are moved to the queue's dead-letter subqueue.
    """

    def __init__(self, *, sender: SenderLike, receiver: ReceiverLike) -> None:
        self.sender = sender
        self.receiver = receiver
        self._inflight: dict[str, Any] = {}
        self._jobs: dict[str, Job] = {}

    @classmethod
    def from_environment(cls) -> "ServiceBusJobQueue":
        namespace = os.environ["EIP_SERVICEBUS_NAMESPACE"]
        queue_name = os.environ["EIP_SERVICEBUS_QUEUE"]
        client = ServiceBusClient(namespace, credential=DefaultAzureCredential())
        return cls(
            sender=client.get_queue_sender(queue_name=queue_name),
            receiver=client.get_queue_receiver(queue_name=queue_name, receive_mode="peek_lock"),
        )

    @staticmethod
    def _message_for(job: Job, *, message_id: str | None = None) -> ServiceBusMessage:
        body = json.dumps(asdict(job), sort_keys=True, default=str)
        return ServiceBusMessage(
            body,
            message_id=message_id or f"{job.job_id}:{job.attempts}",
            correlation_id=job.workflow_id,
            subject=job.kind,
            application_properties={"eip_job_id": job.job_id},
        )

    def enqueue(
        self,
        *,
        job_id: str,
        workflow_id: str,
        kind: str,
        payload: dict[str, object],
        max_attempts: int = 5,
        not_before: float | None = None,
    ) -> bool:
        job = Job(
            job_id=job_id,
            workflow_id=workflow_id,
            kind=kind,
            payload=dict(payload),
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
            not_before=time.time() if not_before is None else not_before,
            lease_until=None,
            last_error=None,
        )
        message = self._message_for(job)
        if not_before is not None and not_before > time.time():
            self.sender.schedule_messages(message, datetime.fromtimestamp(not_before, timezone.utc))
        else:
            self.sender.send_messages(message)
        return True

    @staticmethod
    def _decode_body(message: Any) -> dict[str, Any]:
        body = message.body
        if isinstance(body, str):
            text = body
        elif isinstance(body, bytes):
            text = body.decode()
        else:
            chunks: list[bytes] = []
            for chunk in body:
                chunks.append(chunk if isinstance(chunk, bytes) else bytes(chunk))
            text = b"".join(chunks).decode()
        return json.loads(text)

    def claim(self, *, lease_seconds: int = 60, now: float | None = None) -> Job | None:
        # Service Bus owns lock duration; `lease_seconds` remains part of the common
        # queue interface and should match the queue's configured lock duration.
        messages = self.receiver.receive_messages(max_message_count=1, max_wait_time=0.5)
        if not messages:
            return None
        message = messages[0]
        raw = self._decode_body(message)
        current = time.time() if now is None else now
        attempts = int(raw.get("attempts", 0)) + 1
        job = Job(
            job_id=str(raw["job_id"]),
            workflow_id=str(raw["workflow_id"]),
            kind=str(raw["kind"]),
            payload=dict(raw.get("payload") or {}),
            status="leased",
            attempts=attempts,
            max_attempts=int(raw.get("max_attempts", 5)),
            not_before=float(raw.get("not_before", current)),
            lease_until=current + lease_seconds,
            last_error=raw.get("last_error"),
        )
        self._inflight[job.job_id] = message
        self._jobs[job.job_id] = job
        return job

    def complete(self, job_id: str) -> None:
        message = self._inflight.pop(job_id, None)
        if message is None:
            raise KeyError(f"job is not currently leased: {job_id}")
        self.receiver.complete_message(message)
        job = self._jobs[job_id]
        self._jobs[job_id] = Job(
            **{**asdict(job), "status": "completed", "lease_until": None, "last_error": None}
        )

    def fail(
        self,
        job_id: str,
        error: Exception,
        *,
        base_backoff_seconds: float = 5.0,
        now: float | None = None,
    ) -> Job:
        message = self._inflight.pop(job_id, None)
        if message is None:
            raise KeyError(f"job is not currently leased: {job_id}")
        job = self._jobs[job_id]
        current = time.time() if now is None else now
        error_text = f"{type(error).__name__}: {error}"
        if job.attempts >= job.max_attempts:
            self.receiver.dead_letter_message(
                message,
                reason="max-attempts-exhausted",
                error_description=error_text[:4096],
            )
            updated = Job(
                **{**asdict(job), "status": "dead_letter", "lease_until": None, "last_error": error_text}
            )
            self._jobs[job_id] = updated
            return updated

        delay = base_backoff_seconds * (2 ** max(0, job.attempts - 1))
        retry_at = current + delay
        updated = Job(
            **{
                **asdict(job),
                "status": "queued",
                "not_before": retry_at,
                "lease_until": None,
                "last_error": error_text,
            }
        )
        retry_message = self._message_for(updated, message_id=f"{job.job_id}:retry:{job.attempts}")
        self.sender.schedule_messages(retry_message, datetime.fromtimestamp(retry_at, timezone.utc))
        self.receiver.complete_message(message)
        self._jobs[job_id] = updated
        return updated

    def get(self, job_id: str) -> Job | None:
        # Service Bus is the durable source of truth; this method exposes only jobs
        # observed by the current worker and is intended for operational diagnostics.
        return self._jobs.get(job_id)
