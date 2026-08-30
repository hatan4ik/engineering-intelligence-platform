"""Typed, validated configuration for the HTTP application process.

The web process is intentionally configured once at its composition root.
Routes and adapters receive these immutable records instead of rereading
``os.environ`` while serving a request.  This makes the effective capability
set inspectable, keeps tests explicit, and prevents two call sites from
normalising the same safety-critical setting differently.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping, TypeAlias, cast

from app.auth_mode import backend_mode
from control_plane.runtime import (
    REFERENCE_MODE,
    ControlPlaneConfigurationError,
    control_plane_mode,
)


BackendMode: TypeAlias = Literal["deterministic", "azure"]
AuthenticationMode: TypeAlias = Literal["entra", "api-key"]
ControlPlaneMode: TypeAlias = Literal["disabled", "reference", "temporal"]


class SettingsError(ValueError):
    """The process environment cannot safely describe the requested capability."""


def _optional(source: Mapping[str, str], name: str) -> str | None:
    value = source.get(name, "").strip()
    return value or None


def observability_endpoint_from_environment() -> str | None:
    """Read the one bootstrap input needed before router modules create tracers.

    OpenTelemetry must be configured before import-time tracer handles are
    requested. This narrow bootstrap read remains at the composition root;
    all request-serving configuration is parsed by ``ApplicationSettings`` at
    lifespan startup.
    """

    return _optional(os.environ, "OTEL_EXPORTER_OTLP_ENDPOINT")


def _required(source: Mapping[str, str], name: str) -> str:
    value = _optional(source, name)
    if value is None:
        raise SettingsError(f"{name} is required")
    return value


def _boolean(source: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw = _optional(source, name)
    if raw is None:
        return default
    normalized = raw.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise SettingsError(f"{name} must be true or false")


def _positive_int(source: Mapping[str, str], name: str, *, default: int) -> int:
    raw = _optional(source, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise SettingsError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise SettingsError(f"{name} must be a positive integer")
    return value


def _nonnegative_float(source: Mapping[str, str], name: str, *, default: float) -> float:
    raw = _optional(source, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise SettingsError(f"{name} must be a non-negative finite number") from error
    if not math.isfinite(value) or value < 0:
        raise SettingsError(f"{name} must be a non-negative finite number")
    return value


@dataclass(frozen=True)
class AuthenticationSettings:
    """Trusted identity configuration for the governed-query and portal routes."""

    mode: AuthenticationMode
    api_key_principals_json: str = field(repr=False)
    entra_tenant_id: str | None
    entra_audience: str | None
    entra_allowed_issuers: tuple[str, ...]
    entra_jwks_url: str | None

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "AuthenticationSettings":
        raw_mode = _optional(source, "EIP_AUTH_MODE") or "entra"
        normalized_mode = raw_mode.lower()
        if normalized_mode not in {"entra", "api-key"}:
            raise SettingsError("EIP_AUTH_MODE must be entra or api-key")
        tenant = _optional(source, "EIP_ENTRA_TENANT_ID")
        default_issuer = (
            f"https://login.microsoftonline.com/{tenant}/v2.0" if tenant is not None else None
        )
        issuers = tuple(
            item.strip()
            for item in (_optional(source, "EIP_ENTRA_ALLOWED_ISSUERS") or default_issuer or "").split(",")
            if item.strip()
        )
        mode: AuthenticationMode = "entra" if normalized_mode == "entra" else "api-key"
        return cls(
            mode=mode,
            api_key_principals_json=source.get("EIP_API_KEY_PRINCIPALS", "{}"),
            entra_tenant_id=tenant,
            entra_audience=_optional(source, "EIP_ENTRA_AUDIENCE"),
            entra_allowed_issuers=issuers,
            entra_jwks_url=(
                _optional(source, "EIP_ENTRA_JWKS_URL")
                or (
                    f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
                    if tenant is not None
                    else None
                )
            ),
        )

    def validate_for_authenticated_requests(self) -> None:
        """Reject incomplete identity configuration before it reaches a request path."""

        if self.mode == "entra":
            missing = [
                name
                for name, value in (
                    ("EIP_ENTRA_TENANT_ID", self.entra_tenant_id),
                    ("EIP_ENTRA_AUDIENCE", self.entra_audience),
                    ("EIP_ENTRA_ALLOWED_ISSUERS", self.entra_allowed_issuers),
                    ("EIP_ENTRA_JWKS_URL", self.entra_jwks_url),
                )
                if not value
            ]
            if missing:
                raise SettingsError(
                    "authenticated requests require " + ", ".join(missing)
                )
            return

        try:
            parsed: object = json.loads(self.api_key_principals_json)
        except json.JSONDecodeError as error:
            raise SettingsError("EIP_API_KEY_PRINCIPALS must be valid JSON") from error
        if not isinstance(parsed, dict):
            raise SettingsError("EIP_API_KEY_PRINCIPALS must be a JSON object")


@dataclass(frozen=True)
class AzureRagSettings:
    """All Azure RAG adapter inputs, parsed before the adapter is constructed."""

    search_endpoint: str
    search_index: str
    openai_endpoint: str
    chat_deployment: str
    advanced_chat_deployment: str | None
    embedding_deployment: str | None
    openai_api_version: str
    search_semantic_configuration: str
    input_per_million_tokens_usd: float
    output_per_million_tokens_usd: float
    search_per_1000_queries_usd: float
    tool_call_usd: float

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "AzureRagSettings":
        standard_deployment = (
            _optional(source, "AZURE_OPENAI_CHAT_DEPLOYMENT_STANDARD")
            or _optional(source, "AZURE_OPENAI_CHAT_DEPLOYMENT")
        )
        if standard_deployment is None:
            raise SettingsError(
                "AZURE_OPENAI_CHAT_DEPLOYMENT_STANDARD or AZURE_OPENAI_CHAT_DEPLOYMENT is required"
            )
        return cls(
            search_endpoint=_required(source, "AZURE_SEARCH_ENDPOINT"),
            search_index=_required(source, "AZURE_SEARCH_INDEX"),
            openai_endpoint=_required(source, "AZURE_OPENAI_ENDPOINT"),
            chat_deployment=standard_deployment,
            advanced_chat_deployment=_optional(source, "AZURE_OPENAI_CHAT_DEPLOYMENT_ADVANCED"),
            embedding_deployment=_optional(source, "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            openai_api_version=_optional(source, "AZURE_OPENAI_API_VERSION") or "2024-10-21",
            search_semantic_configuration=(
                _optional(source, "AZURE_SEARCH_SEMANTIC_CONFIG") or "default"
            ),
            input_per_million_tokens_usd=_nonnegative_float(
                source, "EIP_COST_INPUT_PER_MILLION_TOKENS_USD", default=0.0
            ),
            output_per_million_tokens_usd=_nonnegative_float(
                source, "EIP_COST_OUTPUT_PER_MILLION_TOKENS_USD", default=0.0
            ),
            search_per_1000_queries_usd=_nonnegative_float(
                source, "EIP_COST_SEARCH_PER_1000_QUERIES_USD", default=0.0
            ),
            tool_call_usd=_nonnegative_float(source, "EIP_COST_TOOL_CALL_USD", default=0.0),
        )

    def deployment_for(self, model_tier: str) -> str:
        if model_tier == "advanced" and self.advanced_chat_deployment is not None:
            return self.advanced_chat_deployment
        return self.chat_deployment


@dataclass(frozen=True)
class QuerySettings:
    """Configuration consumed by every governed-query route invocation."""

    backend: BackendMode
    allow_header_identity: bool
    estimated_request_usd: float
    authentication: AuthenticationSettings
    azure_rag: AzureRagSettings | None

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "QuerySettings":
        raw_backend = backend_mode(source)
        if raw_backend not in {"deterministic", "azure"}:
            raise SettingsError("EIP_BACKEND must be deterministic or azure")
        backend: BackendMode = "deterministic" if raw_backend == "deterministic" else "azure"
        return cls(
            backend=backend,
            allow_header_identity=_boolean(
                source,
                "EIP_ALLOW_HEADER_IDENTITY",
                default=backend == "deterministic",
            ),
            estimated_request_usd=_nonnegative_float(
                source, "EIP_ESTIMATED_REQUEST_USD", default=0.05
            ),
            authentication=AuthenticationSettings.from_mapping(source),
            azure_rag=AzureRagSettings.from_mapping(source) if backend == "azure" else None,
        )

    @property
    def header_identity_permitted(self) -> bool:
        """Header assertions are never an identity source for real Azure data."""

        return self.backend == "deterministic" and self.allow_header_identity

    @property
    def header_identity_refusal_reason(self) -> str | None:
        if self.backend == "azure":
            return (
                "header identity is not permitted with the Azure backend; "
                "configure Entra JWT or API-key authentication"
            )
        return None

    def validate(self) -> None:
        if self.backend == "azure" and self.azure_rag is None:
            raise SettingsError("Azure backend requires Azure RAG configuration")
        if not self.header_identity_permitted:
            self.authentication.validate_for_authenticated_requests()


@dataclass(frozen=True)
class RuntimeSafetySettings:
    """Safety controls parsed once for the HTTP process.

    Helm exposes these as process environment variables. They establish the
    initial state of a pod; changing one requires a replacement pod rather
    than implying a live control-plane API exists.
    """

    control_plane_mode: ControlPlaneMode
    autonomy_kill_switch_engaged: bool
    pr_guardian_kill_switch_engaged: bool
    opa_evaluator_required: bool
    kill_switch_update: Literal["restart-required"] = "restart-required"

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "RuntimeSafetySettings":
        try:
            mode = control_plane_mode(source)
        except ControlPlaneConfigurationError as error:
            raise SettingsError(str(error)) from error
        requested_opa_evaluator = _boolean(source, "EIP_REQUIRE_OPA", default=False)
        return cls(
            control_plane_mode=cast(ControlPlaneMode, mode),
            autonomy_kill_switch_engaged=_boolean(
                source, "EIP_AUTONOMY_KILL_SWITCH", default=False
            ),
            pr_guardian_kill_switch_engaged=_boolean(
                source, "EIP_PR_GUARDIAN_KILL_SWITCH", default=False
            ),
            opa_evaluator_required=(
                mode != REFERENCE_MODE
                or requested_opa_evaluator
            ),
        )


@dataclass(frozen=True)
class PRGuardianSettings:
    """Runtime inputs for the optional, shadow-only PR Guardian capability."""

    enabled: bool
    github_token: str | None = field(repr=False)
    state_directory: Path | None
    service_graph_root: Path | None
    policy_version: str
    company_brain_database: Path | None
    company_brain_tenant: str | None
    principal_groups: tuple[str, ...]

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "PRGuardianSettings":
        state_directory = _optional(source, "EIP_STATE_DIR")
        database = _optional(source, "EIP_COMPANY_BRAIN_DB")
        return cls(
            enabled=(_optional(source, "EIP_PR_GUARDIAN_WEBHOOK") or "").lower() == "enabled",
            github_token=_optional(source, "GITHUB_TOKEN"),
            state_directory=Path(state_directory) if state_directory is not None else None,
            service_graph_root=(
                Path(value)
                if (value := _optional(source, "EIP_SERVICE_GRAPH_ROOT")) is not None
                else None
            ),
            policy_version=_optional(source, "EIP_PR_GUARDIAN_POLICY_VERSION") or "pr-policy-v1",
            company_brain_database=Path(database) if database is not None else None,
            company_brain_tenant=_optional(source, "EIP_COMPANY_BRAIN_TENANT"),
            principal_groups=tuple(
                sorted(
                    {
                        item.strip()
                        for item in (_optional(source, "EIP_PR_GUARDIAN_PRINCIPAL_GROUPS") or "").split(",")
                        if item.strip()
                    }
                )
            ),
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        missing = [
            name
            for name, value in (
                ("GITHUB_TOKEN", self.github_token),
                ("EIP_STATE_DIR", self.state_directory),
                ("EIP_SERVICE_GRAPH_ROOT", self.service_graph_root),
            )
            if value is None
        ]
        if missing:
            raise SettingsError(
                "EIP_PR_GUARDIAN_WEBHOOK=enabled requires " + ", ".join(missing)
            )
        company_brain_values = (
            self.company_brain_database,
            self.company_brain_tenant,
            self.principal_groups,
        )
        if any(company_brain_values) and not all(company_brain_values):
            raise SettingsError(
                "Company Brain PR Guardian context requires EIP_COMPANY_BRAIN_DB, "
                "EIP_COMPANY_BRAIN_TENANT, EIP_PR_GUARDIAN_PRINCIPAL_GROUPS"
            )


@dataclass(frozen=True)
class OperationsSettings:
    """Runtime inputs for the optional L1/L2 operational-intelligence capability."""

    webhook_secret: str | None = field(repr=False)
    evidence_mode: str | None
    state_directory: Path | None
    topology_database: Path | None
    azure_tenant_id: str | None
    azure_client_id: str | None
    log_analytics_workspace_id: str | None
    evidence_lookback_minutes: int
    evidence_kql: str | None

    @property
    def enabled(self) -> bool:
        return self.webhook_secret is not None or self.evidence_mode is not None

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "OperationsSettings":
        state_directory = _optional(source, "EIP_STATE_DIR")
        topology_database = _optional(source, "EIP_TOPOLOGY_DB")
        return cls(
            webhook_secret=_optional(source, "EIP_OPERATIONS_WEBHOOK_SECRET"),
            evidence_mode=_optional(source, "EIP_OPERATIONS_EVIDENCE"),
            state_directory=Path(state_directory) if state_directory is not None else None,
            topology_database=(Path(topology_database) if topology_database is not None else None),
            azure_tenant_id=_optional(source, "AZURE_TENANT_ID"),
            azure_client_id=_optional(source, "AZURE_CLIENT_ID"),
            log_analytics_workspace_id=_optional(
                source, "EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID"
            ),
            evidence_lookback_minutes=_positive_int(
                source, "EIP_OPERATIONS_EVIDENCE_LOOKBACK_MINUTES", default=120
            ),
            evidence_kql=_optional(source, "EIP_OPERATIONS_EVIDENCE_KQL"),
        )

    def validate(self, *, require_webhook_secret: bool = True) -> None:
        if not self.enabled:
            return
        required = (
            (
                ("EIP_OPERATIONS_WEBHOOK_SECRET", self.webhook_secret),
                ("EIP_OPERATIONS_EVIDENCE", self.evidence_mode),
                ("EIP_STATE_DIR", self.state_directory),
            )
            if require_webhook_secret
            else (
                ("EIP_OPERATIONS_EVIDENCE", self.evidence_mode),
                ("EIP_STATE_DIR", self.state_directory),
            )
        )
        missing = [
            name
            for name, value in required
            if value is None
        ]
        mode = self.evidence_mode
        if mode is not None and mode != "azure-monitor" and not mode.startswith("fixture:"):
            raise SettingsError(
                "EIP_OPERATIONS_EVIDENCE must be 'azure-monitor' or 'fixture:<path>'"
            )
        if mode == "azure-monitor":
            missing.extend(
                name
                for name, value in (
                    ("AZURE_TENANT_ID", self.azure_tenant_id),
                    ("AZURE_CLIENT_ID", self.azure_client_id),
                    (
                        "EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID",
                        self.log_analytics_workspace_id,
                    ),
                )
                if value is None
            )
        if mode is not None and mode.startswith("fixture:") and not mode.split(":", 1)[1].strip():
            missing.append("EIP_OPERATIONS_EVIDENCE fixture path")
        if missing:
            raise SettingsError(
                "operational intelligence requires " + ", ".join(dict.fromkeys(missing))
            )


@dataclass(frozen=True)
class ApplicationSettings:
    """The complete immutable configuration accepted by the HTTP application."""

    query: QuerySettings
    runtime: RuntimeSafetySettings
    github_webhook_secret: str | None = field(repr=False)
    feedback_database: Path | None
    pr_guardian: PRGuardianSettings
    operations: OperationsSettings

    @classmethod
    def from_environment(cls) -> "ApplicationSettings":
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "ApplicationSettings":
        settings = cls(
            query=QuerySettings.from_mapping(source),
            runtime=RuntimeSafetySettings.from_mapping(source),
            github_webhook_secret=_optional(source, "EIP_GITHUB_WEBHOOK_SECRET"),
            feedback_database=(
                Path(value)
                if (value := _optional(source, "EIP_FEEDBACK_DB")) is not None
                else None
            ),
            pr_guardian=PRGuardianSettings.from_mapping(source),
            operations=OperationsSettings.from_mapping(source),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        self.query.validate()
        self.pr_guardian.validate()
        self.operations.validate()


def settings_for_application(application: object) -> ApplicationSettings:
    """Get the immutable settings record bound during startup or injection.

    Serving a request before lifespan startup is an integration error, not an
    excuse to read a potentially changed process environment.  Tests and
    embedding hosts can either enter lifespan or pass ``create_app(settings)``.
    """

    state = getattr(application, "state", None)
    configured = getattr(state, "eip_settings", None)
    if isinstance(configured, ApplicationSettings):
        return configured
    raise SettingsError(
        "application settings are not bound; start the ASGI lifespan or pass explicit settings"
    )
