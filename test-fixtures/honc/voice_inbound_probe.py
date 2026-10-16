"""Exercise installed Hermes inbound/STT hooks, never a real bot or speech service."""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

repository, fixture = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repository / "src"))
home = fixture / "profiles/honc"
plugin = home / "plugins/honc_life"
shutil.copytree(repository / "integrations/hermes/honc_life", plugin)
config = {
    "profile": "honc",
    "owner_id": "voice-fixture-owner",
    "profile_home": str(home),
    "repository_root": str(repository),
    "database_path": str(fixture / "honc.db"),
    "delivery_binding": {"platform": "telegram", "chat_id": "voice-fixture-owner"},
    "scheduler_job_id": "not-running",
}
(plugin / "runtime.json").write_text(json.dumps(config), encoding="utf-8")
(home / "config.yaml").write_text("plugins:\n  enabled: [honc_life]\n", encoding="utf-8")
os.environ["HERMES_HOME"] = str(home)
from gateway.platforms.event import MessageEvent, MessageType
from gateway.run_inbound import GatewayInboundMixin
from gateway.session import Platform, SessionSource
from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import discover_plugins, invoke_hook

from uuma.honc.life_context import LifeContextBroker
from uuma.honc.life_models import BodyObservation, BodyRecordRequest

discover_plugins(force=True)
broker = LifeContextBroker(config)


class Runner(GatewayInboundMixin):
    config = SimpleNamespace(multiplex_profiles=False)

    def _is_user_authorized_for_source(self, source, **kwargs):
        return source.user_id == "voice-fixture-owner"

    async def _prepare_inbound_message_text(self, *, event, **kwargs):
        if event.message_type == MessageType.VOICE:

            async def unused_fallback(path):
                raise AssertionError("successful STT must not fall back")

            def fixture_stt(*args):
                return {"success": True, "transcript": event.raw_message}

            _, wrapped = await self._transcribe_one_clip(
                "fixture.ogg",
                fixture_stt,
                unused_fallback,
            )
            return wrapped
        return event.text


async def exercise():
    runner = Runner()
    applied = []
    for index, idle in enumerate((True, False)):
        mid = str(index)
        source = SessionSource(
            platform=Platform.TELEGRAM,
            chat_id=config["owner_id"],
            user_id=config["owner_id"],
            profile="honc",
            chat_type="dm",
            message_id=mid,
        )
        event = MessageEvent(
            text="",
            source=source,
            message_id=mid,
            message_type=MessageType.VOICE,
            raw_message="今天 精神 一点 累，鼻子 流 鼻涕",
        )
        if idle:
            assert runner._hm_pre_gateway_dispatch_hook(event, source) is event
        raw = await runner._prepare_profile_scoped_inbound_message_text(
            event=event,
            source=source,
            history=[],
            session_key="fixture",
        )
        tokens = set_session_vars(
            platform="telegram",
            chat_id=config["owner_id"],
            chat_type="dm",
            user_id=config["owner_id"],
            message_id=mid,
            profile="honc",
            session_id="voice",
        )
        try:
            output = invoke_hook(
                "pre_llm_call",
                platform="telegram",
                sender_id=config["owner_id"],
                chat_id=config["owner_id"],
                session_id="voice",
                turn_id=mid,
                user_message=raw,
                parent_session_id="",
            )
            context = next(x["context"] for x in output if "HONC_LIFE" in x.get("context", ""))
            receipt = json.loads(context.split("\n", 1)[1])
            assert set(receipt["request_refs"]) == {"record_body"}
            changes = invoke_hook(
                "pre_tool_call",
                tool_name="mcp__honc_execution__honc_record_body",
                args={},
                session_id="voice",
                turn_id=mid,
            )
            token = next(x["args"]["context_ref"] for x in changes if x.get("action") == "modify")
            service = broker.service(token)
            request = BodyRecordRequest(
                request_ref=receipt["request_refs"]["record_body"],
                source_quote=raw,
                observations=[BodyObservation(description="精神 一点 累")],
            )
            result = service.record_body(request)
            repeated = service.record_body(request)
            assert result.status == "APPLIED" and repeated.status == "ALREADY_APPLIED"
            assert result.records == repeated.records
            with broker.store.ledger.connect() as connection:
                stored = connection.execute(
                    "SELECT raw_content FROM life_sources WHERE source_ref=?",
                    (receipt["source_ref"],),
                ).fetchone()[0]
                assert stored == raw
            applied.append(result.records[0].id)
            invoke_hook("post_llm_call", session_id="voice", turn_id=mid)
        finally:
            clear_session_vars(tokens)
    assert len(set(applied)) == 2
    print(json.dumps({"status": "PASS", "idle_and_queued_saved": 2, "duplicate_facts": 0}))


asyncio.run(exercise())
