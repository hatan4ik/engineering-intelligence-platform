"""Validate a non-authorizing PR Guardian shadow-pilot onboarding manifest.

The manifest describes a planned, named pilot; it does not enable PR Guardian
or create an evidence record.  Supplying ``--config-root`` additionally proves
only that the checked-out repository configuration matches the shadow plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from product.pr_guardian.config import load_repository_config
from product.pr_guardian.contracts import ProductContractError
from product.pr_guardian.pilot import (
    parse_shadow_pilot_manifest,
    validate_shadow_installation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", required=True, type=Path, help="shadow-pilot JSON manifest"
    )
    parser.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="optional checkout root whose .eip/pr-guardian.json must match the manifest",
    )
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest = parse_shadow_pilot_manifest(payload)
        configuration_checked = args.config_root is not None
        if args.config_root is not None:
            configuration = load_repository_config(
                args.config_root,
                repository=manifest.repository,
            )
            validate_shadow_installation(manifest, configuration)
    except (OSError, json.JSONDecodeError, ProductContractError) as error:
        print(f"shadow-pilot manifest is invalid: {error}", file=sys.stderr)
        return 2

    print(
        "shadow-pilot manifest is valid: "
        f"pilot={manifest.pilot_id} repository={manifest.repository} "
        f"mode={manifest.mode} advisory_or_enforcement_authorized="
        f"{manifest.advisory_or_enforcement_authorized} "
        f"configuration_checked={configuration_checked}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
