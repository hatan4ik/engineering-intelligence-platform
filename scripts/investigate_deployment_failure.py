"""Investigate an Azure DevOps deployment failure from a saved service-hook payload.

Runs the same service composition as ``POST /v1/events/deployment`` and prints the
L1 analysis and the L2 proposals as JSON. It proposes; it never executes.

    python -m scripts.investigate_deployment_failure \
        --payload ado-service-hook.json \
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
    GitHubDeploymentFailurePublisher,
    build_operations_capability,
    deployment_report,
    github_intelligence_client,
)
from integrations.azure_devops.deployment_failure import normalize_service_hook


def _github_client(token: str):
    """Seam: tests substitute a recording client here rather than reaching GitHub."""

    return github_intelligence_client(token)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, help="file holding the ADO service-hook JSON")
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
    event = normalize_service_hook(payload)

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
        publisher = GitHubDeploymentFailurePublisher(_github_client(token), args.repository)

    capability = build_operations_capability(
        environ, deployment_publisher=publisher, require_webhook_secret=False
    )
    result = asyncio.run(capability.deployment.investigate(event))
    print(json.dumps(deployment_report(event, result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
