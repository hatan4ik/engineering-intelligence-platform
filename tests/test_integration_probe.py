from validation.integration_probe import (
    ProbeResult,
    collect,
    probe_authorized_query,
    probe_denied_query,
    probe_private_dns,
)


def test_missing_environment_is_reported_as_failure(monkeypatch):
    for name in (
        "EIP_BASE_URL",
        "AZURE_SEARCH_HOST",
        "AZURE_OPENAI_HOST",
        "AZURE_KEYVAULT_HOST",
        "EIP_COSMOS_HOST",
        "AZURE_POSTGRESQL_HOST",
        "EIP_TEMPORAL_HOST",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(
        "validation.integration_probe._run",
        lambda command, *, name: ProbeResult(name, True, "ok"),
    )
    results = {item.name: item for item in collect()}

    assert results["azure-identity"].passed is True
    assert results["aks-private-context"].passed is True
    assert results["eip-health"].passed is False
    assert results["authorized-query"].passed is False
    assert results["search-private-dns"].passed is False


def test_private_dns_rejects_public_resolution(monkeypatch):
    monkeypatch.setattr(
        "validation.integration_probe.socket.getaddrinfo",
        lambda host, port: [(None, None, None, None, ("52.1.2.3", 0))],
    )

    result = probe_private_dns("search-private-dns", "search.example")

    assert result.passed is False
    assert "non-private" in result.detail


def test_authorized_and_denied_queries_prove_opposite_acl_outcomes(monkeypatch, tmp_path):
    allowed_token = tmp_path / "allowed.token"
    denied_token = tmp_path / "denied.token"
    allowed_token.write_text("allowed-token")
    denied_token.write_text("denied-token")

    def fake_query(base_url, token, payload):
        assert base_url == "https://eip.private"
        if token == "allowed-token":
            return 200, {
                "model": "azure-chat",
                "answer": "Grounded response",
                "evidence": [{"source": "docs/allowed.md"}],
            }, None
        return 200, {
            "model": "none",
            "answer": "I do not have enough authorized evidence to answer.",
            "evidence": [],
        }, None

    monkeypatch.setattr("validation.integration_probe._query", fake_query)

    allowed = probe_authorized_query(
        base_url="https://eip.private",
        token_file=str(allowed_token),
        question="What is the approved rollback?",
        repository="platform",
        expected_source="docs/allowed.md",
    )
    denied = probe_denied_query(
        base_url="https://eip.private",
        token_file=str(denied_token),
        question="What is the approved rollback?",
        repository="platform",
    )

    assert allowed.passed is True
    assert denied.passed is True


def test_denied_query_fails_if_any_evidence_is_returned(monkeypatch, tmp_path):
    token = tmp_path / "denied.token"
    token.write_text("denied-token")
    monkeypatch.setattr(
        "validation.integration_probe._query",
        lambda *args, **kwargs: (200, {"model": "azure", "answer": "leak", "evidence": [{"source": "secret"}]}, None),
    )

    result = probe_denied_query(
        base_url="https://eip.private",
        token_file=str(token),
        question="protected query",
        repository=None,
    )

    assert result.passed is False
    assert "received evidence" in result.detail
