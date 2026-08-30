"""Emit a deterministic, review-only Company Brain memory-maintenance plan.

The command opens an existing SQLite reference database in SQLite ``mode=ro``.
It never initializes a schema, writes Company Brain facts, or publishes a
ticket.  The optional output is a separate JSON review artifact.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from company_brain import (
    CompanyBrainMaintenanceError,
    CompanyBrainStoreError,
    MemoryMaintenancePolicy,
    SqliteCompanyBrainStore,
    plan_company_brain_maintenance,
)
from control_plane.runtime import ControlPlaneConfigurationError


def _as_of(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--as-of must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--as-of must include a timezone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="existing Company Brain SQLite reference database",
    )
    parser.add_argument("--tenant", required=True, help="explicit tenant ID to assess")
    parser.add_argument(
        "--as-of", type=_as_of, required=True, help="ISO-8601 timestamp with timezone"
    )
    parser.add_argument("--stale-after-days", type=int, default=180)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional separate JSON review artifact",
    )
    args = parser.parse_args(argv)

    if args.output is not None and args.output.resolve() == args.database.resolve():
        print("--output must not overwrite the Company Brain database", file=sys.stderr)
        return 2

    try:
        plan = plan_company_brain_maintenance(
            SqliteCompanyBrainStore.open_read_only(args.database),
            tenant_id=args.tenant,
            as_of=args.as_of,
            policy=MemoryMaintenancePolicy(stale_after_days=args.stale_after_days),
        )
    except (
        CompanyBrainMaintenanceError,
        CompanyBrainStoreError,
        ControlPlaneConfigurationError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(f"company-brain maintenance planning failed: {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(plan.to_payload(), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        try:
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as error:
            print(
                f"company-brain maintenance output could not be written: {error}",
                file=sys.stderr,
            )
            return 2
        print(f"wrote review-only maintenance plan: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
