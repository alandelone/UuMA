"""Guide isolation, real source admission and configuration preservation contracts."""

import importlib.util
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from uuma.honc.life_context import allowed_operations

ROOT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin():
    return load("honc_guide_test", "integrations/hermes/uuma_honc_commands/__init__.py")


class Context:
    def __init__(self, profile="honc"):
        self.profile_name = profile
        self.commands = {}

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = {"handler": handler, **kwargs}

    def call_mcp(self, *args, **kwargs):
        pytest.fail("A static guide must not access records or cause model/tool calls")


def test_guide_is_honc_only_and_preserves_native_commands(plugin):
    for profile in ("default", "brainstormer", "forge-lab-bot", "yonc", "wisdom-oldman"):
        ctx = Context(profile)
        plugin.register(ctx)
        assert not ctx.commands
    ctx = Context()
    plugin.register(ctx)
    assert set(ctx.commands) == {"honc"}
    for page in ("", *plugin.SECTIONS):
        text = ctx.commands["honc"]["handler"](page)
        assert text and len(text) < 3500


def test_guide_does_not_execute_example_or_arbitrary_arguments(plugin):
    assert plugin.guide(" REST ") == plugin.REST
    assert plugin.guide("习惯") == plugin.HABITS
    assert plugin.guide("help") == plugin.GUIDE
    text = plugin.guide("新增一个习惯：午休，按分钟记录，不设提醒。")
    assert "另发一条" in text and "已新增" not in text
    assert plugin.guide("habits; remove") == text


@pytest.mark.parametrize(
    ("example", "operation"),
    [
        ("新增一个习惯：午休，按分钟记录，不设提醒。", "configure_habit"),
        ("新增一个习惯：伸展，每天15:00提醒一次，按分钟记录。", "configure_habit"),
        ("新增一个习惯：阅读，每周一到周五21:00提醒一次，按分钟记录。", "configure_habit"),
        ("修改伸展习惯的提醒，改为每天16:00一次。", "configure_habit"),
        ("暂停伸展习惯。", "configure_habit"),
        ("恢复伸展习惯。", "configure_habit"),
        ("记录午休习惯：今天午休了20分钟。", "record_habit"),
        ("记录伸展习惯：今天做了10分钟伸展。", "record_habit"),
        ("今天的伸展没做，记录为跳过。", "record_habit"),
        ("补记昨天的伸展习惯：昨天做了15分钟伸展。", "record_habit"),
        ("我起床了。", "record_anchor"),
        ("我准备睡觉了。", "record_anchor"),
        ("记录身体状态：今天有点累。", "record_body"),
    ],
)
def test_advertised_life_examples_pass_existing_source_admission(plugin, example, operation):
    assert any(example in page for page in (plugin.GUIDE, *plugin.SECTIONS.values()))
    assert operation in allowed_operations(example, ("伸展", "午休", "阅读"))


def test_history_queries_do_not_grant_completion_writes(plugin):
    for text in ("我有哪些习惯和提醒？", "查看昨天的习惯记录。", "查看午休习惯最近七天的记录。"):
        assert text in plugin.HABITS + plugin.HISTORY
        assert "record_habit" not in allowed_operations(text, ("午休", "伸展"))


def test_deployment_keeps_all_non_menu_settings_and_raw_backup(tmp_path):
    module = load("deploy_honc_guide_test", "scripts/deploy-honc-commands.py")
    profile = tmp_path / "profiles/honc"
    profile.mkdir(parents=True)
    yaml = YAML()
    config = {
        "model": {"default": "existing-model", "provider": "existing-provider"},
        "mcp_servers": {"honc-execution": {"env": {"YONC_GRAPH_URL": "http://localhost:8000"}}},
        "plugins": {"enabled": ["honc_life"], "entries": {"honc_life": {"custom": True}}},
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
    assert receipt["model_and_mcp_servers_unchanged"] and not receipt["life_records_changed"]
    for key in ("model", "mcp_servers", "quick_commands"):
        assert after[key] == config[key]
    assert after["plugins"]["entries"] == config["plugins"]["entries"]
    assert after["platforms"]["telegram"]["extra"]["custom_setting"] == 42
    assert (tmp_path / "backup/config.before.yaml").read_bytes() == before
    assert env.read_bytes() == b"fixture credential; preserve exact bytes\r\n"
    assert (profile / "plugins/uuma_honc_commands/plugin.yaml").is_file()
    with pytest.raises(ValueError):
        module.deploy(tmp_path / "profiles/brainstormer", tmp_path / "backup-other")
