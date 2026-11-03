import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def module():
    path = Path(__file__).parents[1] / "integrations/hermes/uuma_wisdom_commands/__init__.py"
    spec = importlib.util.spec_from_file_location("wisdom_commands_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Context:
    profile_name = "wisdom-oldman"

    def __init__(self):
        self.commands = {}
        self.calls = []
        self.failure = False
        self.rows = [{"topic_id": "topic_a", "title": "咖啡", "status": "ACTIVE"}]

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler

    def call_mcp(self, server, tool, arguments, **kwargs):
        assert server == "wisdom-knowledge"
        assert tool in {"knowledge_topic_list", "knowledge_topic_get", "knowledge_orbit_list"}
        self.calls.append((tool, arguments))
        if self.failure:
            return {"ok": False}
        orbit = {
            "status": "BLOCKED",
            "objective": "验证成本",
            "stop_reason": "缺少来源",
            "updated_at": "2026-10-20T08:00:00Z",
        }
        results = {
            "knowledge_topic_list": {"records": self.rows},
            "knowledge_orbit_list": {"records": [orbit]},
            "knowledge_topic_get": {
                "topic": self.rows[0],
                "document": {"current_version": 2},
                "orbits": [orbit],
                "questions": [{"question": {"text": "租金多少", "status": "OPEN"}}],
                "document_url": "http://localhost/wisdom/topics/topic_a",
            },
        }
        return {"ok": True, "result": json.dumps(results[tool])}


def test_registration_only_for_wisdom_and_no_builtin_override(module):
    ctx = Context()
    ctx.profile_name = "brainstormer"
    module.register(ctx)
    assert ctx.commands == {}
    ctx.profile_name = "wisdom-oldman"
    module.register(ctx)
    assert {"topics", "progress", "wisdom"}.issubset(set(ctx.commands))
    assert "progress_1" in ctx.commands
    assert "topics_1" in ctx.commands
    assert "只查询" in asyncio.run(ctx.commands["wisdom"]())


def test_list_and_progress_use_only_read_tools(module):
    ctx = Context()
    module.register(ctx)
    assert "/progress topic_a" in asyncio.run(ctx.commands["topics"]())
    assert "topics_1" in ctx.commands
    assert "progress_1" in ctx.commands
    assert "验证成本" in asyncio.run(ctx.commands["progress_1"]())
    assert "咖啡" in asyncio.run(ctx.commands["topics_1"]())
    assert "受阻" in asyncio.run(ctx.commands["progress"]())
    detail = asyncio.run(ctx.commands["progress"]("咖啡"))
    assert "缺少来源" in detail and "租金多少" in detail and "版本：2" in detail
    assert {tool for tool, _ in ctx.calls} == {
        "knowledge_topic_list",
        "knowledge_topic_get",
        "knowledge_orbit_list",
    }


def test_duplicates_missing_and_errors_do_not_create_or_bind(module):
    ctx = Context()
    commands = module.WisdomCommands(ctx)
    ctx.rows *= 2
    assert "多个" in commands.run("progress", "咖啡")
    assert not any(tool == "knowledge_topic_get" for tool, _ in ctx.calls)
    assert "找不到" in commands.run("progress", "不存在")
    ctx.failure = True
    assert "未完成" in commands.run("topics")
    assert "暂无" not in commands.run("progress")


def test_paging_and_bounded_messages(module):
    ctx = Context()
    ctx.rows = [
        {"topic_id": f"topic_{i}", "title": "x" * 500, "status": "ACTIVE"} for i in range(20)
    ]
    commands = module.WisdomCommands(ctx)
    output = commands.run("topics", "2")
    assert "topic_8" in output and "下一页：/topics 3" in output
    assert len(output) <= 3500
    assert "没有这一页" in commands.run("topics", "100")
    assert "未完成" in commands.run("topics", "-1")


def test_failed_or_truncated_receipt_is_never_empty(module):
    ctx = Context()
    ctx.call_mcp = lambda *a, **kw: {"ok": True, "truncated": True, "result": {"records": []}}
    assert "未完成" in module.WisdomCommands(ctx).run("progress")


def test_cold_command_initializes_only_knowledge_server_and_retries_read(module, monkeypatch):
    import sys
    from types import SimpleNamespace

    ctx = Context()
    original = ctx.call_mcp
    attempts = []
    initialized = []

    def read(*args, **kwargs):
        attempts.append(args[1])
        if len(attempts) == 1:
            return {"ok": False, "error": "MCP server 'wisdom-knowledge' is not connected"}
        return original(*args, **kwargs)

    ctx.call_mcp = read
    monkeypatch.setitem(
        sys.modules,
        "tools.mcp_tool_discovery",
        SimpleNamespace(
            discover_mcp_tools=lambda allowed_mcp_names: initialized.append(allowed_mcp_names)
        ),
    )
    assert "咖啡" in module.WisdomCommands(ctx).run("topics")
    assert initialized == [["wisdom-knowledge"]]
    assert attempts == ["knowledge_topic_list", "knowledge_topic_list"]


def test_deployment_preserves_backend_model_and_other_plugins(tmp_path):
    import yaml

    path = Path(__file__).parents[1] / "scripts/deploy-wisdom-commands.py"
    spec = importlib.util.spec_from_file_location("wisdom_deploy_test", path)
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    profile = tmp_path / "wisdom-oldman"
    profile.mkdir()
    before = {
        "model": {"default": "unchanged"},
        "mcp_servers": {"knowledge": {"x": 1}},
        "plugins": {"enabled": ["existing"], "entries": {"existing": {"x": 1}}},
    }
    raw = yaml.safe_dump(before).encode()
    (profile / "config.yaml").write_bytes(raw)
    backup = tmp_path / "backup"
    assert deploy.deploy(profile, backup)["model_and_mcp_servers_unchanged"]
    assert (backup / "config.before.yaml").read_bytes() == raw
    after = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8"))
    assert after["plugins"]["entries"]["existing"] == {"x": 1}
    assert after["plugins"]["entries"]["uuma_wisdom_commands"]["mcp_allowlist"] == [
        "wisdom-knowledge"
    ]


def screenshot_tasks():
    return [
        {
            "status": "FAILED",
            "objective": 'Resolve the worthwhile evidence gaps for: "OK，继续继续继续。"',
            "stop_reason": "The synthesis model did not return source-linked JSON after two attempts: URLError.",
            "orbit_id": "orbit_1",
            "updated_at": "2026-10-20T05:00:00Z",
        },
        {
            "status": "STOPPED",
            "objective": "Resolve the worthwhile evidence gaps for: how is your progress?",
            "stop_reason": "A progress request was incorrectly processed as research and matched to a generic topic.",
            "orbit_id": "orbit_2",
            "updated_at": "2026-10-20T04:00:00Z",
        },
        {
            "status": "STOPPED",
            "objective": 'Resolve the worthwhile evidence gaps for: {"detail":"Wisdom topic not found"}',
            "stop_reason": "Invalid topic originated from a Wisdom 404 error payload; retract erroneous research.",
            "orbit_id": "orbit_3",
            "updated_at": "2026-10-20T03:00:00Z",
        },
        {
            "status": "BUDGET_EXHAUSTED",
            "objective": "Verify restart-safe unattended research with two public sources and located evidence.",
            "stop_reason": "The Orbit reached at least one configured research budget limit.",
            "orbit_id": "orbit_4",
            "updated_at": "2026-10-20T02:00:00Z",
        },
        {
            "status": "FAILED",
            "objective": "Verify restart-safe unattended research with two public sources and located evidence.",
            "stop_reason": 'KAG recovery failed: time="2026-09-21T11:39:35+08:00" level=warning msg="C:\\Users\\Alandelone\\CodeSpace_Local\\UuMA\\.uuma-local\\kag\\docker-compose-west.yml"',
            "orbit_id": "orbit_5",
            "updated_at": "2026-10-20T01:00:00Z",
        },
    ]


def test_screenshot_overview_separates_current_from_history_without_technical_logs(module):
    rows = screenshot_tasks()
    output = module.progress_overview(rows)
    assert "目前没有正在运行或排队的研究" in output
    assert "失败 2" in output and "已停止 2" in output and "预算已用完 1" in output
    assert output.index("需要留意") < output.index("历史记录")
    assert "进度查询（历史误建）" in output and "错误响应（历史误建）" in output
    assert "Resolve the worthwhile" not in output and "Verify restart-safe" not in output
    assert "URLError" not in output and "C:\\Users" not in output and "level=warning" not in output
    assert "未能连接" in output and "/progress detail 1" in output
    assert len(output) < 1000
    # Presentation changes never alter historical task records or reasons.
    assert rows == screenshot_tasks()


def test_raw_reason_available_only_on_explicit_detail_request(module):
    ctx = Context()
    rows = screenshot_tasks()
    ctx.call_mcp = lambda *a, **kw: {"ok": True, "result": {"records": rows}}
    commands = module.WisdomCommands(ctx)
    ordered = module.progress_rows(rows)
    index = next(i for i, row in enumerate(ordered, 1) if row["orbit_id"] == "orbit_5")
    assert "KAG recovery failed" not in commands.run("progress")
    detail = commands.run("progress", f"detail {index}")
    assert "原始原因（历史记录）" in detail and "KAG recovery failed" in detail
    assert "orbit_5" in detail
    assert "没有这条" in commands.run("progress", "detail 100")


def test_running_tasks_rank_ahead_of_historical_failures_and_history_is_paged(module):
    rows = screenshot_tasks() * 3
    rows.append({"status": "ACTIVE", "objective": "咖啡店选址", "updated_at": "2026-10-01"})
    ctx = Context()
    ctx.call_mcp = lambda *a, **kw: {"ok": True, "result": {"records": rows}}
    commands = module.WisdomCommands(ctx)
    output = commands.run("progress")
    assert "进行或排队中：1 项" in output and "1. 咖啡店选址" in output
    assert output.index("当前研究") < output.index("历史记录")
    assert "/progress page 2" in output
    assert "第 2 页" in commands.run("progress", "page 2")
    assert "原始记录：/progress detail 9" in commands.run("progress", "page 2")


def test_unknown_technical_reason_is_not_fabricated_or_dumped_into_overview(module):
    row = {"status": "FAILED", "objective": "租金调查", "stop_reason": "UnhandledVendorError=xyz"}
    output = module.progress_overview([row])
    assert "具体原因见详细记录" in output and "UnhandledVendorError" not in output
    assert "UnhandledVendorError" in module.task_detail(row, 1)
