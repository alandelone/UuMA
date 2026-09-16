from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

PLUGIN_PATH = (
    Path(__file__).parents[1]
    / "integrations"
    / "hermes"
    / "uuma_observability"
    / "__init__.py"
)
SPEC = importlib.util.spec_from_file_location("uuma_observability_test_plugin", PLUGIN_PATH)
assert SPEC is not None and SPEC.loader is not None
PLUGIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLUGIN
SPEC.loader.exec_module(PLUGIN)


class FakeSpan:
    def __init__(self, name: str, parent: Any, attributes: dict[str, Any]) -> None:
        self.name = name
        self.parent = parent
        self.attributes = dict(attributes)
        self.status = None
        self.ended = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: Any) -> None:
        self.status = status

    def end(self) -> None:
        self.ended = True


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_span(
        self,
        name: str,
        *,
        context: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> FakeSpan:
        span = FakeSpan(name, context, attributes or {})
        self.spans.append(span)
        return span


class FakeProvider:
    def __init__(self) -> None:
        self.flushed = False

    def force_flush(self, *, timeout_millis: int) -> None:
        self.flushed = timeout_millis == 2000


def runtime(*, capture_content: bool = False):
    tracer = FakeTracer()
    provider = FakeProvider()
    instance = PLUGIN._Runtime(
        tracer,
        provider,
        lambda span: span,
        lambda code, description: (code, description),
        profile="orchestrator",
        capture_content=capture_content,
        content_limit=512,
    )
    return instance, tracer, provider


def test_one_turn_is_root_with_llm_and_tool_children() -> None:
    instance, tracer, _provider = runtime()
    turn = {"session_id": "session-1", "turn_id": "turn-1", "user_message": "secret prompt"}
    instance.pre_llm_call(turn)
    instance.pre_api_request(
        {
            **turn,
            "api_request_id": "api-1",
            "provider": "openai",
            "model": "gpt-test",
            "tool_count": 12,
            "approx_input_tokens": 900,
            "request": {"messages": ["secret prompt"]},
        }
    )
    instance.post_api_request(
        {
            **turn,
            "api_request_id": "api-1",
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "api_duration": 1.25,
            "response": {"content": "secret response"},
        }
    )
    instance.pre_tool_call(
        {**turn, "tool_call_id": "tool-1", "tool_name": "inventory.search", "args": {"q": "private"}}
    )
    instance.post_tool_call(
        {
            **turn,
            "tool_call_id": "tool-1",
            "tool_name": "inventory.search",
            "status": "ok",
            "duration_ms": 80,
            "result": {"part": "private"},
        }
    )
    instance.post_llm_call({**turn, "assistant_response": "secret final"})

    root, llm, tool = tracer.spans
    assert root.name == "hermes.turn"
    assert root.attributes["openinference.span.kind"] == "AGENT"
    assert root.attributes["session.id"] == "session-1"
    assert "input.value" not in root.attributes
    assert llm.parent is root
    assert llm.attributes["openinference.span.kind"] == "LLM"
    assert llm.attributes["llm.token_count.total"] == 120
    assert llm.attributes["uuma.duration_ms"] == 1250
    assert "input.value" not in llm.attributes
    assert "output.value" not in llm.attributes
    assert tool.parent is root
    assert tool.attributes["openinference.span.kind"] == "TOOL"
    assert tool.attributes["uuma.duration_ms"] == 80
    assert root.ended and llm.ended and tool.ended
    assert root.status == ("OK", None)


def test_delegated_agent_remains_in_parent_trace_tree() -> None:
    instance, tracer, _provider = runtime(capture_content=True)
    instance.pre_llm_call(
        {"session_id": "parent", "turn_id": "turn-parent", "user_message": "research this"}
    )
    instance.subagent_start(
        {
            "parent_session_id": "parent",
            "parent_turn_id": "turn-parent",
            "child_session_id": "child",
            "child_subagent_id": "agent-1",
            "child_role": "scholar",
            "child_goal": "find evidence",
        }
    )
    instance.pre_llm_call(
        {"session_id": "child", "turn_id": "turn-child", "user_message": "find evidence"}
    )
    instance.post_llm_call(
        {"session_id": "child", "turn_id": "turn-child", "assistant_response": "evidence found"}
    )
    instance.subagent_stop(
        {
            "parent_session_id": "parent",
            "parent_turn_id": "turn-parent",
            "child_session_id": "child",
            "child_subagent_id": "agent-1",
            "child_status": "completed",
            "child_summary": "done",
            "duration_ms": 50,
        }
    )
    instance.post_llm_call(
        {"session_id": "parent", "turn_id": "turn-parent", "assistant_response": "final"}
    )

    root, delegation, child_turn = tracer.spans
    assert delegation.parent is root
    assert child_turn.parent is delegation
    assert child_turn.attributes["input.value"] == "find evidence"
    assert child_turn.attributes["output.value"] == "evidence found"
    assert delegation.attributes["uuma.child.status"] == "completed"
    assert all(span.ended for span in tracer.spans)


def test_failed_provider_attempt_records_retry_and_error() -> None:
    instance, tracer, _provider = runtime()
    turn = {"session_id": "session-1", "turn_id": "turn-1"}
    instance.pre_llm_call(turn)
    instance.pre_api_request({**turn, "api_request_id": "api-1", "provider": "anthropic"})
    instance.api_request_error(
        {
            **turn,
            "api_request_id": "api-1",
            "retry_count": 2,
            "max_retries": 3,
            "retryable": True,
            "error": {"type": "TimeoutError", "message": "provider timed out"},
        }
    )

    failed = tracer.spans[1]
    assert failed.ended
    assert failed.status == ("ERROR", "provider timed out")
    assert failed.attributes["uuma.retry.count"] == 2
    assert failed.attributes["error.type"] == "TimeoutError"


def test_shutdown_closes_dangling_spans_and_flushes() -> None:
    instance, tracer, provider = runtime()
    instance.pre_llm_call({"session_id": "session-1", "turn_id": "turn-1"})
    instance.pre_tool_call(
        {"session_id": "session-1", "turn_id": "turn-1", "tool_call_id": "tool-1"}
    )
    instance.shutdown()

    assert all(span.ended for span in tracer.spans)
    assert all(span.status[0] == "ERROR" for span in tracer.spans)
    assert provider.flushed
