"""The ingestion CLI must fail closed on incomplete Azure configuration."""
from __future__ import annotations

import json

import pytest

from ingestion.azure_search import AzureSearchIndex
from ingestion.index import InMemoryIndex
from scripts.ingest_repository import AZURE_REQUIRED, main, resolve_index


def _checkout(root):
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Title\n\nA paragraph of prose.\n", encoding="utf-8")
    (root / "service.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    return root


def test_in_memory_index_needs_no_configuration():
    assert isinstance(resolve_index("in-memory", {}), InMemoryIndex)


def test_azure_index_lists_every_missing_variable():
    with pytest.raises(RuntimeError) as error:
        resolve_index("azure", {})

    message = str(error.value)
    for name in ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX", "AZURE_SEARCH_API_KEY", "AZURE_CLIENT_ID"):
        assert name in message


def test_azure_index_only_names_what_is_actually_missing():
    with pytest.raises(RuntimeError) as error:
        resolve_index("azure", {"AZURE_SEARCH_ENDPOINT": "https://search.private", "AZURE_SEARCH_INDEX": "eip"})

    message = str(error.value)
    assert "AZURE_SEARCH_ENDPOINT" not in message
    assert "AZURE_SEARCH_INDEX" not in message
    assert "AZURE_SEARCH_API_KEY" in message
    assert "AZURE_CLIENT_ID" in message


def test_azure_required_names_are_declared_for_the_runbook():
    assert AZURE_REQUIRED == ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX")


def test_azure_index_uses_the_api_key_when_present():
    index = resolve_index(
        "azure",
        {
            "AZURE_SEARCH_ENDPOINT": "https://search.private",
            "AZURE_SEARCH_INDEX": "eip",
            "AZURE_SEARCH_API_KEY": "secret",
        },
    )

    assert isinstance(index, AzureSearchIndex)
    assert index.endpoint == "https://search.private"
    assert index.index_name == "eip"
    assert index.credential.key == "secret"


def test_azure_index_falls_back_to_workload_identity(monkeypatch):
    import scripts.ingest_repository as cli

    monkeypatch.setattr(cli, "_identity_credential", lambda: "workload-identity")
    index = resolve_index(
        "azure",
        {
            "AZURE_SEARCH_ENDPOINT": "https://search.private",
            "AZURE_SEARCH_INDEX": "eip",
            "AZURE_CLIENT_ID": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert index.credential == "workload-identity"


def test_main_exits_2_when_azure_configuration_is_incomplete(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path / "checkout")
    for name in ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX", "AZURE_SEARCH_API_KEY", "AZURE_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)

    code = main(
        [
            "--root", str(root),
            "--repository", "acme/platform",
            "--branch", "main",
            "--commit-sha", "c" * 40,
            "--groups", "engineering",
            "--index", "azure",
            "--ledger", str(tmp_path / "ledger.db"),
        ]
    )

    assert code == 2
    captured = capsys.readouterr()
    assert "AZURE_SEARCH_ENDPOINT" in captured.err
    assert "AZURE_SEARCH_INDEX" in captured.err


def test_main_runs_the_pipeline_in_memory_and_prints_counts(tmp_path, capsys):
    root = _checkout(tmp_path / "checkout")
    argv = [
        "--root", str(root),
        "--repository", "acme/platform",
        "--branch", "main",
        "--commit-sha", "d" * 40,
        "--groups", "engineering,platform",
        "--ledger", str(tmp_path / "ledger.db"),
    ]

    assert main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["documents"] == 2
    assert first["repository"] == "acme/platform"
    assert first["branch"] == "main"
    assert first["commit_sha"] == "d" * 40
    assert first["index"] == "in-memory"
    assert first["groups"] == ["engineering", "platform"]

    assert main(argv) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["documents"] == 0
    assert second["duplicates"] == 2


def test_main_rejects_an_empty_group_list(tmp_path, capsys):
    root = _checkout(tmp_path / "checkout")

    code = main(
        [
            "--root", str(root),
            "--repository", "acme/platform",
            "--branch", "main",
            "--commit-sha", "e" * 40,
            "--groups", "",
            "--ledger", str(tmp_path / "ledger.db"),
        ]
    )

    assert code == 2
    assert "groups" in capsys.readouterr().err
