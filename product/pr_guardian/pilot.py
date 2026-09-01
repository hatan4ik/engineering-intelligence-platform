"""Non-authorizing onboarding contract for a PR Guardian shadow pilot.

The runtime configuration tells PR Guardian what a repository has enabled.
This module is intentionally separate: it records the operational controls a
named pilot must plan before it is enabled, then verifies that its runtime
configuration remains in shadow mode.  Neither a manifest nor this validator
can enable a workflow, change a repository setting, or authorize advisory or
enforcement publishing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Mapping, Sequence

from .contracts import ProductContractError, ProductMode, RepositoryConfig


PILOT_MANIFEST_RELATIVE_PATH = ".eip/pr-guardian-shadow-pilot.json"
RUNTIME_CONFIG_RELATIVE_PATH: Literal[".eip/pr-guardian.json"] = ".eip/pr-guardian.json"
KILL_SWITCH_VARIABLE = "EIP_PR_GUARDIAN_KILL_SWITCH"
MINIMUM_EVIDENCE_RETENTION_DAYS = 90
MINIMUM_SHADOW_OBSERVATIONS = 30

EVALUATION_PERMISSIONS = ("contents:read", "pull-requests:read")
PUBLISHER_PERMISSIONS = (
    "actions:read",
    "checks:write",
    "contents:read",
    "issues:write",
    "pull-requests:write",
)
OUTCOME_PERMISSIONS = ("contents:read", "issues:write", "pull-requests:read")
REPORT_PERMISSIONS = ("actions:read", "contents:read")

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PILOT_ID = re.compile(r"^pr-guardian-[a-z0-9][a-z0-9-]{2,79}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@/-]{0,159}$")
_PLACEHOLDER_PARTS = frozenset({"example", "replace", "tbd", "todo", "undeclared"})


class ShadowPilotContractError(ProductContractError):
    """A shadow-pilot onboarding record lacks a required safety control."""


class PilotDataClassification(StrEnum):
    """Classifications the initial PR Guardian pilot may declare explicitly."""

    INTERNAL = "internal"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class ShadowReviewerLabels:
    """The exact reviewer inputs understood by the outcome workflow."""

    confirmed_risk: str
    false_positive: str
    useful: str
    not_useful: str

    def __post_init__(self) -> None:
        expected = {
            "confirmed_risk": "eip-pr-guardian/confirmed-risk",
            "false_positive": "eip-pr-guardian/false-positive",
            "useful": "eip-pr-guardian/useful",
            "not_useful": "eip-pr-guardian/not-useful",
        }
        actual = {
            "confirmed_risk": self.confirmed_risk,
            "false_positive": self.false_positive,
            "useful": self.useful,
            "not_useful": self.not_useful,
        }
        if actual != expected:
            raise ShadowPilotContractError(
                "reviewer_labels must use the four checked-in PR Guardian label names"
            )

    def to_payload(self) -> dict[str, str]:
        return {
            "confirmed_risk": self.confirmed_risk,
            "false_positive": self.false_positive,
            "useful": self.useful,
            "not_useful": self.not_useful,
        }


@dataclass(frozen=True)
class ShadowWorkflowControls:
    """The least-privilege and trust split required for a shadow installation."""

    evaluation_permissions: tuple[str, ...]
    publisher_permissions: tuple[str, ...]
    outcome_permissions: tuple[str, ...]
    report_permissions: tuple[str, ...]
    evaluation_has_write_token: Literal[False]
    publisher_checks_out_pr_head: Literal[False]
    outcome_checks_out_pr_head: Literal[False]
    check_is_required: Literal[False]

    def __post_init__(self) -> None:
        expected = {
            "evaluation_permissions": EVALUATION_PERMISSIONS,
            "publisher_permissions": PUBLISHER_PERMISSIONS,
            "outcome_permissions": OUTCOME_PERMISSIONS,
            "report_permissions": REPORT_PERMISSIONS,
        }
        actual = {
            "evaluation_permissions": self.evaluation_permissions,
            "publisher_permissions": self.publisher_permissions,
            "outcome_permissions": self.outcome_permissions,
            "report_permissions": self.report_permissions,
        }
        if actual != expected:
            raise ShadowPilotContractError(
                "workflow_controls permissions do not match the reviewed shadow workflow split"
            )
        if any(
            value is not False
            for value in (
                self.evaluation_has_write_token,
                self.publisher_checks_out_pr_head,
                self.outcome_checks_out_pr_head,
                self.check_is_required,
            )
        ):
            raise ShadowPilotContractError(
                "shadow workflow controls may not grant write evaluation, execute PR head, or require a check"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "evaluation_permissions": list(self.evaluation_permissions),
            "publisher_permissions": list(self.publisher_permissions),
            "outcome_permissions": list(self.outcome_permissions),
            "report_permissions": list(self.report_permissions),
            "evaluation_has_write_token": self.evaluation_has_write_token,
            "publisher_checks_out_pr_head": self.publisher_checks_out_pr_head,
            "outcome_checks_out_pr_head": self.outcome_checks_out_pr_head,
            "check_is_required": self.check_is_required,
        }


@dataclass(frozen=True)
class PilotEvidenceRetention:
    """A declared external evidence destination, not evidence that export succeeded."""

    system: str
    locator: str
    retention_days: int
    access_control_ref: str
    immutability_control_ref: str

    def __post_init__(self) -> None:
        _text(self.system, "evidence_retention.system", maximum=160)
        _text(self.locator, "evidence_retention.locator", maximum=500)
        _text(
            self.access_control_ref,
            "evidence_retention.access_control_ref",
            maximum=500,
        )
        _text(
            self.immutability_control_ref,
            "evidence_retention.immutability_control_ref",
            maximum=500,
        )
        if (
            type(self.retention_days) is not int
            or self.retention_days < MINIMUM_EVIDENCE_RETENTION_DAYS
        ):
            raise ShadowPilotContractError(
                f"evidence_retention.retention_days must be an integer >= {MINIMUM_EVIDENCE_RETENTION_DAYS}"
            )
        combined = f"{self.system} {self.locator}".casefold()
        if (
            "github actions" in combined
            or "github-actions" in combined
            or "/actions/runs/" in combined
        ):
            raise ShadowPilotContractError(
                "evidence_retention must name an approved external evidence system, not an Actions artifact"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "system": self.system,
            "locator": self.locator,
            "retention_days": self.retention_days,
            "access_control_ref": self.access_control_ref,
            "immutability_control_ref": self.immutability_control_ref,
        }


@dataclass(frozen=True)
class ShadowPilotOperatingModel:
    """Named human handoffs for a pilot; names are not treated as approvals."""

    pilot_owner: str
    security_reviewer: str
    developer_experience_owner: str
    reviewer_disposition_sla_hours: int
    hypercare_days: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.pilot_owner, "operating_model.pilot_owner"),
            (self.security_reviewer, "operating_model.security_reviewer"),
            (
                self.developer_experience_owner,
                "operating_model.developer_experience_owner",
            ),
        ):
            _named_identifier(value, label)
        if (
            type(self.reviewer_disposition_sla_hours) is not int
            or not 1 <= self.reviewer_disposition_sla_hours <= 24 * 14
        ):
            raise ShadowPilotContractError(
                "operating_model.reviewer_disposition_sla_hours must be in [1, 336]"
            )
        if type(self.hypercare_days) is not int or not 1 <= self.hypercare_days <= 90:
            raise ShadowPilotContractError(
                "operating_model.hypercare_days must be in [1, 90]"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "pilot_owner": self.pilot_owner,
            "security_reviewer": self.security_reviewer,
            "developer_experience_owner": self.developer_experience_owner,
            "reviewer_disposition_sla_hours": self.reviewer_disposition_sla_hours,
            "hypercare_days": self.hypercare_days,
        }


@dataclass(frozen=True)
class ShadowPilotManifest:
    """One named, non-enforcing PR Guardian pilot scope.

    ``mode`` and ``decision_impact`` are literal types and checked at runtime.
    They deliberately make advisory/enforcement installation invalid here.
    """

    pilot_id: str
    repository: str
    service_ids: tuple[str, ...]
    owner_ids: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    policy_version: str
    data_classification: PilotDataClassification
    reviewer_labels: ShadowReviewerLabels
    workflow_controls: ShadowWorkflowControls
    kill_switch_variable: str
    kill_switch_engaged_value: str
    evidence_retention: PilotEvidenceRetention
    operating_model: ShadowPilotOperatingModel
    schema_version: Literal[1] = 1
    mode: Literal["shadow"] = "shadow"
    decision_impact: Literal["advisory"] = "advisory"
    configuration_path: Literal[".eip/pr-guardian.json"] = RUNTIME_CONFIG_RELATIVE_PATH
    minimum_shadow_observations: int = MINIMUM_SHADOW_OBSERVATIONS

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ShadowPilotContractError("shadow pilot schema_version must be 1")
        if not _PILOT_ID.fullmatch(_text(self.pilot_id, "pilot_id", maximum=80)):
            raise ShadowPilotContractError(
                "pilot_id must be pr-guardian- followed by lowercase words"
            )
        if not _REPOSITORY.fullmatch(_text(self.repository, "repository", maximum=200)):
            raise ShadowPilotContractError("repository is invalid")
        _named_identifiers(self.service_ids, "service_ids")
        _named_identifiers(self.owner_ids, "owner_ids")
        _named_identifiers(self.evidence_sources, "evidence_sources")
        if "github-pull-request" not in self.evidence_sources:
            raise ShadowPilotContractError(
                "evidence_sources must include github-pull-request"
            )
        _text(self.policy_version, "policy_version", maximum=120)
        if not isinstance(self.data_classification, PilotDataClassification):
            raise ShadowPilotContractError("data_classification is invalid")
        if not isinstance(self.reviewer_labels, ShadowReviewerLabels):
            raise ShadowPilotContractError("reviewer_labels is invalid")
        if not isinstance(self.workflow_controls, ShadowWorkflowControls):
            raise ShadowPilotContractError("workflow_controls is invalid")
        if self.kill_switch_variable != KILL_SWITCH_VARIABLE:
            raise ShadowPilotContractError(
                f"kill_switch_variable must be {KILL_SWITCH_VARIABLE}"
            )
        if self.kill_switch_engaged_value != "true":
            raise ShadowPilotContractError(
                "kill_switch_engaged_value must be the exact value 'true'"
            )
        if not isinstance(self.evidence_retention, PilotEvidenceRetention):
            raise ShadowPilotContractError("evidence_retention is invalid")
        if not isinstance(self.operating_model, ShadowPilotOperatingModel):
            raise ShadowPilotContractError("operating_model is invalid")
        if self.mode != "shadow" or self.decision_impact != "advisory":
            raise ShadowPilotContractError(
                "a shadow pilot may describe only shadow-mode advisory feedback"
            )
        if self.configuration_path != RUNTIME_CONFIG_RELATIVE_PATH:
            raise ShadowPilotContractError(
                f"configuration_path must be {RUNTIME_CONFIG_RELATIVE_PATH}"
            )
        if self.minimum_shadow_observations != MINIMUM_SHADOW_OBSERVATIONS:
            raise ShadowPilotContractError(
                f"minimum_shadow_observations must be {MINIMUM_SHADOW_OBSERVATIONS}"
            )

    @property
    def advisory_or_enforcement_authorized(self) -> Literal[False]:
        """A manifest is planning metadata and cannot grant product authority."""

        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pilot_id": self.pilot_id,
            "repository": self.repository,
            "service_ids": list(self.service_ids),
            "owner_ids": list(self.owner_ids),
            "evidence_sources": list(self.evidence_sources),
            "policy_version": self.policy_version,
            "data_classification": self.data_classification.value,
            "mode": self.mode,
            "decision_impact": self.decision_impact,
            "configuration_path": self.configuration_path,
            "minimum_shadow_observations": self.minimum_shadow_observations,
            "reviewer_labels": self.reviewer_labels.to_payload(),
            "workflow_controls": self.workflow_controls.to_payload(),
            "kill_switch_variable": self.kill_switch_variable,
            "kill_switch_engaged_value": self.kill_switch_engaged_value,
            "evidence_retention": self.evidence_retention.to_payload(),
            "operating_model": self.operating_model.to_payload(),
        }


_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_id",
        "repository",
        "service_ids",
        "owner_ids",
        "evidence_sources",
        "policy_version",
        "data_classification",
        "mode",
        "decision_impact",
        "configuration_path",
        "minimum_shadow_observations",
        "reviewer_labels",
        "workflow_controls",
        "kill_switch_variable",
        "kill_switch_engaged_value",
        "evidence_retention",
        "operating_model",
    }
)


def parse_shadow_pilot_manifest(payload: object) -> ShadowPilotManifest:
    """Parse exact JSON-shaped onboarding data into a non-authorizing contract."""

    raw = _mapping(payload, "shadow pilot manifest")
    _exact_keys(raw, _FIELDS, "shadow pilot manifest")
    classification = _text(
        raw.get("data_classification"), "data_classification", maximum=40
    )
    try:
        data_classification = PilotDataClassification(classification)
    except ValueError as error:
        raise ShadowPilotContractError("data_classification is invalid") from error
    return ShadowPilotManifest(
        schema_version=_literal_one(raw.get("schema_version"), "schema_version"),
        pilot_id=_text(raw.get("pilot_id"), "pilot_id", maximum=80),
        repository=_text(raw.get("repository"), "repository", maximum=200),
        service_ids=_identifier_list(raw.get("service_ids"), "service_ids"),
        owner_ids=_identifier_list(raw.get("owner_ids"), "owner_ids"),
        evidence_sources=_identifier_list(
            raw.get("evidence_sources"), "evidence_sources"
        ),
        policy_version=_text(raw.get("policy_version"), "policy_version", maximum=120),
        data_classification=data_classification,
        mode=_shadow_mode(raw.get("mode")),
        decision_impact=_advisory_impact(raw.get("decision_impact")),
        configuration_path=_runtime_configuration_path(raw.get("configuration_path")),
        minimum_shadow_observations=_positive_int(
            raw.get("minimum_shadow_observations"), "minimum_shadow_observations"
        ),
        reviewer_labels=_reviewer_labels(raw.get("reviewer_labels")),
        workflow_controls=_workflow_controls(raw.get("workflow_controls")),
        kill_switch_variable=_text(
            raw.get("kill_switch_variable"), "kill_switch_variable", maximum=120
        ),
        kill_switch_engaged_value=_text(
            raw.get("kill_switch_engaged_value"),
            "kill_switch_engaged_value",
            maximum=20,
        ),
        evidence_retention=_evidence_retention(raw.get("evidence_retention")),
        operating_model=_operating_model(raw.get("operating_model")),
    )


def validate_shadow_installation(
    manifest: ShadowPilotManifest, configuration: RepositoryConfig
) -> None:
    """Verify a named pilot's repository-owned config cannot exceed shadow mode."""

    if configuration.mode is not ProductMode.SHADOW:
        raise ShadowPilotContractError(
            "a shadow pilot requires RepositoryConfig.mode=shadow"
        )
    for field, configured, planned in (
        ("repository", configuration.repository, manifest.repository),
        ("service_ids", configuration.service_ids, manifest.service_ids),
        ("owner_ids", configuration.owner_ids, manifest.owner_ids),
        ("evidence_sources", configuration.evidence_sources, manifest.evidence_sources),
        ("policy_version", configuration.policy_version, manifest.policy_version),
    ):
        if configured != planned:
            raise ShadowPilotContractError(
                f"repository configuration {field} does not match the reviewed pilot manifest"
            )


def _reviewer_labels(value: object) -> ShadowReviewerLabels:
    raw = _mapping(value, "reviewer_labels")
    _exact_keys(
        raw,
        {"confirmed_risk", "false_positive", "useful", "not_useful"},
        "reviewer_labels",
    )
    return ShadowReviewerLabels(
        confirmed_risk=_text(
            raw.get("confirmed_risk"), "reviewer_labels.confirmed_risk", maximum=120
        ),
        false_positive=_text(
            raw.get("false_positive"), "reviewer_labels.false_positive", maximum=120
        ),
        useful=_text(raw.get("useful"), "reviewer_labels.useful", maximum=120),
        not_useful=_text(
            raw.get("not_useful"), "reviewer_labels.not_useful", maximum=120
        ),
    )


def _workflow_controls(value: object) -> ShadowWorkflowControls:
    raw = _mapping(value, "workflow_controls")
    _exact_keys(
        raw,
        {
            "evaluation_permissions",
            "publisher_permissions",
            "outcome_permissions",
            "report_permissions",
            "evaluation_has_write_token",
            "publisher_checks_out_pr_head",
            "outcome_checks_out_pr_head",
            "check_is_required",
        },
        "workflow_controls",
    )
    return ShadowWorkflowControls(
        evaluation_permissions=_permission_list(
            raw.get("evaluation_permissions"),
            "workflow_controls.evaluation_permissions",
        ),
        publisher_permissions=_permission_list(
            raw.get("publisher_permissions"), "workflow_controls.publisher_permissions"
        ),
        outcome_permissions=_permission_list(
            raw.get("outcome_permissions"), "workflow_controls.outcome_permissions"
        ),
        report_permissions=_permission_list(
            raw.get("report_permissions"), "workflow_controls.report_permissions"
        ),
        evaluation_has_write_token=_false(
            raw.get("evaluation_has_write_token"),
            "workflow_controls.evaluation_has_write_token",
        ),
        publisher_checks_out_pr_head=_false(
            raw.get("publisher_checks_out_pr_head"),
            "workflow_controls.publisher_checks_out_pr_head",
        ),
        outcome_checks_out_pr_head=_false(
            raw.get("outcome_checks_out_pr_head"),
            "workflow_controls.outcome_checks_out_pr_head",
        ),
        check_is_required=_false(
            raw.get("check_is_required"), "workflow_controls.check_is_required"
        ),
    )


def _evidence_retention(value: object) -> PilotEvidenceRetention:
    raw = _mapping(value, "evidence_retention")
    _exact_keys(
        raw,
        {
            "system",
            "locator",
            "retention_days",
            "access_control_ref",
            "immutability_control_ref",
        },
        "evidence_retention",
    )
    return PilotEvidenceRetention(
        system=_text(raw.get("system"), "evidence_retention.system", maximum=160),
        locator=_text(raw.get("locator"), "evidence_retention.locator", maximum=500),
        retention_days=_positive_int(
            raw.get("retention_days"), "evidence_retention.retention_days"
        ),
        access_control_ref=_text(
            raw.get("access_control_ref"),
            "evidence_retention.access_control_ref",
            maximum=500,
        ),
        immutability_control_ref=_text(
            raw.get("immutability_control_ref"),
            "evidence_retention.immutability_control_ref",
            maximum=500,
        ),
    )


def _operating_model(value: object) -> ShadowPilotOperatingModel:
    raw = _mapping(value, "operating_model")
    _exact_keys(
        raw,
        {
            "pilot_owner",
            "security_reviewer",
            "developer_experience_owner",
            "reviewer_disposition_sla_hours",
            "hypercare_days",
        },
        "operating_model",
    )
    return ShadowPilotOperatingModel(
        pilot_owner=_text(
            raw.get("pilot_owner"), "operating_model.pilot_owner", maximum=160
        ),
        security_reviewer=_text(
            raw.get("security_reviewer"),
            "operating_model.security_reviewer",
            maximum=160,
        ),
        developer_experience_owner=_text(
            raw.get("developer_experience_owner"),
            "operating_model.developer_experience_owner",
            maximum=160,
        ),
        reviewer_disposition_sla_hours=_positive_int(
            raw.get("reviewer_disposition_sla_hours"),
            "operating_model.reviewer_disposition_sla_hours",
        ),
        hypercare_days=_positive_int(
            raw.get("hypercare_days"), "operating_model.hypercare_days"
        ),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ShadowPilotContractError(f"{label} must be a JSON object")
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str] | set[str], label: str
) -> None:
    if set(value) != set(expected):
        raise ShadowPilotContractError(f"{label} has unexpected or missing fields")


def _text(value: object, label: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\n" in value
    ):
        raise ShadowPilotContractError(f"{label} is invalid")
    return value


def _named_identifier(value: object, label: str) -> str:
    text = _text(value, label, maximum=160)
    if not _IDENTIFIER.fullmatch(text):
        raise ShadowPilotContractError(f"{label} is invalid")
    if any(part in text.casefold() for part in _PLACEHOLDER_PARTS):
        raise ShadowPilotContractError(
            f"{label} must name a real accountable identity, not a placeholder"
        )
    return text


def _named_identifiers(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not values or values != tuple(sorted(set(values))):
        raise ShadowPilotContractError(f"{label} must be non-empty, sorted, and unique")
    return tuple(_named_identifier(value, label) for value in values)


def _identifier_list(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ShadowPilotContractError(f"{label} must be a non-empty JSON array")
    values = tuple(_named_identifier(item, label) for item in value)
    if values != tuple(sorted(set(values))):
        raise ShadowPilotContractError(f"{label} must be sorted and unique")
    return values


def _permission_list(value: object, label: str) -> tuple[str, ...]:
    """Parse permission tokens before comparing them with the exact profiles."""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ShadowPilotContractError(f"{label} must be a non-empty JSON array")
    values = tuple(_text(item, label, maximum=80) for item in value)
    if values != tuple(sorted(set(values))):
        raise ShadowPilotContractError(f"{label} must be sorted and unique")
    return values


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ShadowPilotContractError(f"{label} must be a positive integer")
    return value


def _literal_one(value: object, label: str) -> Literal[1]:
    if value != 1 or type(value) is not int:
        raise ShadowPilotContractError(f"{label} must be 1")
    return 1


def _shadow_mode(value: object) -> Literal["shadow"]:
    if value != "shadow":
        raise ShadowPilotContractError("mode must be shadow")
    return "shadow"


def _advisory_impact(value: object) -> Literal["advisory"]:
    if value != "advisory":
        raise ShadowPilotContractError("decision_impact must be advisory")
    return "advisory"


def _runtime_configuration_path(value: object) -> Literal[".eip/pr-guardian.json"]:
    if value != RUNTIME_CONFIG_RELATIVE_PATH:
        raise ShadowPilotContractError(
            f"configuration_path must be {RUNTIME_CONFIG_RELATIVE_PATH}"
        )
    return RUNTIME_CONFIG_RELATIVE_PATH


def _false(value: object, label: str) -> Literal[False]:
    if value is not False:
        raise ShadowPilotContractError(f"{label} must be false")
    return False
