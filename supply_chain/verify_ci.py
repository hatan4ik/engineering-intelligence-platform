from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from security.redteam import run_content_corpus
from supply_chain.provenance import load_cyclonedx, parse_requirements, verify_image_sbom, write_image_evidence


def run_preflight() -> int:
    """Run source-only gates that do not claim anything about a built image."""

    redteam = run_content_corpus()
    if not redteam.success:
        raise SystemExit(f"red-team failures: {','.join(redteam.failures)}")

    components = parse_requirements("app/requirements.txt")
    print(f"security corpus={redteam.passed}/{redteam.total}; direct dependency pins={len(components)}")
    return 0


def run_image_verification(*, image: str, sbom_path: str, output_path: str) -> int:
    """Verify a Syft-produced image SBOM and record the exact CI image ID."""

    components = parse_requirements("app/requirements.txt")
    sbom = load_cyclonedx(sbom_path)
    allowed, failures = verify_image_sbom(
        sbom=sbom,
        required_components=components,
        image_reference=image,
    )
    if not allowed:
        raise SystemExit("image SBOM verification failed: " + "; ".join(failures))

    image_id = _inspect_image_id(image)
    source_revision = os.getenv("GITHUB_SHA", "local")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    evidence = write_image_evidence(
        output=output_path,
        image_reference=image,
        image_id=image_id,
        sbom_path=sbom_path,
        source_revision=source_revision,
    )
    print(
        "image SBOM verified; "
        f"image_id={evidence.image_id}; sbom_sha256={evidence.sbom_sha256}; "
        "evidence=local-only-not-an-attestation"
    )
    return 0


def _inspect_image_id(image: str) -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Docker error"
        raise SystemExit(f"cannot inspect built image {image!r}: {detail}")
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run supply-chain CI gates")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight", help="run source-only red-team and dependency-pin checks")
    verify = commands.add_parser("verify-image", help="verify a Syft CycloneDX SBOM for a built image")
    verify.add_argument("--image", required=True, help="the local image reference scanned by Syft")
    verify.add_argument("--sbom", required=True, help="CycloneDX SBOM generated from that image")
    verify.add_argument("--output", default="build/image-evidence.json", help="local CI evidence output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "preflight":
        return run_preflight()
    return run_image_verification(image=args.image, sbom_path=args.sbom, output_path=args.output)


if __name__ == "__main__":
    raise SystemExit(main())
