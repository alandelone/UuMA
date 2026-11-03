"""Isolated contracts: production databases, profiles and Telegram are never contacted."""

import importlib.util
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from uuma.brainstormer_navigation import BrainstormerNavigation
from uuma.brainstormer_state import BrainstormerStore


class Bindings:
    def __init__(self):
        self.rows = {}

    def get_binding(self, user):
        return self.rows.get(user)

    def set_binding(self, user, project, topic):
        self.rows[user] = {"active_project_id": project, "active_topic_id": topic}


@pytest.fixture
def navigation(tmp_path):
    return BrainstormerNavigation(
        SimpleNamespace(
            store=BrainstormerStore(tmp_path),
            db=Bindings(),
            get_project_lock=lambda project: threading.RLock(),
        )
    )


def create(nav, title, ref, user="owner"):
    return nav.execute({"action": "create", "user_id": user, "title": title, "source_ref": ref})


def test_switch_restores_topic_checkpoint_and_does_not_resolve(navigation):
    first = create(navigation, "咖啡店", "telegram:1:1")
    binding = first["binding"]
    turn = {
        "action": "turn",
        "user_id": "owner",
        "project_id": binding["active_project_id"],
        "topic_id": binding["active_topic_id"],
        "text": "预算待验证，不是决定",
        "source_ref": "msg:2",
    }
    assert navigation.execute(turn)["status"] == "saved"
    assert navigation.execute(turn)["status"] == "already_saved"
    create(navigation, "实验田", "telegram:1:3")
    restored = navigation.execute({"action": "switch", "user_id": "owner", "selector": "咖啡店"})
    assert restored["context"]["latest_checkpoint"]["text"] == turn["text"]
    assert not any(x["kind"] == "decision" for x in restored["context"]["objects"])
    assert (
        next(x for x in restored["context"]["objects"] if x["kind"] == "topic")["status"]
        == "ACTIVE"
    )
    # A process restart preserves canonical objects and all progress.
    restarted = BrainstormerNavigation(
        SimpleNamespace(
            store=BrainstormerStore(navigation.daemon.store.root),
            db=navigation.daemon.db,
            get_project_lock=lambda p: threading.RLock(),
        )
    )
    assert restarted.execute({"action": "context", "user_id": "owner"}) == {
        k: v for k, v in restored.items() if k != "status"
    }


def test_idempotent_create_explicit_review_and_duplicate_titles(navigation):
    first = create(navigation, "预算", "msg:1")
    assert create(navigation, "预算", "msg:1")["binding"] == first["binding"]
    create(navigation, "预算", "msg:2")
    result = navigation.execute({"action": "switch", "user_id": "owner", "selector": "预算"})
    assert result["status"] == "ambiguous"
    assert len(result["matches"]) == 2
    proposals = [
        navigation.daemon.store.get_proposal(p.stem)
        for p in navigation.daemon.store.proposals.glob("*.json")
    ]
    assert all(p["reviewed_by"] == "user" and p["review_required"] for p in proposals)


def test_turn_finishing_after_switch_stays_in_original_topic(navigation):
    first = create(navigation, "A", "msg:1")
    create(navigation, "B", "msg:2")
    navigation.execute(
        {
            "action": "turn",
            "user_id": "owner",
            "role": "assistant",
            "project_id": first["binding"]["active_project_id"],
            "topic_id": first["binding"]["active_topic_id"],
            "source_ref": "msg:3",
            "text": "A的答复",
        }
    )
    current = navigation.execute({"action": "context", "user_id": "owner"})
    assert current["context"]["latest_checkpoint"] is None
    assert navigation.execute({"action": "context", "user_id": "other"})["context"] is None


def test_corrupt_store_is_error_not_empty(navigation):
    result = create(navigation, "A", "msg:1")
    path = navigation.daemon.store.projects / result["binding"]["active_project_id"] / "state.json"
    path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        navigation.execute({"action": "list", "user_id": "owner"})


def test_latest_checkpoint_uses_time_even_when_ids_sort_backwards(navigation):
    from uuma.brainstormer_state import StateOperation, StateTransaction

    created = create(navigation, "A", "msg:1")
    binding = created["binding"]
    store = navigation.daemon.store
    for target, text in [("zz_old", "old"), ("aa_new", "new")]:
        tx = StateTransaction(
            project_id=binding["active_project_id"],
            rationale="Progress",
            operations=[
                StateOperation(
                    action="CHECKPOINT",
                    kind="checkpoint",
                    target_id=target,
                    values={"title": text, "topic_id": binding["active_topic_id"]},
                )
            ],
        )
        proposal = store.propose(tx, requested_by="owner")
        store.commit_safe(proposal["proposal_id"], actor_id="owner")
    assert navigation.context("owner")["context"]["latest_checkpoint"]["id"] == "aa_new"


@pytest.fixture
def plugin():
    path = Path(__file__).parents[1] / "integrations/hermes/uuma_brainstormer_commands/__init__.py"
    spec = importlib.util.spec_from_file_location("brainstormer_plugin_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_commands_are_explicit_and_normal_discussion_is_untouched(plugin):
    assert plugin.parse_command("/topics@my_bot 咖啡店") == ("topics", "咖啡店")
    assert plugin.parse_command("/topics_1") == ("topics", "index 1")
    assert plugin.parse_command("/topics_page_2") == ("topics", "page 2")
    assert plugin.parse_command("切换到 实验田") == ("topics", "实验田")
    assert plugin.parse_command("新建议题：预算") == ("topics", "new 预算")
    assert plugin.parse_command("如果以后切换到咖啡店，要多少钱？") is None
    assert plugin.parse_command("/new") is None
    assert plugin.parse_command("/model") is None


def test_plugin_profile_and_sender_isolation(plugin):
    ctx = SimpleNamespace(profile_name="forge-lab-bot")
    plugin.register(ctx)  # Must not even inspect settings for another profile.
    commands = plugin.BrainstormerCommands(
        SimpleNamespace(get_config=lambda key, default=None: {"owner_id": "1"}.get(key, default))
    )
    source = SimpleNamespace(
        profile="brainstormer",
        platform=SimpleNamespace(value="telegram"),
        chat_type="dm",
        user_id="2",
        chat_id="1",
        is_bot=False,
    )
    event = SimpleNamespace(source=source, internal=False, message_id="3", text="/topics")
    assert commands.inbound(event, SimpleNamespace()) is None
    source.user_id = "1"
    gateway = SimpleNamespace(_is_user_authorized_for_source=lambda *a, **k: False)
    assert commands.inbound(event, gateway) is None
    assert not commands.pending


def test_actual_plugin_command_roundtrip_and_no_inferred_decisions(plugin, navigation):
    commands = plugin.BrainstormerCommands(
        SimpleNamespace(get_config=lambda key, default=None: {"owner_id": "1"}.get(key, default))
    )
    commands.rpc = lambda action, **kw: navigation.execute(
        {"action": action, "user_id": "owner", **kw}
    )
    text, _ = commands.command("topics", "new 咖啡店", "msg:1")
    assert "咖啡店" in text and "暂无记录" in text
    text, buttons = commands.command("topics", "", "msg:2")
    assert buttons == []
    assert "切换：/topics 咖啡店" in text
    assert "1 个" in text
    text, _ = commands.command("topics", "不存在", "msg:3")
    assert "找不到" in text


def test_verified_turn_restores_and_saves_to_original_binding(plugin, navigation, monkeypatch):
    import sys

    create(navigation, "A", "msg:1")
    commands = plugin.BrainstormerCommands(
        SimpleNamespace(get_config=lambda key, default=None: {"owner_id": "1"}.get(key, default))
    )
    commands.rpc = lambda action, **kw: navigation.execute(
        {"action": action, "user_id": "owner", **kw}
    )
    env = {
        "HERMES_SESSION_PROFILE": "brainstormer",
        "HERMES_SESSION_USER_ID": "1",
        "HERMES_SESSION_CHAT_ID": "1",
        "HERMES_SESSION_MESSAGE_ID": "7",
    }
    monkeypatch.setitem(
        sys.modules,
        "gateway.session_context",
        SimpleNamespace(get_session_env=lambda key: env.get(key, "")),
    )
    commands.pending["7"] = ("讨论A的预算", "msg:7")
    context = commands.pre_llm(platform="telegram", session_id="s", turn_id="t")
    assert "BRAINSTORMER_ACTIVE_TOPIC" in context["context"]
    assert '"title": "A"' in context["context"]
    create(navigation, "B", "msg:2")
    commands.post_llm(session_id="s", turn_id="t", assistant_response="A需要验证租金")
    assert navigation.context("owner")["context"]["latest_checkpoint"] is None
    restored = navigation.execute({"action": "switch", "user_id": "owner", "selector": "A"})
    assert restored["context"]["latest_checkpoint"]["text"] == "A需要验证租金"
    assert not commands.turns


def test_unauthenticated_turn_cannot_restore_or_save(plugin, monkeypatch):
    import sys

    commands = plugin.BrainstormerCommands(
        SimpleNamespace(get_config=lambda key, default=None: {"owner_id": "1"}.get(key, default))
    )
    commands.rpc = lambda *a, **kw: pytest.fail("Must not read state for an unverified turn")
    monkeypatch.setitem(
        sys.modules, "gateway.session_context", SimpleNamespace(get_session_env=lambda key: "")
    )
    assert commands.pre_llm(platform="telegram", session_id="s", turn_id="t") is None


def test_navigation_http_contract_uses_isolated_db(tmp_path):
    import os
    import subprocess
    import sys

    code = """
from fastapi.testclient import TestClient
from uuma.state_daemon import app
client = TestClient(app)
empty = client.post('/api/v1/navigation', json={'action':'list','user_id':'owner'})
assert empty.status_code == 200 and empty.json()['topics'] == []
created = client.post('/api/v1/navigation', json={
    'action':'create','user_id':'owner','title':'A','source_ref':'telegram:1:1'})
assert created.status_code == 200, created.text
binding = created.json()['binding']
saved = client.post('/api/v1/navigation', json={
    'action':'turn','user_id':'owner','project_id':binding['active_project_id'],
    'topic_id':binding['active_topic_id'],'source_ref':'telegram:1:2','text':'resume me'})
assert saved.status_code == 200, saved.text
restored = client.post('/api/v1/navigation', json={'action':'context','user_id':'owner'})
assert restored.json()['context']['latest_checkpoint']['text'] == 'resume me'
invalid = client.post('/api/v1/navigation', json={'action':'delete','user_id':'owner'})
assert invalid.status_code == 422
"""
    env = {**os.environ, "UUMA_DATA_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "uuma.db").is_file()


@pytest.mark.parametrize("backend_failure", [False, True])
def test_authenticated_delivery_removes_persistent_keyboard(
    plugin, navigation, monkeypatch, backend_failure,
):
    import asyncio
    import sys

    monkeypatch.setitem(
        sys.modules, "telegram",
        SimpleNamespace(ReplyKeyboardRemove=lambda: {"remove_keyboard": True}),
    )

    create(navigation, "A", "msg:1")
    commands = plugin.BrainstormerCommands(
        SimpleNamespace(get_config=lambda key, default=None: {"owner_id": "1"}.get(key, default))
    )
    commands.rpc = lambda action, **kw: navigation.execute(
        {"action": action, "user_id": "owner", **kw}
    )
    if backend_failure:
        def fail_backend(*args, **kwargs):
            raise OSError("isolated backend unavailable")

        commands.rpc = fail_backend
    delivered = []

    async def send(chat_id, text, **kwargs):
        delivered.append((chat_id, text, kwargs))
        return SimpleNamespace(success=True)

    source = SimpleNamespace(
        profile="brainstormer",
        platform=SimpleNamespace(value="telegram"),
        chat_type="dm",
        user_id="1",
        chat_id="1",
        is_bot=False,
    )
    event = SimpleNamespace(source=source, internal=False, message_id="3", text="/topics")
    gateway = SimpleNamespace(
        _is_user_authorized_for_source=lambda *a, **kw: True,
        _check_slash_access=lambda *a: None,
        _delivery_adapter_for=lambda source: SimpleNamespace(_send_control_message=send),
    )

    async def run():
        result = commands.inbound(event, gateway)
        assert result["action"] == "skip"
        await asyncio.gather(*commands.tasks)

    asyncio.run(run())
    assert delivered[0][0] == "1"
    assert ("暂时无法" if backend_failure else "A") in delivered[0][1]
    assert delivered[0][2]["reply_markup"] == {"remove_keyboard": True}


def test_deployment_preserves_model_and_unrelated_config(tmp_path):
    import yaml

    path = Path(__file__).parents[1] / "scripts/deploy-brainstormer-commands.py"
    spec = importlib.util.spec_from_file_location("navigation_deploy_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = tmp_path / "profiles/brainstormer"
    profile.mkdir(parents=True)
    (tmp_path / ".env").write_text("TELEGRAM_ALLOWED_USERS=123\n", encoding="utf-8")
    before = {
        "model": {"provider": "existing", "default": "preserve-me"},
        "mcp_servers": {"other": {"env": {"EXAMPLE": "unchanged"}}},
        "plugins": {"enabled": ["other_plugin"], "entries": {"other_plugin": {"x": 1}}},
        "platforms": {"telegram": {"extra": {"custom": True}}},
    }
    config = profile / "config.yaml"
    raw = yaml.safe_dump(before).encode()
    config.write_bytes(raw)
    receipt = module.deploy(profile, tmp_path / "backup")
    after = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert receipt["model_and_servers_unchanged"]
    assert (
        after["plugins"]["entries"]["other_plugin"] == before["plugins"]["entries"]["other_plugin"]
    )
    assert after["platforms"]["telegram"]["extra"]["custom"] is True
    assert (tmp_path / "backup/config.before.yaml").read_bytes() == raw
