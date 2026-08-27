"""The synchronous PR Guardian CLI must await the asynchronous product service."""

from __future__ import annotations

import json
from types import SimpleNamespace

from intelligence.risk import RiskAssessment
from product.pr_guardian.enforcement import EnforcementDecision
from scripts import run_pr_guardian


def _event(tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "opened",
                "number": 7,
                "repository": {"full_name": "acme/platform"},
                "pull_request": {"head": {"sha": "deadbeef"}},
            }
        ),
        encoding="utf-8",
    )
    return event_path


def test_cli_awaits_the_async_product_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(_event(tmp_path)))
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EIP_PR_GUARDIAN_RESULT_PATH", str(tmp_path / "result.json"))
    monkeypatch.setattr(run_pr_guardian, "build_service_graph_from_checkout", lambda root: object())

    called = False

    class AsyncService:
        def __init__(self, **kwargs):
            pass

        # The fake honours the real PRGuardianService.evaluate contract: the
        # CLI passes ``now`` and reads changed_files / mode / enforcement so it
        # can run Architecture Guard and record the repository's mode.
        async def evaluate(self, event, *, publish, now=None):
            nonlocal called
            called = True
            return SimpleNamespace(
                assessment=RiskAssessment(0, "low", (), ()),
                workflow_id="pr:acme/platform:7",
                changed_services=(),
                changed_files=(),
                policy=SimpleNamespace(
                    require_extended_tests=False,
                    require_additional_approval=False,
                ),
                would_block=False,
                mode="shadow",
                enforcement=EnforcementDecision(False, "shadow-mode", None),
            )

    monkeypatch.setattr(run_pr_guardian, "PRGuardianService", AsyncService)

    assert run_pr_guardian.main() == 0
    assert called is True
    observation = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert observation["assessment"]["score"] == 0
