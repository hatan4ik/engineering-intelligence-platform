from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


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
            body = response.read(1024).decode(errors="replace")
            return ProbeResult(name, 200 <= response.status < 300, f"HTTP {response.status}: {body}")
    except Exception as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def probe_dns(name: str, hostname: str) -> ProbeResult:
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(hostname, None)})
        return ProbeResult(name, bool(addresses), ",".join(addresses))
    except OSError as exc:
        return ProbeResult(name, False, str(exc))


def collect() -> tuple[ProbeResult, ...]:
    results: list[ProbeResult] = []
    results.append(_run(["az", "account", "show", "--output", "none"], name="azure-identity"))
    results.append(_run(["kubectl", "cluster-info"], name="aks-context"))

    base_url = os.getenv("EIP_BASE_URL", "").rstrip("/")
    results.append(
        probe_http("eip-health", f"{base_url}/healthz")
        if base_url
        else ProbeResult("eip-health", False, "EIP_BASE_URL is not configured")
    )

    for env_name, probe_name in (
        ("AZURE_SEARCH_HOST", "search-private-dns"),
        ("AZURE_OPENAI_HOST", "openai-private-dns"),
        ("AZURE_KEYVAULT_HOST", "keyvault-private-dns"),
    ):
        host = os.getenv(env_name, "").strip()
        results.append(
            probe_dns(probe_name, host)
            if host
            else ProbeResult(probe_name, False, f"{env_name} is not configured")
        )
    return tuple(results)


def main() -> int:
    results = collect()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(item) for item in results],
        "passed": all(item.passed for item in results),
    }
    path = Path(os.getenv("EIP_INTEGRATION_EVIDENCE", "integration-evidence.json"))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
