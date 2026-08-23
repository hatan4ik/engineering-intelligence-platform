from validation.integration_probe import ProbeResult, collect, probe_dns, probe_http


def test_missing_environment_is_reported_as_failure(monkeypatch):
    monkeypatch.delenv("EIP_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_SEARCH_HOST", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_HOST", raising=False)
    monkeypatch.delenv("AZURE_KEYVAULT_HOST", raising=False)

    def fake_run(command, *, name):
        return ProbeResult(name, True, "ok")

    monkeypatch.setattr("validation.integration_probe._run", fake_run)
    results = {item.name: item for item in collect()}
    assert results["azure-identity"].passed is True
    assert results["aks-context"].passed is True
    assert results["eip-health"].passed is False
    assert results["search-private-dns"].passed is False


def test_dns_probe_reports_resolution(monkeypatch):
    monkeypatch.setattr(
        "validation.integration_probe.socket.getaddrinfo",
        lambda host, port: [(None, None, None, None, ("10.0.0.4", 0))],
    )
    result = probe_dns("search-private-dns", "search.internal")
    assert result.passed is True
    assert "10.0.0.4" in result.detail


def test_http_probe_reports_success(monkeypatch):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size): return b'{"status":"ok"}'

    monkeypatch.setattr("validation.integration_probe.urllib.request.urlopen", lambda *args, **kwargs: Response())
    result = probe_http("eip-health", "https://eip.internal/healthz")
    assert result.passed is True
    assert "HTTP 200" in result.detail
