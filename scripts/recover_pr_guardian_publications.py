"""Recover due PR Guardian GitHub deliveries from the local reference outbox.

This command operates only on artifacts already durably recorded by PR
Guardian. It does not re-evaluate a pull request, change a product mode, or
grant any additional repository authority. A managed runtime needs an
equivalent scheduled, monitored recovery worker with its own operational
evidence.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from company_brain.artifact_outbox import SqliteArtifactOutbox
from integrations.github.pr_guardian import GitHubRestPRClient
from product.pr_guardian.publication import PRGuardianPublisher


_OUTBOX_FILENAME = "pr-guardian-publication-outbox.db"


def _positive_delivery_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("maximum deliveries must be an integer") from error
    if not 1 <= limit <= 100:
        raise argparse.ArgumentTypeError("maximum deliveries must be between 1 and 100")
    return limit


def main(argv: list[str] | None = None) -> int:
    """Drain a bounded number of currently due artifact deliveries."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("EIP_STATE_DIR", ".eip")),
        help="directory containing pr-guardian-publication-outbox.db",
    )
    parser.add_argument(
        "--maximum-deliveries",
        type=_positive_delivery_limit,
        default=100,
        help="due deliveries to attempt (1-100; default: 100)",
    )
    arguments = parser.parse_args(argv)

    token = os.environ.get("EIP_GITHUB_TOKEN")
    if not token:
        print("PR Guardian publication recovery requires EIP_GITHUB_TOKEN", file=sys.stderr)
        return 2
    outbox_path = arguments.state_dir / _OUTBOX_FILENAME
    if not outbox_path.is_file():
        print(f"PR Guardian publication outbox was not found: {outbox_path}", file=sys.stderr)
        return 2

    try:
        publisher = PRGuardianPublisher(
            GitHubRestPRClient(token),
            SqliteArtifactOutbox(outbox_path),
        )
        delivered = publisher.deliver_pending(maximum_deliveries=arguments.maximum_deliveries)
    except Exception as error:
        # Outbox records can be broadly operationally visible; do not print
        # upstream response bodies or payload details that an adapter carries.
        print(
            "PR Guardian publication recovery failed; "
            f"the durable delivery remains retryable ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    print(f"PR Guardian publication recovery completed: deliveries_attempted={delivered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
