"""Build reviewable shadow-pilot files from operator-supplied facts.

The bootstrap fills only invariant platform controls (labels, least-privilege
workflow split, kill-switch semantics). Repository scope, accountable people,
and the external evidence destination must be supplied by the operator. The
result is validated by the same product contracts used at runtime and remains
non-authorizing until separately reviewed and installed in a target repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import parse_repository_config
from .contracts import PilotDataClassification if False else ProductMode
from .pilot import (
    EVALUATION_PERMISSIONS,
    OUTCOME_PERMISSIONS,
    PUBLISHER_PERMISSIONS,
    REPORT_PERMISSIONS,
    PilotDataClassification,
    ShadowPilotManifest,
    parse_shadow_pilot_manifest,
    validate_shadow_installation,
)


@dataclass(frozen=True)
class ShadowPilotBootstrapBundle:
    """Validated source files ready for human review, not installation proof."""

    manifest: ShadowPilotManifest
    runtime_configuration: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_payload(),
            "runtime_configuration": self.runtime_configuration,
            "advisory_or_enforcement_authorized": False,
            "operational_evidence_collected": False,
        }


def build_shadow_pilot_bundle(
    *,
    repository: str,
    service_ids: tuple[str, ...],
    owner_ids: tuple[str, ...],
    policy_version: str,
    data_classification: PilotDataClassification,
    evidence_system: str,
    evidence_locator: str,
    evidence_access_control_ref: str,
    evidence_immutability_control_ref: str,
    pilot_owner: str,
    security_reviewer: str,
    developer_experience_owner: str,
    pilot_id: str | None = None,
    reviewer_disposition_sla_hours: int = 72,
    hypercare_days: int = 14,
) -> ShadowPilotBootstrapBundle:
    """Create and cross-validate the two repository-local shadow contracts."""

    normalized_services = tuple(sorted(set(service_ids)))
    normalized_owners = tuple(sorted(set(owner_ids)))
    resolved_pilot_id = pilot_id or _pilot_id(repository)

    manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "pilot_id": resolved_pilot_id,
        "repository": repository,
        "service_ids": list(normalized_services),
        "owner_ids": list(normalized_owners),
        "evidence_sources": ["github-pull-request"],
        "policy_version": policy_version,
        "data_classification": data_classification.value,
        "mode": "shadow",
        "decision_impact": "advisory",
        "configuration_path": ".eip/pr-guardian.json",
        "minimum_shadow_observations": 30,
        "reviewer_labels": {
            "confirmed_risk": "eip-pr-guardian/confirmed-risk",
            "false_positive": "eip-pr-guardian/false-positive",
            "useful": "eip-pr-guardian/useful",
            "not_useful": "eip-pr-guardian/not-useful",
        },
        "workflow_controls": {
            "evaluation_permissions": list(EVALUATION_PERMISSIONS),
            "publisher_permissions": list(PUBLISHER_PERMISSIONS),
            "outcome_permissions": list(OUTCOME_PERMISSIONS),
            "report_permissions": list(REPORT_PERMISSIONS),
            "evaluation_has_write_token": False,
            "publisher_checks_out_pr_head": False,
            "outcome_checks_out_pr_head": False,
            "check_is_required": False,
        },
        "kill_switch_variable": "EIP_PR_GUARDIAN_KILL_SWITCH",
        "kill_switch_engaged_value": "true",
        "evidence_retention": {
            "system": evidence_system,
            "locator": evidence_locator,
            "retention_days": 90,
            "access_control_ref": evidence_access_control_ref,
            "immutability_control_ref": evidence_immutability_control_ref,
        },
        "operating_model": {
            "pilot_owner": pilot_owner,
            "security_reviewer": security_reviewer,
            "developer_experience_owner": developer_experience_owner,
            "reviewer_disposition_sla_hours": reviewer_disposition_sla_hours,
            "hypercare_days": hypercare_days,
        },
    }
    manifest = parse_shadow_pilot_manifest(manifest_payload)

    runtime_payload: dict[str, object] = {
        "repository": repository,
        "mode": ProductMode.SHADOW.value,
        "service_ids": list(normalized_services),
        "service_owners": list(normalized_owners),
        "evidence_sources": ["github-pull-request"],
        "policy_version": policy_version,
    }
    runtime = parse_repository_config(runtime_payload, repository=repository)
    validate_shadow_installation(manifest, runtime)
    return ShadowPilotBootstrapBundle(
        manifest=manifest,
        runtime_configuration=runtime_payload,
    )


def _pilot_id(repository: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", repository.casefold()).strip("-")
    return f"pr-guardian-{slug}"
