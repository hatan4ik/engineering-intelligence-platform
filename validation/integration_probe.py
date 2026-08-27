"""Read-only integration proof harness for a private EIP environment.

This module deliberately does not create resources, write data, or use a
deployment credential as an end-user identity. It proves the deployed query
contract with two pre-provisioned Entra principals whose bearer tokens are
mounted as files by an approved private runner.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


# Every variable the probe needs before any subprocess, DNS lookup, or HTTP call
# runs. Keep in sync with the "Required environment contract" table in
# ``docs/INTEGRATION-PROOF-RUNBOOK.md``; ``tests/test_integration_probe_configuration.py``
# asserts that each name below is documented there and set by the workflow.
REQUIRED_ENVIRONMENT: tuple[str, ...] = (
    "EIP_BASE_URL",
    "EIP_INTEGRATION_ALLOWED_BEARER_FILE",
    "EIP_INTEGRATION_DENIED_BEARER_FILE",
    "EIP_INTEGRATION_ALLOWED_QUERY",
    "EIP_INTEGRATION_DENIED_QUERY",
    "EIP_INTEGRATION_ALLOWED_SOURCE",
    "AZURE_SEARCH_HOST",
    "AZURE_OPENAI_HOST",
    "AZURE_KEYVAULT_HOST",
    "EIP_COSMOS_HOST",
    "AZURE_POSTGRESQL_HOST",
    "EIP_TEMPORAL_HOST",
    # Unscoped evidence is not evidence (docs/PRODUCTION-EVIDENCE.md: every
    # promotion decision names service, environment, data source and versions),
    # and the runbook requires the evidence path to be outside the source
    # checkout. Neither may fall back to a default on a passing run.
    "EIP_INTEGRATION_SCOPE",
    "EIP_INTEGRATION_EVIDENCE",
)

# Documented in the same table but not required: the repository scopes apply only
# when the governed test question is repository-scoped. They are still passed by
# the workflow.
OPTIONAL_ENVIRONMENT: tuple[str, ...] = (
    "EIP_INTEGRATION_ALLOWED_REPOSITORY",
    "EIP_INTEGRATION_DENIED_REPOSITORY",
)


def missing_configuration(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return every required variable that is unset or blank, in documented order."""

    source = os.environ if environ is None else environ
    return tuple(name for name in REQUIRED_ENVIRONMENT if not str(source.get(name, "")).strip())


@dataclass(frozen=True)
class ProbeResult:
    name: str
    passed: bool
    detail: str


def _run(command: list[str], *, name: str) -> ProbeResult:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        detail = (completed.stdout or completed.stderr).strip()[:1000]
        return ProbeResult(name, True, detail or "ok")
    except (subprocess.SubprocessError, OSError) as exc:
        return ProbeResult(name, False, str(exc))


def probe_http(name: str, url: str) -> ProbeResult:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return ProbeResult(name, 200 <= response.status < 300, f"HTTP {response.status}")
    except Exception as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def probe_private_dns(name: str, hostname: str) -> ProbeResult:
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(hostname, None)})
    except OSError as exc:
        return ProbeResult(name, False, str(exc))
    if not addresses:
        return ProbeResult(name, False, "no addresses returned")
    non_private = [address for address in addresses if not ipaddress.ip_address(address).is_private]
    if non_private:
        return ProbeResult(name, False, "non-private address returned: " + ",".join(non_private))
    return ProbeResult(name, True, "private addresses: " + ",".join(addresses))


def _read_bearer(path: str, *, name: str) -> tuple[str | None, ProbeResult | None]:
    if not path.strip():
        return None, ProbeResult(name, False, "token-file environment variable is not configured")
    try:
        token = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        return None, ProbeResult(name, False, f"cannot read token file: {type(exc).__name__}")
    if not token:
        return None, ProbeResult(name, False, "token file is empty")
    return token, None


def _query(base_url: str, token: str, payload: dict[str, object]) -> tuple[int, dict[str, Any] | None, str | None]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/query",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1024 * 1024)
            decoded = json.loads(raw)
            return response.status, decoded if isinstance(decoded, dict) else None, None
    except urllib.error.HTTPError as exc:
        # An HTTP error is returned without exposing its body, which could
        # contain gateway implementation details or untrusted content.
        return exc.code, None, None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"


def probe_authorized_query(
    *,
    base_url: str,
    token_file: str,
    question: str,
    repository: str | None,
    expected_source: str | None,
) -> ProbeResult:
    token, error = _read_bearer(token_file, name="authorized-query")
    if error is not None:
        return error
    if not question.strip():
        return ProbeResult("authorized-query", False, "EIP_INTEGRATION_ALLOWED_QUERY is not configured")
    status, body, request_error = _query(base_url, token or "", _query_payload(question, repository))
    if request_error:
        return ProbeResult("authorized-query", False, request_error)
    if status != 200 or body is None:
        return ProbeResult("authorized-query", False, f"expected HTTP 200, got {status}")
    evidence = body.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return ProbeResult("authorized-query", False, "authorized principal received no evidence")
    if body.get("model") in {None, "none"}:
        return ProbeResult("authorized-query", False, "authorized query did not use an evidence-backed model path")
    sources = [str(item.get("source", "")) for item in evidence if isinstance(item, dict)]
    if not sources or any(not source for source in sources):
        return ProbeResult("authorized-query", False, "evidence lacks stable source citations")
    if expected_source and expected_source not in sources:
        return ProbeResult("authorized-query", False, "expected citation was absent")
    return ProbeResult("authorized-query", True, f"evidence_count={len(sources)}; citations_present=true")


def probe_denied_query(
    *,
    base_url: str,
    token_file: str,
    question: str,
    repository: str | None,
) -> ProbeResult:
    token, error = _read_bearer(token_file, name="denied-query")
    if error is not None:
        return error
    if not question.strip():
        return ProbeResult("denied-query", False, "EIP_INTEGRATION_DENIED_QUERY is not configured")
    status, body, request_error = _query(base_url, token or "", _query_payload(question, repository))
    if request_error:
        return ProbeResult("denied-query", False, request_error)
    if status != 200 or body is None:
        return ProbeResult("denied-query", False, f"expected an authenticated refusal (HTTP 200), got {status}")
    if body.get("evidence") != [] or body.get("model") != "none":
        return ProbeResult("denied-query", False, "denied principal received evidence or a model answer")
    if body.get("answer") != "I do not have enough authorized evidence to answer.":
        return ProbeResult("denied-query", False, "denied query did not use the required refusal")
    return ProbeResult("denied-query", True, "authorized-evidence refusal verified")


def _query_payload(question: str, repository: str | None) -> dict[str, object]:
    payload: dict[str, object] = {"question": question}
    if repository:
        payload["repo"] = repository
    return payload


def collect() -> tuple[ProbeResult, ...]:
    results: list[ProbeResult] = []
    results.append(_run(["az", "account", "show", "--output", "none"], name="azure-identity"))
    results.append(_run(["kubectl", "cluster-info"], name="aks-private-context"))

    base_url = os.getenv("EIP_BASE_URL", "").rstrip("/")
    if not base_url.startswith("https://"):
        results.append(ProbeResult("eip-health", False, "EIP_BASE_URL must be an https private ingress URL"))
        results.append(ProbeResult("authorized-query", False, "EIP_BASE_URL is not configured for https"))
        results.append(ProbeResult("denied-query", False, "EIP_BASE_URL is not configured for https"))
    else:
        results.append(probe_http("eip-health", f"{base_url}/healthz"))
        results.append(
            probe_authorized_query(
                base_url=base_url,
                token_file=os.getenv("EIP_INTEGRATION_ALLOWED_BEARER_FILE", ""),
                question=os.getenv("EIP_INTEGRATION_ALLOWED_QUERY", ""),
                repository=os.getenv("EIP_INTEGRATION_ALLOWED_REPOSITORY") or None,
                expected_source=os.getenv("EIP_INTEGRATION_ALLOWED_SOURCE") or None,
            )
        )
        results.append(
            probe_denied_query(
                base_url=base_url,
                token_file=os.getenv("EIP_INTEGRATION_DENIED_BEARER_FILE", ""),
                question=os.getenv("EIP_INTEGRATION_DENIED_QUERY", ""),
                repository=os.getenv("EIP_INTEGRATION_DENIED_REPOSITORY") or None,
            )
        )

    for env_name, probe_name in (
        ("AZURE_SEARCH_HOST", "search-private-dns"),
        ("AZURE_OPENAI_HOST", "openai-private-dns"),
        ("AZURE_KEYVAULT_HOST", "keyvault-private-dns"),
        ("EIP_COSMOS_HOST", "cosmos-private-dns"),
        ("AZURE_POSTGRESQL_HOST", "postgresql-private-dns"),
        ("EIP_TEMPORAL_HOST", "temporal-private-dns"),
    ):
        host = os.getenv(env_name, "").strip()
        results.append(
            probe_private_dns(probe_name, host)
            if host
            else ProbeResult(probe_name, False, f"{env_name} is not configured")
        )
    return tuple(results)


#: The scope written on the configuration-refusal path, which runs before
#: ``collect()`` and therefore before EIP_INTEGRATION_SCOPE has been proven set.
#: It is a literal marker, not a fallback: a passing payload can never carry it.
CONFIGURATION_REFUSED_SCOPE = "configuration-refused"


def _emit(results: list[dict[str, object]], *, passed: bool) -> None:
    scope = os.environ.get("EIP_INTEGRATION_SCOPE") or CONFIGURATION_REFUSED_SCOPE
    if passed and scope == CONFIGURATION_REFUSED_SCOPE:
        raise RuntimeError("a passing integration payload must carry EIP_INTEGRATION_SCOPE")
    payload: dict[str, object] = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "results": results,
        "passed": passed,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["sha256"] = hashlib.sha256(canonical).hexdigest()
    path = Path(os.getenv("EIP_INTEGRATION_EVIDENCE", "integration-evidence.json"))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    # Fail closed before any probe runs. A partially configured run produces a
    # long list of individually plausible failures that reads like an outage; the
    # single configuration result says what it actually is.
    missing = missing_configuration()
    if missing:
        _emit(
            [{"probe": "configuration", "passed": False, "missing": list(missing)}],
            passed=False,
        )
        print(
            "integration probe refused to run; missing required environment: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    results = collect()
    passed = all(item.passed for item in results)
    _emit([asdict(item) for item in results], passed=passed)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
