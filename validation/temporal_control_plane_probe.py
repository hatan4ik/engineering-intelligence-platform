"""Deferred operational-validation tool for the non-consequential Temporal worker.

This script intentionally creates one *Temporal evidence workflow* (and only
that workflow). It does not mutate EIP application state, audit exports, cloud
resources, or remediation targets. It is not part of the active product-build
stage; a later approved validation plan must govern its use and evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from control_plane.runtime import TemporalWorkerSettings
from orchestration.temporal_client import run_evidence_workflow


def main() -> int:
    request_id = _required("EIP_TEMPORAL_PROBE_REQUEST_ID")
    correlation_id = _required("EIP_TEMPORAL_PROBE_CORRELATION_ID")
    settings = TemporalWorkerSettings.from_environment()
    result = asyncio.run(
        run_evidence_workflow(
            settings,
            request_id=request_id,
            correlation_id=correlation_id,
        )
    )
    record = {
        "schema_version": 1,
        "kind": "temporal-control-plane-evidence",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "temporal_endpoint": settings.temporal_endpoint,
            "namespace": settings.temporal_namespace,
            "task_queue": settings.temporal_task_queue,
        },
        "request": {"request_id": request_id, "correlation_id": correlation_id},
        "result": {
            "workflow_id": result.workflow_id,
            "capability": result.capability,
            "mutation_performed": result.mutation_performed,
        },
        "limitations": [
            "This proves only the non-consequential Temporal evidence workflow.",
            "It does not prove Cosmos state, immutable audit export, remediation, backup/restore, or worker failover.",
        ],
    }
    serialized = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["sha256"] = hashlib.sha256(serialized).hexdigest()
    output = Path(os.environ.get("EIP_TEMPORAL_PROBE_EVIDENCE", "temporal-control-plane-evidence.json"))
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "workflow_id": result.workflow_id, "evidence": str(output), "sha256": record["sha256"]}))
    return 0


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required; use a retained, caller-assigned opaque identifier")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
