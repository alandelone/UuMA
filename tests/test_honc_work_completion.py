"""Authenticated completion -> versioned Graph mutation -> receipt and node readback."""

import json

import httpx
import pytest

from uuma.honc.graph_client import GraphExecutionClient
from uuma.honc.models import Round
from uuma.honc.service import HoncService
from uuma.honc.store import HoncStore
from uuma.honc.work_completion import WorkCompletion, is_completion_report


class Graph:
    def __init__(self):
        self.version = 4
        self.nodes = [
            {
                "id": "task-a",
                "title": "登录测试",
                "node_kind": "WORK",
                "work_type": "ACTION",
                "status": "DOING",
                "stage": "EXECUTION",
                "done_when": "登录测试全部通过",
                "portfolio_role": None,
                "parent_id": None,
            }
        ]
        self.edges = []
        self.receipts = {}
        self.posts = []
        self.fail_after_commit = False
        self.fail_before_commit = False
        self.stale = False
        self.wrong_readback = False

    def request(self, request):
        path = request.url.path
        if path == "/api/v2/health":
            return httpx.Response(200, json={"database_id": "db", "graph_version": self.version})
        if path == "/api/v2/graph":
            return httpx.Response(
                200, json={"graph_version": self.version, "nodes": self.nodes, "edges": self.edges}
            )
        if "/receipts/" in path:
            receipt = self.receipts.get(path.rsplit("/", 1)[1])
            return httpx.Response(200 if receipt else 404, json={"receipt": receipt})
        if path.startswith("/api/v2/nodes/"):
            node = next(n for n in self.nodes if n["id"] == path.rsplit("/", 1)[1])
            return httpx.Response(
                200, json={**node, "status": "TODO"} if self.wrong_readback else node
            )
        if path == "/api/v2/execution/action-decisions":
            payload = json.loads(request.content)
            assert len(payload["operation_id"]) <= 36
            self.posts.append(payload)
            assert request.headers["X-Graph-Database-Id"] == "db"
            if self.stale:
                return httpx.Response(409, json={"error": "VERSION_CONFLICT"})
            if self.fail_before_commit:
                self.fail_before_commit = False
                raise httpx.ConnectError("fixture outage")
            assert payload["expected_graph_version"] == self.version
            node = next(n for n in self.nodes if n["id"] == payload["node_id"])
            node["status"] = "DONE"
            self.version += 1
            receipt = {
                "operation_id": payload["operation_id"],
                "node_id": payload["node_id"],
                "action": "done",
                "decision_origin": payload["decision_origin"],
                "state_after": {"status": "DONE"},
                "undone_at": None,
            }
            self.receipts[payload["operation_id"]] = receipt
            if self.fail_after_commit:
                self.fail_after_commit = False
                raise httpx.ReadTimeout("fixture response lost")
            return httpx.Response(200, json={"receipt": receipt, "node": node})
        raise AssertionError(request.url)


@pytest.fixture
def setup(tmp_path):
    graph = Graph()
    client = GraphExecutionClient(
        base_url="http://fixture",
        database_id="db",
        client=httpx.Client(transport=httpx.MockTransport(graph.request)),
    )
    store = HoncStore(tmp_path / "honc.db")
    return WorkCompletion(store, client), graph


def report(work, text="今天完成了登录测试", source="telegram:owner:1"):
    return work.report(text=text, owner_id="owner", session_id="s", source_event_id=source)


def test_explicit_user_report_ticks_graph_and_confirms_receipt_and_node(setup):
    work, graph = setup
    result = report(work)
    assert result["status"] == "VERIFIED" and result["graph_verified"]
    assert graph.nodes[0]["status"] == "DONE"
    assert len(graph.posts) == 1
    assert graph.posts[0]["decision_origin"]["evidence_kind"] == "user_completion_report"
    with work.store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM execution_events").fetchone()[0] == 1
        row = connection.execute("SELECT evidence FROM completion_assessments").fetchone()
        assert "未独立检验产物" in row[0]
    assert report(work)["graph_verified"]
    assert len(graph.posts) == 1


@pytest.mark.parametrize(
    "text",
    [
        "登录测试还没完成",
        "登录测试只完成一部分",
        "如果完成了登录测试",
        "明天完成登录测试",
        "他说登录测试完成了",
        '"登录测试完成了"',
        "登录测试完成了吗？",
        "登录测试完成了但还差异常用例",
        "登录测试已完成，不要勾选",
        "I have not completed 登录测试",
        "我没做完登录测试",
        "登录测试完成了一半",
        "登录测试完成了但是运行失败",
        "登录测试好像完成了",
        "我以为登录测试完成了",
        "他说“登录测试完成了”",
    ],
)
def test_negatives_plans_quotes_questions_partial_do_not_complete(setup, text):
    work, graph = setup
    assert report(work, text) is None
    assert not graph.posts


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("work_type", "GOAL", "REVIEW_REQUIRED"),
        ("status", "REVIEW", "REVIEW_REQUIRED"),
        ("portfolio_role", "PARKED", "REVIEW_REQUIRED"),
        ("archived", True, "REVIEW_REQUIRED"),
        ("is_proposed", True, "REVIEW_REQUIRED"),
        ("done_when", "", "NEEDS_CRITERIA"),
    ],
)
def test_ineligible_tasks_keep_fact_without_marking_done(setup, field, value, status):
    work, graph = setup
    graph.nodes[0][field] = value
    assert report(work)["status"] == status
    assert not graph.posts


def test_parent_and_duplicate_names_never_guess(setup):
    work, graph = setup
    graph.edges = [{"relation": "contains", "source_id": "task-a", "target_id": "child"}]
    assert report(work)["status"] == "REVIEW_REQUIRED"
    graph.edges = []
    graph.nodes.append({**graph.nodes[0], "id": "task-b"})
    assert report(work)["status"] == "NEEDS_TARGET"
    assert not graph.posts


def test_deictic_completion_uses_only_owners_active_round(setup):
    work, _graph = setup
    work.store.create_round(
        Round(user_id="other", task_id="task-a", target_outcome="A", tiny_step="B")
    )
    assert report(work, "这个任务完成了")["status"] == "NEEDS_TARGET"
    work.store.create_round(
        Round(user_id="owner", task_id="task-a", target_outcome="A", tiny_step="B")
    )
    assert report(work, "这个任务完成了")["status"] == "VERIFIED"


def test_lost_response_reconciles_original_receipt_after_restart(setup):
    work, graph = setup
    graph.fail_after_commit = True
    pending = report(work)
    assert pending["status"] == "PENDING_VERIFICATION" and not pending["graph_verified"]
    restarted = WorkCompletion(HoncStore(work.store.path), work.graph)
    assert report(restarted)["graph_verified"]
    assert len(graph.posts) == 1


def test_uncommitted_outage_retries_same_operation_and_version(setup):
    work, graph = setup
    graph.fail_before_commit = True
    result = report(work)
    assert not result["graph_verified"]
    service = HoncService(work.store, graph_client=work.graph)
    assert service.reconcile_updates()["reconciled_count"] == 1
    assert graph.posts[0] == graph.posts[1]


def test_conflict_or_false_readback_never_claims_success(setup):
    work, graph = setup
    graph.stale = True
    assert not report(work)["graph_verified"]
    graph.stale = False
    graph.wrong_readback = True
    assert not report(work)["graph_verified"]
    assert len(graph.posts) == 1  # A known version conflict is not blindly resubmitted.
    assert not report(work, source="telegram:owner:2")["graph_verified"]


def test_live_task_context_fetches_snapshot_with_criteria(setup):
    work, _graph = setup
    result = HoncService(work.store, graph_client=work.graph).get_context("task-a")
    assert result["task_snapshot_fresh"]
    assert result["task_snapshot"]["done_when"] == "登录测试全部通过"


def test_voice_wrapper_is_only_unwrapped_for_authenticated_voice(setup):
    work, _graph = setup
    assert not is_completion_report('"登录测试完成了"')
    result = work.report(
        text='"登录测试完成了"',
        owner_id="owner",
        session_id="s",
        source_event_id="voice:1",
        input_kind="voice_transcript",
    )
    assert result["graph_verified"]


def test_existing_reminder_tick_reconciles_pending_completion_without_new_job(setup, monkeypatch):
    from types import SimpleNamespace

    from uuma.honc.native_reminders import run_tick

    work, graph = setup
    graph.fail_before_commit = True
    assert report(work)["status"] == "PENDING_VERIFICATION"
    monkeypatch.setattr("uuma.honc.graph_client.GraphExecutionClient", lambda **kwargs: work.graph)
    config = {
        "profile": "honc",
        "owner_id": "owner",
        "database_path": str(work.store.path),
        "delivery_binding": {"platform": "telegram", "chat_id": "chat"},
        "work_completion": {"enabled": True, "url": "http://fixture", "database_id": "db"},
    }
    result = run_tick(config, delivery=SimpleNamespace(lookup=lambda ref: None))
    assert result["prepared_groups"] == 0
    assert result["work_completion_verified"] == 1 and result["work_completion_pending"] == 0
    assert graph.nodes[0]["status"] == "DONE"
    assert graph.posts[0] == graph.posts[1]


def test_readback_reopened_or_undone_receipt_never_recompletes(setup):
    work, graph = setup
    result = report(work)
    operation = result["operation_id"]
    graph.receipts[operation]["undone_at"] = "2026-10-20T00:00:00Z"
    graph.nodes[0]["status"] = "TODO"
    assert not report(work)["graph_verified"]
    assert graph.nodes[0]["status"] == "TODO" and len(graph.posts) == 1


def test_unknown_named_task_never_falls_back_to_active_task(setup):
    work, graph = setup
    work.store.create_round(
        Round(user_id="owner", task_id="task-a", target_outcome="A", tiny_step="B")
    )
    assert not report(work, "这个任务B完成了")["graph_verified"]
    assert not graph.posts
