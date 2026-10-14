"""Runs real Hermes hooks, stdio MCP and native delivery ledger in two isolated homes."""

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

repository, fixture_root, uuma_python = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repository / "src"))
from cron import delivery_queue, executions
from gateway.platforms.event import MessageEvent
from gateway.session import Platform, SessionSource
from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import discover_plugins, get_plugin_manager, invoke_hook
from tools.mcp_tool_common import mcp_field

from uuma.honc.life_context import LifeContextBroker


async def wire(config, token, receipt):
    environment = dict(
        os.environ,
        PYTHONPATH=str(repository / "src"),
        UUMA_DATA_DIR=str(Path(config["database_path"]).parent / "control"),
        UUMA_AGENT_ID="honc",
    )
    params = StdioServerParameters(
        command=uuma_python,
        args=["-m", "uuma.honc.mcp", "--life-config", config["config_path"]],
        env=environment,
    )
    async with stdio_client(params) as streams, ClientSession(*streams) as session:
        await session.initialize()
        listing = await session.list_tools()
        assert len(listing.tools) == 20
        response = await session.call_tool("honc_get_life_context", {"context_ref": token})
        assert mcp_field(response, "is_error", "isError") is False
        data = mcp_field(response, "structured_content", "structuredContent")
        assert data["status"] == "READ_OK"
        request = {
            "request_ref": receipt["request_refs"]["record_body"],
            "source_quote": "今天状态很好",
            "observations": [{"description": "今天状态很好"}],
        }
        saved = await session.call_tool(
            "honc_record_body", {"context_ref": token, "request": request}
        )
        saved_data = mcp_field(saved, "structured_content", "structuredContent")
        assert (
            mcp_field(saved, "is_error", "isError") is False and saved_data["status"] == "APPLIED"
        )
        repeated = await session.call_tool(
            "honc_record_body", {"context_ref": token, "request": request}
        )
        repeated_data = mcp_field(repeated, "structured_content", "structuredContent")
        assert repeated_data["status"] == "ALREADY_APPLIED"
        assert saved_data["records"] == repeated_data["records"]
        invalid = await session.call_tool(
            "honc_get_life_context", {"context_ref": "model-invented"}
        )
        assert mcp_field(invalid, "is_error", "isError") is True
        return saved_data["records"][0]["id"]


configs = []
for label in ("A", "B"):
    home = fixture_root / label / "profiles/honc"
    plugin = home / "plugins/honc_life"
    shutil.copytree(
        repository / "integrations/hermes/honc_life",
        plugin,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    config = {
        "profile": "honc",
        "owner_id": "fixture-" + label,
        "database_path": str(fixture_root / label / "data/honc.db"),
        "profile_home": str(home),
        "repository_root": str(repository),
        "delivery_binding": {"platform": "telegram", "chat_id": "fixture-" + label},
        "scheduler_job_id": "fixture-tick",
        "config_path": str(plugin / "runtime.json"),
    }
    (plugin / "runtime.json").write_text(json.dumps(config), encoding="utf-8")
    (home / "config.yaml").write_text(
        "plugins:\n  enabled: [honc_life]\n  disabled: []\n", encoding="utf-8"
    )
    configs.append(config)

ids = {}
for index in (0, 1, 0):
    config = configs[index]
    os.environ["HERMES_HOME"] = config["profile_home"]
    discover_plugins(force=False)
    manager = get_plugin_manager()
    loaded = [value for value in manager._plugins.values() if value.manifest.name == "honc_life"]
    assert len(loaded) == 1 and loaded[0].enabled
    actor = config["owner_id"]
    mid = "message-" + str(len(ids))
    event = MessageEvent(
        text="今天状态很好",
        source=SessionSource(
            platform=Platform.TELEGRAM,
            chat_id=actor,
            user_id=actor,
            profile="honc",
            chat_type="dm",
            message_id=mid,
        ),
        message_id=mid,
    )
    gateway = SimpleNamespace(
        _is_user_authorized_for_source=lambda source, actor=actor, **kwargs: source.user_id == actor
    )
    invoke_hook("pre_gateway_dispatch", event=event, gateway=gateway)
    tokens = set_session_vars(
        platform="telegram",
        chat_id=actor,
        chat_type="dm",
        user_id=actor,
        message_id=mid,
        profile="honc",
        session_id="session-" + mid,
    )
    outputs = invoke_hook(
        "pre_llm_call",
        platform="telegram",
        sender_id=actor,
        chat_id=actor,
        session_id="session-" + mid,
        turn_id="turn-" + mid,
        user_message="今天状态很好",
        parent_session_id="",
    )
    output = next(
        value["context"]
        for value in outputs
        if isinstance(value, dict) and "HONC_LIFE_CURRENT_MESSAGE" in value.get("context", "")
    )
    receipt = json.loads(output.split("\n", 1)[1])
    changes = invoke_hook(
        "pre_tool_call",
        tool_name="mcp__honc_execution__honc_get_life_context",
        args={"context_ref": "forged"},
        session_id="session-" + mid,
        turn_id="turn-" + mid,
    )
    token = next(
        value["args"]["context_ref"] for value in changes if value.get("action") == "modify"
    )
    broker = LifeContextBroker(config)
    record_id = asyncio.run(wire(config, token, receipt))
    ids[record_id] = index
    invoke_hook("post_llm_call", session_id="session-" + mid, turn_id="turn-" + mid)
    try:
        broker.service(token)
    except PermissionError:
        pass
    else:
        raise AssertionError("ended turn kept its write capability")
    clear_session_vars(tokens)

os.environ["HERMES_HOME"] = configs[0]["profile_home"]
attempt = executions.create_execution("fixture-tick", source="honc-native-fixture")
executions.mark_execution_running(attempt["id"])
job = {
    "id": "fixture-tick",
    "profile": "honc",
    "deliver": "origin",
    "origin": {"platform": "telegram", "chat_id": "fixture-A"},
    "execution_id": attempt["id"],
}
delivery_queue.enqueue(attempt["id"], job, "fixture reminder")
delivery_queue.enqueue(attempt["id"], job, "fixture reminder")
sends = []
assert delivery_queue.drain(lambda job, content, failure: sends.append((job, content)) or None) == 1
assert len(sends) == 1 and delivery_queue.get_status(attempt["id"])["status"] == "delivered"
assert delivery_queue.drain(lambda *args: sends.append(args)) == 0
executions.finish_execution(attempt["id"], success=True, delivery_outcome="delivered")
assert executions.get_execution(attempt["id"])["delivery_outcome"] == "delivered"

from cron.jobs import create_job
from cron.scheduler import SILENT_MARKER, run_job

from uuma.honc.life_models import (
    HabitConfigureRequest,
    HabitDefinitionInput,
    ReminderRule,
    ReminderSlot,
)
from uuma.honc.life_service import LifeService
from uuma.honc.native_reminders import HermesReminderDelivery

config = configs[0]
broker = LifeContextBroker(config)
observed = datetime.fromisoformat("2026-10-13T08:00:00+08:00")
service = LifeService(
    broker.store,
    owner_id=config["owner_id"],
    profile="honc",
    session_id="native-scheduler-fixture",
    reminders=broker.runtime,
)
source = service.receive_user_message(
    adapter_id="isolated-test",
    source_event_id="add-habit",
    raw_content="添加晨仪",
    received_at=observed,
    granted_operations=("configure_habit",),
)
created = service.bind_source(source["source_ref"]).configure_habit(
    HabitConfigureRequest(
        request_ref=source["request_refs"]["configure_habit"],
        source_quote="添加晨仪",
        action="create",
        definition=HabitDefinitionInput(name="晨仪", record_type="boolean"),
        reminder=ReminderRule(slots=[ReminderSlot(key="wake", trigger="wake")]),
    )
)
assert created.status == "APPLIED"
script = Path(config["profile_home"]) / "scripts/tick.py"
script.parent.mkdir()
script.write_text(
    "import sys, json\nfrom datetime import datetime\nfrom pathlib import Path\n"
    + f"sys.path.insert(0,{str(repository / 'src')!r})\n"
    + "from uuma.honc.native_reminders import run_tick\n"
    + f"config=json.loads(Path({config['config_path']!r}).read_text(encoding='utf-8'))\n"
    + "run_tick(config,now=datetime.fromisoformat('2026-10-13T08:00:00+08:00'))\n",
    encoding="utf-8",
)
native_job = create_job(
    None,
    "1m",
    name="isolated-life-tick",
    script=str(script),
    no_agent=True,
    deliver="local",
    attach_to_session=False,
    paused=True,
)
config["scheduler_job_id"] = native_job["id"]
Path(config["config_path"]).write_text(json.dumps(config), encoding="utf-8")
result = run_job(native_job)
assert result[0] is True and result[2] == SILENT_MARKER and result[3] is None, result
with broker.store.ledger.connect() as connection:
    groups = connection.execute("SELECT * FROM life_reminder_groups").fetchall()
assert len(groups) == 1 and groups[0]["state"] == "QUEUED" and groups[0]["native_execution_id"]
semantic_sends = []
assert (
    delivery_queue.drain(
        lambda job, content, failure: semantic_sends.append((job, content)) or None
    )
    == 1
)
broker.runtime.reconcile(observed, HermesReminderDelivery(config).lookup)
assert broker.runtime.list_occurrences(observed.date())[0]["consumed_count"] == 1
assert run_job(native_job)[0] is True
assert delivery_queue.drain(lambda *args: semantic_sends.append(args)) == 0
assert len(semantic_sends) == 1
print(
    json.dumps(
        {
            "result": "PASS",
            "profile_sequence": ["A", "B", "A"],
            "actual_stdio_tools": 20,
            "saved_body_records": len(ids),
            "native_queue_sends": len(sends),
            "native_scheduler_groups": len(semantic_sends),
            "real_notifications_sent": 0,
            "real_model_calls": 0,
        }
    )
)
