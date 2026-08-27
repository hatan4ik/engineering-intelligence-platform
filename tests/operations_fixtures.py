"""Shared payload/evidence fixtures for the operational-intelligence trigger tests."""
from __future__ import annotations

import json
from pathlib import Path

ADO_FAILED_RUN = {
    "resource": {
        "id": 42,
        "result": "failed",
        "project": {"name": "Platform"},
        "definition": {"id": 7, "name": "payments"},
        "environment": "prod",
        "service": "payments",
        "sourceVersion": "bbb2222",
    }
}

COMMON_ALERT = {
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {
        "essentials": {
            "alertId": "/subscriptions/s1/providers/Microsoft.AlertsManagement/alerts/INC-42",
            "alertRule": "payments-readiness",
            "severity": "Sev2",
            "monitorCondition": "Fired",
        },
        "alertContext": {},
        "customProperties": {"service": "payments", "environment": "prod"},
    },
}

EVIDENCE_FIXTURE = {
    "events": [
        {
            "id": "alert-1",
            "kind": "alert",
            "service": "${service}",
            "timestamp": "2026-08-22T10:04:00Z",
            "summary": "readiness probe failed for ${service}",
            "source": "azure-monitor",
            "severity": 4,
        }
    ],
    "deployment_events": [
        {
            "id": "deploy-previous",
            "kind": "deployment",
            "service": "${service}",
            "timestamp": "2026-08-21T10:00:00Z",
            "summary": "release v1",
            "source": "azure-devops",
            "severity": 1,
            "attributes": {"commit": "aaa1111"},
        },
        {
            "id": "${deployment_id}",
            "kind": "deployment",
            "service": "${service}",
            "timestamp": "2026-08-22T10:00:00Z",
            "summary": "release v2",
            "source": "azure-devops",
            "severity": 1,
            "attributes": {"commit": "bbb2222"},
        },
        # A hotfix deployed while the incident was open. It is inside the evidence
        # window but it is not what failed, so no proposal may name its commit.
        {
            "id": "deploy-hotfix",
            "kind": "deployment",
            "service": "${service}",
            "timestamp": "2026-08-22T10:10:00Z",
            "summary": "hotfix release",
            "source": "azure-devops",
            "severity": 1,
            "attributes": {"commit": "ccc3333"},
        },
    ],
    "incident_events": [
        {
            "id": "deploy-current",
            "kind": "deployment",
            "service": "${service}",
            "timestamp": "2026-08-22T10:00:00Z",
            "summary": "release v2 for incident ${incident_id}",
            "source": "azure-devops",
            "severity": 1,
            "attributes": {"commit": "bbb2222", "last_good_commit": "aaa1111"},
        }
    ],
}


def write_evidence_fixture(directory: Path) -> Path:
    path = Path(directory) / "operations-evidence.json"
    path.write_text(json.dumps(EVIDENCE_FIXTURE, indent=2), encoding="utf-8")
    return path


def write_payload(directory: Path, name: str, payload: dict) -> Path:
    path = Path(directory) / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
