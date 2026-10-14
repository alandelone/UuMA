from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from uuma.honc.graph_client import GraphExecutionClient
from uuma.honc.mcp import (
    honc_apply_completion,
    honc_assess_completion,
    honc_check_habit,
    honc_control_round,
    honc_correct_record,
    honc_get_context,
    honc_get_report,
    honc_reconcile_updates,
    honc_record_execution,
    honc_status,
    set_service,
)
from uuma.honc.models import (
    AssessmentResult,
    RoundStatus,
    TaskSnapshot,
    TrustedInput,
)
from uuma.honc.service import HoncService
from uuma.honc.store import HoncStore


class FakeGraphExecutionClient(GraphExecutionClient):
    """Fake client simulating Yonc Graph responses for unit testing."""

    def __init__(self) -> None:
        super().__init__(base_url="http://fake-graph", database_id="fake-db-123")
        self.decisions_submitted: list[dict[str, Any]] = []
        self.focus_events_submitted: list[dict[str, Any]] = []
        self.receipts_store: dict[str, dict[str, Any]] = {}

    def get_health(self) -> dict[str, Any]:
        return {"ok": True, "database_id": self.database_id, "graph_version": 42}

    def submit_action_decision(
        self,
        operation_id: str,
        node_id: str,
        action: str,
        decision_origin: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "operation_id": operation_id,
            "node_id": node_id,
            "action": action,
            "decision_origin": decision_origin,
            "is_undone": False,
        }
        self.decisions_submitted.append(record)
        receipt = {
            "receipt": {
                "operation_id": operation_id,
                "node_id": node_id,
                "action": action,
                "is_undone": False,
            },
            "node": {"id": node_id, "status": "DONE" if action == "done" else "TODO"},
            "operation_batch_id": f"batch-{operation_id}",
        }
        self.receipts_store[operation_id] = receipt["receipt"]
        return receipt

    def get_receipt(self, operation_id: str) -> dict[str, Any] | None:
        rec = self.receipts_store.get(operation_id)
        return {"receipt": rec} if rec else None

    def submit_focus_event(
        self,
        interval_id: str,
        event_type: str,
        node_id: str | None = None,
        timestamp: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        self.focus_events_submitted.append(
            {
                "interval_id": interval_id,
                "event_type": event_type,
                "node_id": node_id,
                "timestamp": timestamp,
                "duration_seconds": duration_seconds,
            }
        )
        return {
            "status": "closed" if event_type == "close" else "active",
            "session_id": interval_id,
        }


@pytest.fixture
def fake_graph() -> FakeGraphExecutionClient:
    return FakeGraphExecutionClient()


@pytest.fixture
def mcp_service(tmp_path: Path, fake_graph: FakeGraphExecutionClient) -> HoncService:
    db_path = tmp_path / "honc" / "honc.db"
    store = HoncStore(db_path)
    service = HoncService(store=store, graph_client=fake_graph)
    set_service(service)
    yield service
    set_service(None)


def test_mcp_status_and_context_empty(mcp_service: HoncService):
    st = honc_status()
    assert st["active_round"] is None
    assert st["pending_outbox_count"] == 0

    ctx = honc_get_context()
    assert ctx["active_round"] is None
    assert ctx["current_next"] is None
    assert ctx["task_snapshot"] is None


def test_mcp_round_control_and_recording_flow(
    mcp_service: HoncService, fake_graph: FakeGraphExecutionClient
):
    # 1. Prepare round
    prep = honc_control_round(
        action="prepare",
        target_outcome="Implement MCP tests",
        tiny_step="Open test_honc_mcp.py",
        task_id="act-999",
    )
    round_id = prep["round_id"]
    assert prep["status"] == RoundStatus.PREPARED

    # 2. Start round
    start = honc_control_round(action="start", round_id=round_id)
    assert start["status"] == RoundStatus.RUNNING
    # Verified focus event triggered on Graph
    assert len(fake_graph.focus_events_submitted) == 1
    assert fake_graph.focus_events_submitted[0]["event_type"] == "start"

    # 3. Check status
    st = honc_status()
    assert st["active_round"] is not None
    assert st["active_round"]["round_id"] == round_id
    assert st["active_round"]["status"] == RoundStatus.RUNNING

    # 4. Record intermediate execution
    rec = honc_record_execution(
        raw_content="Wrote 3 test cases",
        round_id=round_id,
        task_id="act-999",
        outcome="3 test cases written",
        next_step="Write apply_completion test",
    )
    assert rec["record_id"] is not None

    # 5. Check context
    ctx = honc_get_context(task_id="act-999")
    assert ctx["current_next"] == "Write apply_completion test"
    assert len(ctx["recent_events"]) == 1

    # 6. End round with outcome
    end = honc_control_round(
        action="end",
        round_id=round_id,
        outcome="All MCP tests completed",
    )
    assert end["status"] == RoundStatus.CLOSED
    assert len(fake_graph.focus_events_submitted) == 2
    assert fake_graph.focus_events_submitted[1]["event_type"] == "close"


def test_mcp_habit_and_report(mcp_service: HoncService):
    tick = honc_check_habit("code_review", quantity=1.0, user_report="Reviewed PR #12")
    assert tick["habit_id"] == "code_review"

    rep = honc_get_report()
    assert rep["user_id"] == "default_user"
    assert any(h["habit_id"] == "code_review" for h in rep["habits_summary"])


def test_mcp_assessment_and_apply_completion(
    mcp_service: HoncService, fake_graph: FakeGraphExecutionClient
):
    task_id = "node-action-auth"
    # Seed task snapshot
    mcp_service.store.save_task_snapshot(
        TaskSnapshot(
            graph_database_id="fake-db-123",
            node_id=task_id,
            title="Add OAuth2 token refresh",
            done_when="Token refresh endpoint working; unit tests pass",
        )
    )

    # 1. Assess with insufficient evidence
    eval_bad = honc_assess_completion(
        task_id=task_id,
        evidence="Token refresh endpoint created",
    )
    assert eval_bad["result"] == AssessmentResult.INSUFFICIENT
    assert eval_bad["can_apply"] is False

    # 2. Assess with full evidence
    eval_good = honc_assess_completion(
        task_id=task_id,
        evidence="Token refresh endpoint working and unit tests pass with 100% coverage",
    )
    assert eval_good["result"] == AssessmentResult.SATISFIED
    assert eval_good["can_apply"] is True

    # 3. Create trusted input for completion authorization
    inp = mcp_service.store.record_trusted_input(
        TrustedInput(
            user_id="default_user",
            entrypoint="hermes_local",
            raw_content="OAuth2 token refresh task is completed, tests passed",
        )
    )

    # 4. Apply completion
    applied = honc_apply_completion(
        task_id=task_id,
        trusted_input_id=inp.input_id,
        assessment_id=eval_good["assessment_id"],
    )
    assert applied["graph_update_status"] == "SUCCEEDED"
    assert len(fake_graph.decisions_submitted) == 1
    assert fake_graph.decisions_submitted[0]["action"] == "done"
    assert fake_graph.decisions_submitted[0]["node_id"] == task_id


def test_mcp_correct_record_and_reconcile(
    mcp_service: HoncService, fake_graph: FakeGraphExecutionClient
):
    # Record initial event
    rec = honc_record_execution(
        raw_content="Deployed to production",
        outcome="Deployed v1.0",
        task_id="node-action-deploy",
    )

    # Correct it with compensating reopen action
    corr = honc_correct_record(
        original_event_id=rec["record_id"],
        reason="Rollback deployment due to 500 error",
        corrected_outcome="Rolled back deployment",
        compensating_action="reopen",
    )
    assert corr["assessment_status"] == "CORRECTED"
    assert corr["graph_update_status"] == "COMPENSATED"
    assert any(d["action"] == "reopen" for d in fake_graph.decisions_submitted)

    # Reconcile updates
    reconciled = honc_reconcile_updates()
    assert reconciled["checked_count"] == 0  # all already succeeded


def test_honc_mcp_main(monkeypatch) -> None:
    import sys
    from unittest.mock import Mock

    import uuma.honc.mcp  # noqa: F401

    mod = sys.modules["uuma.honc.mcp"]
    mock_run = Mock()
    monkeypatch.setattr(mod.mcp, "run", mock_run)
    mod.main()
    mock_run.assert_called_once()

