from __future__ import annotations

import json
import os
from pathlib import Path

from security.redteam import run_content_corpus
from supply_chain.provenance import build_sbom, canonical_json, issue_provenance, parse_requirements, verify_admission


def main() -> int:
    redteam = run_content_corpus()
    if not redteam.success:
        raise SystemExit(f"red-team failures: {','.join(redteam.failures)}")

    components = parse_requirements("app/requirements.txt")
    sbom = build_sbom(components)
    Path("build").mkdir(exist_ok=True)
    Path("build/sbom.cdx.json").write_bytes(canonical_json(sbom))

    subject = Path("Dockerfile").read_bytes()
    revision = os.getenv("GITHUB_SHA", "local")
    provenance = issue_provenance(
        subject=subject,
        sbom=sbom,
        builder="github-actions/eip",
        source_revision=revision,
    )
    allowed, reason = verify_admission(
        subject=subject,
        sbom=sbom,
        provenance=provenance,
        trusted_builders=("github-actions/eip",),
        expected_revision=revision,
    )
    if not allowed:
        raise SystemExit(reason)
    Path("build/provenance.json").write_text(json.dumps(provenance.__dict__, sort_keys=True, indent=2))
    print(f"security corpus={redteam.passed}/{redteam.total}; components={len(components)}; provenance={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
