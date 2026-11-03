"""Guide isolation, command registration and configuration preservation contracts for Yonc."""

import importlib.util
from pathlib import Path

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin(monkeypatch):
    monkeypatch.setenv("YONC_API_URL", "http://127.0.0.1:0")
    return load("yonc_guide_test", "integrations/hermes/uuma_yonc_commands/__init__.py")


class Context:
    def __init__(self, profile="yonc"):
        self.profile_name = profile
        self.commands = {}

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = {"handler": handler, **kwargs}

    def call_mcp(self, *args, **kwargs):
        pytest.fail("A static guide must not access records or cause model/tool calls")


def test_guide_is_yonc_only_and_registers_dual_forms(plugin):
    for profile in ("default", "brainstormer", "forge-lab-bot", "honc", "wisdom-oldman"):
        ctx = Context(profile)
        plugin.register(ctx)
        assert not ctx.commands
    ctx = Context("yonc")
    plugin.register(ctx)
    base_commands = {
        "yonc",
        "yonc_split",
        "yonc-split",
        "yonc_projects",
        "yonc-projects",
        "yonc_assign",
        "yonc-assign",
        "yonc_history",
        "yonc-history",
        "yonc_graph",
        "yonc-graph",
    }
    assert base_commands.issubset(set(ctx.commands))
    assert "yonc_projects_1" in ctx.commands
    assert "yonc_split_1_1" in ctx.commands
    assert "yonc_projects_1_1" in ctx.commands
    assert "yonc_context_1_1" in ctx.commands
    assert "yonc_action_1_1" in ctx.commands
    for page in ("", *plugin.SECTIONS):
        text = ctx.commands["yonc"]["handler"](page)
        assert text and len(text) < 3500
    for cmd in base_commands:
        text = ctx.commands[cmd]["handler"]()
        assert text and len(text) < 3500
    # Also verify direct fast subcommands execute cleanly and stay under limit
    assert len(ctx.commands["yonc_split_1_1"]["handler"]()) < 3500
    assert len(ctx.commands["yonc_projects_1"]["handler"]()) < 3500
    assert len(ctx.commands["yonc_projects_1_1"]["handler"]()) < 3500
    assert len(ctx.commands["yonc_context_1_1"]["handler"]()) < 3500
    assert len(ctx.commands["yonc_action_1_1"]["handler"]()) < 3500


def test_guide_does_not_execute_example_or_arbitrary_arguments(plugin):
    assert plugin.guide(" SPLIT ") == plugin.SPLIT
    assert plugin.guide("yonc_split") == plugin.SPLIT
    assert plugin.guide("yonc-split") == plugin.SPLIT
    assert plugin.guide("拆解") == plugin.SPLIT
    assert plugin.guide("projects") == plugin.PROJECTS
    assert plugin.guide("yonc_projects") == plugin.PROJECTS
    assert plugin.guide("项目") == plugin.PROJECTS
    assert plugin.guide("assign") == plugin.ASSIGN
    assert plugin.guide("yonc_assign") == plugin.ASSIGN
    assert plugin.guide("指派") == plugin.ASSIGN
    assert plugin.guide("history") == plugin.HISTORY
    assert plugin.guide("yonc_history") == plugin.HISTORY
    assert plugin.guide("历史") == plugin.HISTORY
    assert plugin.guide("graph") == plugin.GRAPH
    assert plugin.guide("yonc_graph") == plugin.GRAPH
    assert plugin.guide("help") == plugin.GUIDE
    text = plugin.guide("准备拆解项目〈项目名称〉，目标是两周内上线，先列出主要 Action。")
    assert "没有这个手册章节" in text
    assert plugin.guide("split; remove") == text


def test_deployment_keeps_all_non_menu_settings_and_raw_backup(tmp_path):
    module = load("deploy_yonc_guide_test", "scripts/deploy-yonc-commands.py")
    profile = tmp_path / "profiles/yonc"
    profile.mkdir(parents=True)
    yaml = YAML()
    config = {
        "model": {"default": "existing-model", "provider": "existing-provider"},
        "mcp_servers": {"yonc-project": {"env": {"YONC_API_URL": "http://localhost:8766"}}},
        "plugins": {"enabled": ["uuma_audit"], "entries": {"uuma_audit": {"custom": True}}},
        "quick_commands": {"existing": {"type": "alias", "target": "/help"}},
        "platforms": {"telegram": {"extra": {"custom_setting": 42}}},
    }
    config_path = profile / "config.yaml"
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.dump(config, stream)
    before = config_path.read_bytes()
    env = profile / ".env"
    env.write_bytes(b"fixture credential; preserve exact bytes\r\n")
    receipt = module.deploy(profile, tmp_path / "backup")
    after = yaml.load(config_path.read_text(encoding="utf-8"))
    assert receipt["model_and_mcp_servers_unchanged"] and not receipt["graph_state_changed"]
    for key in ("model", "mcp_servers", "quick_commands"):
        assert after[key] == config[key]
    assert after["plugins"]["entries"] == config["plugins"]["entries"]
    assert "uuma_yonc_commands" in after["plugins"]["enabled"]
    assert after["platforms"]["telegram"]["extra"]["custom_setting"] == 42
    assert after["platforms"]["telegram"]["extra"]["command_menu"]["priority"][0] == "yonc"
    assert (tmp_path / "backup/config.before.yaml").read_bytes() == before
    assert env.read_bytes() == b"fixture credential; preserve exact bytes\r\n"
    assert (profile / "plugins/uuma_yonc_commands/plugin.yaml").is_file()
    with pytest.raises(ValueError):
        module.deploy(tmp_path / "profiles/brainstormer", tmp_path / "backup-other")


def test_split_and_projects_real_timeline_navigation(plugin):
    split_text = plugin.render_split()
    assert "目标拆解与规划" in split_text
    assert "Timeline / Deadline" in split_text
    assert "Thesis Phd Logic" in split_text
    assert "1.1" in split_text
    assert "准备拆解 1.1〈Thesis Phd Logic〉" in split_text
    assert len(split_text) < 3500

    # Number lookup on split (e.g. 1.1)
    split_item = plugin.render_split("1.1")
    assert "待拆解项目：1.1〈Thesis Phd Logic〉" in split_item
    assert "准备拆解 1.1〈Thesis Phd Logic〉" in split_item
    assert len(split_item) < 3500

    # Keyword filtering on split
    filtered_split = plugin.render_split("素食堂")
    assert "素食堂 菜单开发" in filtered_split
    assert "准备拆解 1.1〈素食堂 菜单开发〉" in filtered_split
    assert len(filtered_split) < 3500

    # Projects categorisation overview
    proj_text = plugin.render_projects()
    assert "真实项目库总览" in proj_text
    assert "博士与科研" in proj_text
    assert "小事业群" in proj_text
    assert "Thesis Phd Logic" in proj_text
    assert "1.1" in proj_text
    assert len(proj_text) < 3500

    # Group expansion on projects (e.g. 1)
    group_proj = plugin.render_projects("1")
    assert "分类详情：1. 🎓 博士与科研" in group_proj
    assert "1.1 Thesis Phd Logic" in group_proj
    assert len(group_proj) < 3500

    # Number lookup on projects (e.g. 1.1)
    item_proj = plugin.render_projects("1.1")
    assert "项目详情：1.1〈Thesis Phd Logic〉" in item_proj
    assert "查询项目 1.1〈Thesis Phd Logic〉" in item_proj
    assert len(item_proj) < 3500

    # Keyword filtering on projects
    filtered_proj = plugin.render_projects("素食堂")
    assert "素食堂 菜单开发" in filtered_proj
    assert "查询项目 1.1〈素食堂 菜单开发〉" in filtered_proj
    assert len(filtered_proj) < 3500

