from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "integrations/hermes/uuma_forge_commands/__init__.py"
SPEC = importlib.util.spec_from_file_location("forge_commands_test", SOURCE)
assert SPEC and SPEC.loader
PLUGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLUGIN)


class Context:
    profile_name = "forge-lab-bot"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.commands = {}
        self.calls = []
        self.result = {"ok": True, "result": {}}

    def get_config(self, _key, _default=None):
        return str(self.root)

    def register_command(self, name, handler, **_kwargs):
        self.commands[name] = handler

    def call_mcp(self, server, tool, arguments, timeout):
        self.calls.append((server, tool, arguments))
        return self.result


@pytest.fixture
def context(tmp_path):
    project = tmp_path / "projects/demo"
    (project / "bom").mkdir(parents=True)
    (project / "project.yaml").write_text(
        'project_code: "007"\nname: Demo Pump\nstatus: concept\n', encoding="utf-8"
    )
    (project / "bom/pump-candidates.csv").write_text("name,quantity\npump,2\n", encoding="utf-8")
    return Context(tmp_path)


def test_profile_isolation_and_no_builtin_overrides(context):
    PLUGIN.register(context)
    assert {"inventory", "projects", "shortages", "worklog", "forge", "cancel"} == set(
        context.commands
    )
    assert not {"model", "help", "new", "stop"} & context.commands.keys()
    context.profile_name = "yonc"
    assert "仅供 forge-lab-bot" in context.commands["inventory"]("")
    assert not context.calls
    other = Context(context.root)
    other.profile_name = "yonc"
    PLUGIN.register(other)
    assert not other.commands
    context.profile_name = "forge-lab-bot"
    assert "Hermes" in context.commands["forge"]("")
    assert not context.calls


def test_inventory_keeps_purchase_evidence_separate(context):
    context.result = {"ok": True, "result": {
        "balances": [{"component_id": "part-1", "quantity": 3, "bucket": "AVAILABLE",
                      "location_id": "drawer-2"}],
        "purchase_history_count": 18, "purchase_review_count": 4,
    }}
    out = PLUGIN.ForgeCommands(context).run("inventory")
    assert "part-1：3" in out and "drawer-2" in out
    assert "18 条" in out and "采购不等于入库" in out
    assert context.calls == [("uuma-worker", "inventory_status", {})]


@pytest.mark.parametrize("result", [
    {"ok": False, "error": "offline"},
    {"ok": True, "result": {}, "truncated": True},
    {"ok": True, "result": {}},
])
def test_failed_reads_are_never_reported_as_zero_stock(context, result):
    context.result = result
    out = PLUGIN.ForgeCommands(context).run("inventory")
    assert "查询未完成" in out
    assert "0 条" not in out


def test_projects_separate_definitions_from_physical_builds(context):
    context.result = {"ok": True, "result": {"builds": [{"build_id": "build-1", "status": "OPEN"}]}}
    out = PLUGIN.ForgeCommands(context).run("projects", "pump")
    assert "PROJ-007 Demo Pump" in out
    assert "concept" in out and "build-1" in out
    assert "独立于项目设计列表" in out
    assert context.calls == [("uuma-worker", "lab_list_builds", {"limit": 5})]


def test_shortages_candidates_are_not_confirmed_shortage(context):
    commands = PLUGIN.ForgeCommands(context)
    out = commands.run("shortages")
    assert "1 条候选" in out and "不是已确认缺料" in out
    assert not context.calls
    out = commands.run("shortages", "../outside.csv")
    assert "工作区 projects/" in out and not context.calls
    context.result = {"ok": True, "result": {"inventory": {
        "status": "SHORTAGE", "items": [{"component_id": "pump", "required": 2,
                                          "available": 0, "shortage": 2}],
    }}}
    out = commands.run("shortages", "projects/demo/bom/pump-candidates.csv")
    assert "需要 2，可用 0，缺少 2" in out
    assert "未创建采购或库存操作" in out
    assert context.calls[0][1] == "lab_analyze_bom"


def test_worklog_is_read_only_and_preserves_user_text(context):
    context.result = {"ok": True, "result": {"worklogs": [{
        "project_name": "pump", "action": "测试 24V", "result": "尚待复测",
        "occurred_at": "2026-10-19T10:00:00Z",
    }]}}
    out = PLUGIN.ForgeCommands(context).run("worklog", "pump")
    assert "测试 24V" in out and "尚待复测" in out and "不写入日志" in out
    assert context.calls == [("uuma-worker", "lab_list_worklogs", {"project_name": "pump", "limit": 5})]
