"""End-to-end replay of eip.remediation.v1 on Temporal's time-skipping server.

The test server is a binary that ``temporalio`` downloads on first use. Tests
here must never reach the network, so this module skips unless that binary is
already cached locally and then starts it with an explicit path so no download
can be attempted. ``tests/test_remediation_workflow.py`` covers the same
contract as plain functions and always runs.
"""
from __future__ import annotations

import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("temporalio")

import temporalio.service
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from control_plane.remediation import RemediationWorkflowPlan, _hash as plan_hash_of
from intelligence.incidents import analyze_incident
from orchestration.approvals import issue_approval
from orchestration.remediation_workflow import (
    RemediationApprovalSignal,
    RemediationRequest,
    RemediationWorkflow,
)
from remediation.planner import plan_from_incident
from tests.test_remediation_workflow import (
    SECRET,
    activities as build_activities,
    crashloop_evidence,
    request as build_request,
)


def cached_test_server() -> Path:
    return Path(tempfile.gettempdir()) / f"temporal-test-server-sdk-python-{temporalio.service.__version__}"


pytestmark = pytest.mark.skipif(
    not cached_test_server().is_file(),
    reason="Temporal test-server binary is not cached locally; refusing to download it in tests",
)


def expected_plan_hash(request: RemediationRequest) -> str:
    analysis = analyze_incident(list(crashloop_evidence()), service=request.service)
    plan = plan_from_incident(analysis)
    assert plan is not None
    return plan_hash_of(
        RemediationWorkflowPlan(
            workflow_id=request.workflow_id,
            service=request.service,
            environment=request.environment,
            runbook_id=plan.runbook_id,
            blast_radius=request.blast_radius,
            evidence_ids=tuple(plan.evidence_ids),
            confidence=plan.confidence,
        ).payload()
    )


def approval_signal(request: RemediationRequest, plan_hash: str) -> RemediationApprovalSignal:
    approval = issue_approval(
        workflow_id=request.workflow_id, approver="sre-oncall", plan_hash=plan_hash, secret=SECRET
    )
    return RemediationApprovalSignal(
        workflow_id=approval.workflow_id,
        approver=approval.approver,
        plan_hash=approval.plan_hash,
        issued_at=approval.issued_at,
        signature=approval.signature,
    )


def test_a_mismatched_plan_hash_is_rejected_and_the_matching_one_completes(tmp_path):
    acts = build_activities(tmp_path)
    request = build_request()
    plan_hash = expected_plan_hash(request)

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping(
            test_server_existing_path=str(cached_test_server())
        ) as env:
            async with Worker(
                env.client,
                task_queue="eip-remediation-test",
                workflows=[RemediationWorkflow],
                activities=acts.activity_functions(),
                activity_executor=ThreadPoolExecutor(4),
            ):
                handle = await env.client.start_workflow(
                    RemediationWorkflow.run,
                    request,
                    id=request.workflow_id,
                    task_queue="eip-remediation-test",
                )
                await handle.signal(
                    RemediationWorkflow.submit_approval,
                    approval_signal(request, "sha256:" + "b" * 64),
                )
                await handle.signal(
                    RemediationWorkflow.submit_approval, approval_signal(request, plan_hash)
                )
                result = await handle.result()
                rejected = await handle.query(RemediationWorkflow.rejected_approvals)
                return result, rejected

    outcome, rejected = asyncio.run(scenario())

    assert outcome.status == "succeeded"
    assert outcome.plan_hash == plan_hash
    assert outcome.approver == "sre-oncall"
    assert rejected == ["approval plan hash does not match the planned remediation"]
