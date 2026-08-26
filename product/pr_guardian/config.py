"""Read the repository-owned PR Guardian configuration.

The file lives in the evaluated repository at ``.eip/pr-guardian.json``.  JSON
was chosen over YAML deliberately: the runtime has no YAML parser and this
package must not add a dependency to read a policy file.

The platform never writes this file and never upgrades a repository's mode.
An absent file means ``shadow``; anything else is a decision the repository's
own service owners recorded, reviewed through their own pull-request process.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import (
    EnforcementPolicy,
    EnforcementRule,
    EnforcementWaiver,
    ProductContractError,
    ProductMode,
    RepositoryConfig,
)


CONFIG_RELATIVE_PATH = ".eip/pr-guardian.json"

# An absent configuration file declares nothing: no owner, no service, and no
# evidence source.  The sentinel keeps the contract honest instead of inventing
# a plausible-looking owner for a repository that never named one.
UNDECLARED = "undeclared"

DEFAULT_EVIDENCE_SOURCES = ("github-pull-request",)

_TOP_LEVEL_FIELDS = frozenset({
    "repository", "mode", "service_ids", "service_owners", "evidence_sources",
    "policy_version", "enforcement",
})
_ENFORCEMENT_FIELDS = frozenset({
    "rule", "threshold", "approved_by", "approved_on", "expires_on", "waivers",
})
_WAIVER_FIELDS = frozenset({"path_glob", "reason", "owner", "expires_on"})


def default_shadow_config(repository: str) -> RepositoryConfig:
    """The mode a repository has when it has told us nothing at all."""
    return RepositoryConfig(
        repository=repository,
        service_ids=(UNDECLARED,),
        owner_ids=(UNDECLARED,),
        evidence_sources=(UNDECLARED,),
        policy_version=UNDECLARED,
        mode=ProductMode.SHADOW,
    )


def config_path(root: str | Path = ".") -> Path:
    return Path(root) / CONFIG_RELATIVE_PATH


def load_effective_config(
    root: str | Path = ".",
    *,
    repository: str,
    now: date | None = None,
) -> tuple[RepositoryConfig, str | None]:
    """Load the configuration the way a *runtime* must: never raising.

    Two failure modes are handled differently, on purpose:

    * An approval whose ``expires_on`` has passed is still a well-formed
      statement of intent, so it loads as written. The enforcement decision
      then lapses it (``enforcement-approval-expired``). If loading refused it
      instead, every publisher run in an enforcing repository would die on the
      day the approval expired — and an enforcing repository is exactly the one
      likely to have marked the check required, so the platform would block
      merges through its own failure.
    * Anything else invalid degrades to shadow and returns the reason, so the
      caller can say out loud why the repository lost its configured mode.

    ``load_repository_config`` keeps the strict behaviour for authoring and
    validating a file, where refusing an expired approval is the point.
    """
    try:
        return load_repository_config(
            root, repository=repository, now=now, require_unexpired=False
        ), None
    except ProductContractError as exc:
        return default_shadow_config(repository), str(exc)


def load_repository_config(
    root: str | Path = ".",
    *,
    repository: str,
    now: date | None = None,
    require_unexpired: bool = True,
) -> RepositoryConfig:
    """Load ``<root>/.eip/pr-guardian.json``; a missing file means shadow.

    ``root`` is a checkout of a *trusted* revision — the pull request's base
    commit in the evaluation job, and the default branch in the publisher.  A
    pull request cannot raise its own repository's mode by editing this file,
    because neither job reads the file from the pull-request head.  It can still
    suppress a block on itself by editing the evaluation workflow definition,
    which is read from the head; see docs/PR-GUARDIAN-REPOSITORY-CONFIG.md
    ("Threat model") for the CODEOWNERS mitigation.
    """
    path = config_path(root)
    if not path.is_file():
        return default_shadow_config(repository)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProductContractError(f"{CONFIG_RELATIVE_PATH} could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProductContractError(
            f"{CONFIG_RELATIVE_PATH} is not valid JSON: {exc}"
        ) from exc
    return parse_repository_config(
        raw, repository=repository, now=now, require_unexpired=require_unexpired
    )


def parse_repository_config(
    payload: Any,
    *,
    repository: str,
    now: date | None = None,
    require_unexpired: bool = True,
) -> RepositoryConfig:
    """Validate one configuration mapping, naming the first offending field.

    ``require_unexpired=False`` accepts an approval whose ``expires_on`` has
    passed; see ``load_effective_config`` for why a runtime needs that.
    """
    today = now or datetime.now(timezone.utc).date()
    if not isinstance(payload, Mapping):
        raise ProductContractError("pr-guardian configuration must be a JSON object")
    for key in payload:
        if key not in _TOP_LEVEL_FIELDS:
            raise ProductContractError(f"{key} is not a recognized configuration field")

    declared_repository = payload.get("repository")
    if declared_repository is not None:
        if not isinstance(declared_repository, str) or declared_repository != repository:
            raise ProductContractError(
                "repository does not match the repository being evaluated"
            )

    mode = _mode(payload.get("mode"))
    service_ids = _identifiers(payload.get("service_ids"), "service_ids")
    owner_ids = _identifiers(payload.get("service_owners"), "service_owners")
    evidence_sources = (
        DEFAULT_EVIDENCE_SOURCES
        if payload.get("evidence_sources") is None
        else _identifiers(payload.get("evidence_sources"), "evidence_sources")
    )
    policy_version = payload.get("policy_version")
    if not isinstance(policy_version, str) or not policy_version or len(policy_version) > 120:
        raise ProductContractError("policy_version is invalid")

    raw_enforcement = payload.get("enforcement")
    if mode is ProductMode.ENFORCE and raw_enforcement is None:
        raise ProductContractError("enforcement is required when mode is enforce")
    if mode is not ProductMode.ENFORCE and raw_enforcement is not None:
        raise ProductContractError("enforcement is allowed only when mode is enforce")
    enforcement = (
        None
        if raw_enforcement is None
        else _enforcement(
            raw_enforcement,
            today=today,
            owner_ids=owner_ids,
            require_unexpired=require_unexpired,
        )
    )

    return RepositoryConfig(
        repository=repository,
        service_ids=service_ids,
        owner_ids=owner_ids,
        evidence_sources=evidence_sources,
        policy_version=policy_version,
        mode=mode,
        enforcement=enforcement,
    )


def _mode(value: object) -> ProductMode:
    if not isinstance(value, str):
        raise ProductContractError("mode is invalid")
    try:
        return ProductMode(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ProductMode)
        raise ProductContractError(f"mode is invalid; expected one of {allowed}") from exc


def _identifiers(value: object, label: str) -> tuple[str, ...]:
    """Accept any order but refuse duplicates, so the file stays unambiguous."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ProductContractError(f"{label} must be a non-empty list of identifiers")
    items: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry or len(entry) > 160 or "\n" in entry:
            raise ProductContractError(f"{label} contains an invalid identifier")
        items.append(entry)
    if len(set(items)) != len(items):
        raise ProductContractError(f"{label} contains a duplicate identifier")
    return tuple(sorted(items))


def _enforcement(
    value: object,
    *,
    today: date,
    owner_ids: tuple[str, ...],
    require_unexpired: bool,
) -> EnforcementPolicy:
    if not isinstance(value, Mapping):
        raise ProductContractError("enforcement must be an object")
    for key in value:
        if key not in _ENFORCEMENT_FIELDS:
            raise ProductContractError(f"enforcement.{key} is not a recognized field")

    rule = value.get("rule")
    if not isinstance(rule, str):
        raise ProductContractError("enforcement.rule is invalid")
    try:
        enforcement_rule = EnforcementRule(rule)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in EnforcementRule)
        raise ProductContractError(
            f"enforcement.rule is invalid; expected one of {allowed}"
        ) from exc

    threshold = value.get("threshold")
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ProductContractError("enforcement.threshold must be an integer between 0 and 100")

    approved_by = value.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by or len(approved_by) > 200:
        raise ProductContractError("enforcement.approved_by is invalid")
    if approved_by not in owner_ids:
        raise ProductContractError(
            "enforcement.approved_by must name one of the declared service_owners"
        )

    approved_on = _date_field(value.get("approved_on"), "enforcement.approved_on")
    expires_on = _date_field(value.get("expires_on"), "enforcement.expires_on")
    if expires_on < approved_on:
        raise ProductContractError("enforcement.expires_on precedes enforcement.approved_on")
    if require_unexpired and expires_on < today:
        raise ProductContractError(
            f"enforcement.expires_on ({expires_on.isoformat()}) has passed; "
            "a service owner must re-approve enforcement"
        )

    raw_waivers = value.get("waivers")
    if raw_waivers is None:
        waivers: tuple[EnforcementWaiver, ...] = ()
    elif not isinstance(raw_waivers, Sequence) or isinstance(raw_waivers, (str, bytes)):
        raise ProductContractError("enforcement.waivers must be a list")
    elif len(raw_waivers) > 64:
        raise ProductContractError("enforcement.waivers is too large")
    else:
        waivers = tuple(
            _waiver(entry, index, owner_ids) for index, entry in enumerate(raw_waivers)
        )

    return EnforcementPolicy(
        rule=enforcement_rule,
        threshold=threshold,
        approved_by=approved_by,
        approved_on=approved_on.isoformat(),
        expires_on=expires_on.isoformat(),
        waivers=waivers,
    )


def _waiver(value: object, index: int, owner_ids: tuple[str, ...]) -> EnforcementWaiver:
    label = f"waivers[{index}]"
    if not isinstance(value, Mapping):
        raise ProductContractError(f"{label} must be an object")
    for key in value:
        if key not in _WAIVER_FIELDS:
            raise ProductContractError(f"{label}.{key} is not a recognized field")
    path_glob = value.get("path_glob")
    if not isinstance(path_glob, str) or not path_glob or len(path_glob) > 200:
        raise ProductContractError(f"{label}.path_glob is invalid")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason or len(reason) > 500:
        raise ProductContractError(f"{label}.reason is invalid")
    owner = value.get("owner")
    if not isinstance(owner, str) or not owner or len(owner) > 200:
        raise ProductContractError(f"{label}.owner is invalid")
    if owner not in owner_ids:
        raise ProductContractError(
            f"{label}.owner must name one of the declared service_owners"
        )
    expires_on = _date_field(value.get("expires_on"), f"{label}.expires_on")
    return EnforcementWaiver(
        path_glob=path_glob,
        reason=reason,
        owner=owner,
        expires_on=expires_on.isoformat(),
    )


def _date_field(value: object, label: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ProductContractError(f"{label} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ProductContractError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc
