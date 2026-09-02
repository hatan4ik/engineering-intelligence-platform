"""Operator-facing readiness over the existing shadow-pilot contracts.

This module deliberately evaluates only facts available in a trusted target
repository checkout.  A contract-ready result means the manifest and runtime
configuration agree on a bounded shadow scope.  It never claims that GitHub
labels/settings exist, humans approved the pilot, or external evidence was
retained; those remain explicit operational actions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from .config import CONFIG_RELATIVE_PATH, load_repository_config
from .contracts import ProductContractError
from .pilot import (
    PILOT_MANIFEST_RELATIVE_PATH,
    ShadowPilotManifest,
    parse_shadow_pilot_manifest,
    validate_shadow_installation,
)


class PilotReadinessState(StrEnum):
    NOT_READY = "not-ready"
    CONTRACT_READY = "contract-ready"


class ReadinessCheckState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    EXTERNAL_REQUIRED = "external-required"


@dataclass(frozen=True)
class PilotReadinessCheck:
    name: str
    state: ReadinessCheckState
    detail: str

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "state": self.state.value, "detail": self.detail}


@dataclass(frozen=True)
class PilotReadinessReport:
    state: PilotReadinessState
    repository: str | None
    pilot_id: str | None
    checks: tuple[PilotReadinessCheck, ...]
    operator_actions: tuple[str, ...]
    operational_evidence_collected: Literal[False] = False
    advisory_or_enforcement_authorized: Literal[False] = False

    @property
    def contract_ready(self) -> bool:
        return self.state is PilotReadinessState.CONTRACT_READY

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "state": self.state.value,
            "contract_ready": self.contract_ready,
            "repository": self.repository,
            "pilot_id": self.pilot_id,
            "checks": [check.to_payload() for check in self.checks],
            "operator_actions": list(self.operator_actions),
            "operational_evidence_collected": self.operational_evidence_collected,
            "advisory_or_enforcement_authorized": self.advisory_or_enforcement_authorized,
        }


def assess_shadow_pilot_checkout(root: str | Path) -> PilotReadinessReport:
    """Assess repository-local pilot contracts without performing external I/O."""

    checkout = Path(root)
    manifest_path = checkout / PILOT_MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        return _not_ready(
            repository=None,
            pilot_id=None,
            detail=f"{PILOT_MANIFEST_RELATIVE_PATH} is missing",
            action="Create a reviewed shadow-pilot manifest with real accountable values.",
        )

    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = parse_shadow_pilot_manifest(payload)
    except (OSError, json.JSONDecodeError, ProductContractError) as error:
        return _not_ready(
            repository=None,
            pilot_id=None,
            detail=f"shadow-pilot manifest is invalid: {error}",
            action="Correct the shadow-pilot manifest before configuring runtime behavior.",
        )

    config_path = checkout / CONFIG_RELATIVE_PATH
    if not config_path.is_file():
        return _not_ready(
            repository=manifest.repository,
            pilot_id=manifest.pilot_id,
            detail=f"{CONFIG_RELATIVE_PATH} is missing",
            action="Add the repository-owned PR Guardian configuration in shadow mode.",
            manifest=manifest,
        )

    try:
        configuration = load_repository_config(
            checkout,
            repository=manifest.repository,
        )
        validate_shadow_installation(manifest, configuration)
    except ProductContractError as error:
        return _not_ready(
            repository=manifest.repository,
            pilot_id=manifest.pilot_id,
            detail=f"runtime configuration does not match the shadow manifest: {error}",
            action="Align .eip/pr-guardian.json with the reviewed shadow-pilot manifest.",
            manifest=manifest,
        )

    checks = (
        PilotReadinessCheck(
            "manifest-contract",
            ReadinessCheckState.PASS,
            "The named manifest is valid and bounded to shadow mode.",
        ),
        PilotReadinessCheck(
            "runtime-contract",
            ReadinessCheckState.PASS,
            "The repository-owned runtime configuration matches the manifest.",
        ),
        PilotReadinessCheck(
            "github-operational-controls",
            ReadinessCheckState.EXTERNAL_REQUIRED,
            "Labels, permissions, kill switch, branch/ruleset settings, and live workflow behavior must be verified in GitHub.",
        ),
        PilotReadinessCheck(
            "human-operating-model",
            ReadinessCheckState.EXTERNAL_REQUIRED,
            "Named owner, Security/SRE, and Developer Experience consent/review remain human operational facts.",
        ),
        PilotReadinessCheck(
            "external-evidence-retention",
            ReadinessCheckState.EXTERNAL_REQUIRED,
            "The declared immutable evidence destination must be verified and receive real pilot records.",
        ),
    )
    return PilotReadinessReport(
        state=PilotReadinessState.CONTRACT_READY,
        repository=manifest.repository,
        pilot_id=manifest.pilot_id,
        checks=checks,
        operator_actions=(
            "Verify the four reviewer labels and least-privilege workflow permissions in the target repository.",
            "Verify the kill switch and confirm the neutral shadow check is not required by branch protection/rulesets.",
            "Obtain accountable owner, Security/SRE, and Developer Experience approval for the named pilot scope.",
            "Verify the approved external evidence destination and retention/immutability controls.",
            "Run the shadow workflow and retain the first real observation before claiming the pilot is active.",
        ),
    )


def _not_ready(
    *,
    repository: str | None,
    pilot_id: str | None,
    detail: str,
    action: str,
    manifest: ShadowPilotManifest | None = None,
) -> PilotReadinessReport:
    checks: list[PilotReadinessCheck] = []
    if manifest is not None:
        checks.append(
            PilotReadinessCheck(
                "manifest-contract",
                ReadinessCheckState.PASS,
                "The named shadow-pilot manifest is valid.",
            )
        )
    checks.append(
        PilotReadinessCheck("repository-contract", ReadinessCheckState.FAIL, detail)
    )
    return PilotReadinessReport(
        state=PilotReadinessState.NOT_READY,
        repository=repository,
        pilot_id=pilot_id,
        checks=tuple(checks),
        operator_actions=(action,),
    )
