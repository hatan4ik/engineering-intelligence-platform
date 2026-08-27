"""Correlate an incident from a saved Azure Monitor common-alert-schema payload.

Runs the same service composition as ``POST /v1/events/incident`` and prints the
L1 analysis, the topology blast radius, and the L2 proposals as JSON. It proposes;
it never executes.

    python -m scripts.correlate_incident \
        --payload common-alert.json \
        --evidence fixture:operations-evidence.json \
        --state-dir .eip

``--publish github`` opens or updates one marked issue carrying the same document;
it requires ``GITHUB_TOKEN`` and ``--repository owner/name``.
"""
from __future__ import annotations

import asyncio

import argparse
import json
import os
from pathlib import Path

from app.operations_api import (
    GitHubIncidentPublisher,
    build_operations_capability,
    github_intelligence_client,
    incident_report,
    normalize_common_alert,
)


def _github_client(token: str):
    """Seam: tests substitute a recording client here rather than reaching GitHub."""

    return github_intelligence_client(token)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, help="file holding the common alert schema JSON")
    parser.add_argument(
        "--evidence",
        default=None,
        help="evidence mode; defaults to EIP_OPERATIONS_EVIDENCE (fixture:<path> or azure-monitor)",
    )
    parser.add_argument("--state-dir", default=None, help="defaults to EIP_STATE_DIR, else .eip")
    parser.add_argument("--publish", choices=("none", "github"), default="none")
    parser.add_argument("--repository", default=None, help="owner/name, required by --publish github")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    trigger = normalize_common_alert(payload)

    environ = dict(os.environ)
    if args.evidence:
        environ["EIP_OPERATIONS_EVIDENCE"] = args.evidence
    environ["EIP_STATE_DIR"] = args.state_dir or environ.get("EIP_STATE_DIR") or ".eip"

    publisher = None
    if args.publish == "github":
        token = environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("--publish github requires GITHUB_TOKEN")
        if not args.repository:
            raise RuntimeError("--publish github requires --repository owner/name")
        publisher = GitHubIncidentPublisher(
            _github_client(token), args.repository, trigger.environment
        )

    capability = build_operations_capability(
        environ, incident_publisher=publisher, require_webhook_secret=False
    )
    if not trigger.fired:
        print(
            json.dumps(
                {
                    "status": "ignored",
                    "reason": "monitorCondition is not Fired",
                    "incident_id": trigger.incident_id,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    result = asyncio.run(
        capability.incident.investigate(
            incident_id=trigger.incident_id,
            service=trigger.service,
            environment=trigger.environment,
        )
    )
    print(json.dumps(incident_report(trigger, result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
