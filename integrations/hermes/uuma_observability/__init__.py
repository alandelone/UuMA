"""Fail-open OpenTelemetry/OpenInference tracing for Hermes observer hooks.

The plugin intentionally observes Hermes' stable hook contract instead of
wrapping model providers or tool execution. Phoenix is an optional OTLP
backend; an unavailable backend must never affect Agent execution.
"""

from __future__ import annotations

import atexit
import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable


_VERSION = "0.1.0"
_LOCK = threading.RLock()
_RUNTIME: "_Runtime | None" = None
_INITIALIZED = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _profile() -> str:
    value = os.environ.get("HERMES_PROFILE") or os.environ.get("HERMES_PROFILE_NAME") or "default"
    return "orchestrator" if value == "default" else value


def _bounded_json(value: Any, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        encoded = repr(value)
    if len(encoded) <= limit:
        return encoded
    return encoded[:limit] + f"...[truncated {len(encoded) - limit} chars]"


def _text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if "." in str(value) else int(value)
    except (TypeError, ValueError):
        return None


def _usage_value(usage: Any, *names: str) -> int | None:
    if usage is None:
        return None
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        parsed = _number(value)
        if parsed is not None:
            return int(parsed)
    return None


def _duration_ms(kwargs: dict[str, Any]) -> float | None:
    for key, multiplier in (("duration_ms", 1.0), ("api_duration", 1000.0)):
        parsed = _number(kwargs.get(key))
        if parsed is not None:
            return float(parsed) * multiplier
    return None


def _identity(kwargs: dict[str, Any], *names: str) -> str:
    return ":".join(str(kwargs.get(name) or "") for name in names)


@dataclass
class _OpenSpan:
    span: Any
    context: Any


class _Runtime:
    """Correlate out-of-order observer callbacks into one trace per user goal."""

    def __init__(
        self,
        tracer: Any,
        provider: Any,
        set_span_in_context: Callable[[Any], Any],
        status_factory: Callable[[str, str | None], Any],
        *,
        profile: str,
        capture_content: bool,
        content_limit: int,
    ) -> None:
        self.tracer = tracer
        self.provider = provider
        self.set_span_in_context = set_span_in_context
        self.status_factory = status_factory
        self.profile = profile
        self.capture_content = capture_content
        self.content_limit = content_limit
        self.turns: dict[str, list[_OpenSpan]] = {}
        self.apis: dict[str, list[_OpenSpan]] = {}
        self.tools: dict[str, list[_OpenSpan]] = {}
        self.approvals: dict[str, list[_OpenSpan]] = {}
        self.delegations: dict[str, list[_OpenSpan]] = {}
        self.session_parents: dict[str, Any] = {}

    def _push(self, mapping: dict[str, list[_OpenSpan]], key: str, value: _OpenSpan) -> None:
        mapping.setdefault(key, []).append(value)

    def _pop(self, mapping: dict[str, list[_OpenSpan]], key: str) -> _OpenSpan | None:
        values = mapping.get(key)
        if not values:
            return None
        value = values.pop()
        if not values:
            mapping.pop(key, None)
        return value

    @staticmethod
    def _turn_key(kwargs: dict[str, Any]) -> str:
        return _identity(kwargs, "session_id", "turn_id")

    @staticmethod
    def _api_key(kwargs: dict[str, Any]) -> str:
        return str(kwargs.get("api_request_id") or _identity(kwargs, "session_id", "turn_id", "api_call_count"))

    @staticmethod
    def _tool_key(kwargs: dict[str, Any]) -> str:
        return str(
            kwargs.get("tool_call_id")
            or _identity(kwargs, "session_id", "turn_id", "api_request_id", "tool_name")
        )

    @staticmethod
    def _approval_key(kwargs: dict[str, Any]) -> str:
        return _identity(kwargs, "session_key", "surface", "pattern_key", "command")

    @staticmethod
    def _delegation_key(kwargs: dict[str, Any]) -> str:
        return str(
            kwargs.get("child_subagent_id")
            or kwargs.get("child_session_id")
            or _identity(kwargs, "parent_session_id", "parent_turn_id", "child_role")
        )

    def _parent_context(self, kwargs: dict[str, Any]) -> Any:
        session_id = str(kwargs.get("session_id") or kwargs.get("parent_session_id") or "")
        turn_id = str(kwargs.get("turn_id") or kwargs.get("parent_turn_id") or "")
        values = self.turns.get(f"{session_id}:{turn_id}")
        if values:
            return values[-1].context
        return self.session_parents.get(session_id)

    def _start(
        self,
        name: str,
        attributes: dict[str, Any],
        parent_context: Any = None,
    ) -> _OpenSpan:
        clean = {key: value for key, value in attributes.items() if value is not None and value != ""}
        span = self.tracer.start_span(name, context=parent_context, attributes=clean)
        return _OpenSpan(span=span, context=self.set_span_in_context(span))

    def _finish(
        self,
        opened: _OpenSpan | None,
        *,
        attributes: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if opened is None:
            return
        for key, value in (attributes or {}).items():
            if value is not None and value != "":
                opened.span.set_attribute(key, value)
        opened.span.set_status(self.status_factory("ERROR" if error else "OK", error))
        opened.span.end()

    def pre_llm_call(self, kwargs: dict[str, Any]) -> None:
        session_id = str(kwargs.get("session_id") or "unknown")
        turn_id = str(kwargs.get("turn_id") or kwargs.get("task_id") or "unknown")
        parent = self.session_parents.get(session_id)
        attributes: dict[str, Any] = {
            "openinference.span.kind": "AGENT",
            "session.id": session_id,
            "agent.name": self.profile,
            "uuma.agent.profile": self.profile,
            "uuma.turn.id": turn_id,
            "uuma.task.id": kwargs.get("task_id"),
            "uuma.platform": kwargs.get("platform"),
            "uuma.model": kwargs.get("model"),
            "uuma.is_first_turn": bool(kwargs.get("is_first_turn", False)),
            "uuma.context.message_count": len(kwargs.get("conversation_history") or []),
        }
        if self.capture_content:
            attributes.update(
                {
                    "input.value": _text(kwargs.get("user_message"), self.content_limit),
                    "input.mime_type": "text/plain",
                }
            )
        opened = self._start("hermes.turn", attributes, parent)
        self._push(self.turns, f"{session_id}:{turn_id}", opened)

    def post_llm_call(self, kwargs: dict[str, Any]) -> None:
        attributes: dict[str, Any] = {}
        if self.capture_content:
            attributes.update(
                {
                    "output.value": _text(kwargs.get("assistant_response"), self.content_limit),
                    "output.mime_type": "text/plain",
                }
            )
        self._finish(self._pop(self.turns, self._turn_key(kwargs)), attributes=attributes)

    def pre_api_request(self, kwargs: dict[str, Any]) -> None:
        attributes: dict[str, Any] = {
            "openinference.span.kind": "LLM",
            "llm.system": str(kwargs.get("provider") or kwargs.get("platform") or "unknown").lower(),
            "llm.model_name": kwargs.get("model"),
            "session.id": kwargs.get("session_id"),
            "uuma.agent.profile": self.profile,
            "uuma.turn.id": kwargs.get("turn_id"),
            "uuma.task.id": kwargs.get("task_id"),
            "uuma.api.request_id": kwargs.get("api_request_id"),
            "uuma.api.call_count": _number(kwargs.get("api_call_count")),
            "uuma.api.mode": kwargs.get("api_mode"),
            "uuma.context.message_count": _number(kwargs.get("message_count")),
            "uuma.context.approx_input_tokens": _number(kwargs.get("approx_input_tokens")),
            "uuma.context.request_chars": _number(kwargs.get("request_char_count")),
            "uuma.tools.available_count": _number(kwargs.get("tool_count")),
            "llm.invocation_parameters": _bounded_json(
                {"max_tokens": kwargs.get("max_tokens"), "api_mode": kwargs.get("api_mode")},
                self.content_limit,
            ),
        }
        if self.capture_content:
            attributes.update(
                {
                    "input.value": _bounded_json(kwargs.get("request"), self.content_limit),
                    "input.mime_type": "application/json",
                }
            )
        opened = self._start("llm.call", attributes, self._parent_context(kwargs))
        self._push(self.apis, self._api_key(kwargs), opened)

    def post_api_request(self, kwargs: dict[str, Any]) -> None:
        usage = kwargs.get("usage")
        attributes: dict[str, Any] = {
            "llm.model_name": kwargs.get("response_model") or kwargs.get("model"),
            "llm.token_count.prompt": _usage_value(usage, "prompt_tokens", "input_tokens"),
            "llm.token_count.completion": _usage_value(usage, "completion_tokens", "output_tokens"),
            "llm.token_count.total": _usage_value(usage, "total_tokens"),
            "uuma.duration_ms": _duration_ms(kwargs),
            "uuma.finish_reason": kwargs.get("finish_reason"),
            "uuma.response.content_chars": _number(kwargs.get("assistant_content_chars")),
            "uuma.response.tool_call_count": _number(kwargs.get("assistant_tool_call_count")),
        }
        if self.capture_content:
            attributes.update(
                {
                    "output.value": _bounded_json(kwargs.get("response"), self.content_limit),
                    "output.mime_type": "application/json",
                }
            )
        self._finish(self._pop(self.apis, self._api_key(kwargs)), attributes=attributes)

    def api_request_error(self, kwargs: dict[str, Any]) -> None:
        error = kwargs.get("error")
        message = error.get("message") if isinstance(error, dict) else str(error or kwargs.get("reason") or "API request failed")
        self._finish(
            self._pop(self.apis, self._api_key(kwargs)),
            attributes={
                "uuma.duration_ms": _duration_ms(kwargs),
                "uuma.retry.count": _number(kwargs.get("retry_count")),
                "uuma.retry.maximum": _number(kwargs.get("max_retries")),
                "uuma.retryable": bool(kwargs.get("retryable", False)),
                "error.type": error.get("type") if isinstance(error, dict) else None,
                "error.message": _text(message, self.content_limit),
            },
            error=_text(message, self.content_limit),
        )

    def pre_tool_call(self, kwargs: dict[str, Any]) -> None:
        attributes: dict[str, Any] = {
            "openinference.span.kind": "TOOL",
            "tool.name": kwargs.get("tool_name"),
            "session.id": kwargs.get("session_id"),
            "uuma.agent.profile": self.profile,
            "uuma.turn.id": kwargs.get("turn_id"),
            "uuma.task.id": kwargs.get("task_id"),
            "uuma.tool.call_id": kwargs.get("tool_call_id"),
            "uuma.api.request_id": kwargs.get("api_request_id"),
        }
        if self.capture_content:
            attributes.update(
                {
                    "input.value": _bounded_json(kwargs.get("args"), self.content_limit),
                    "input.mime_type": "application/json",
                }
            )
        opened = self._start(f"tool.{kwargs.get('tool_name') or 'call'}", attributes, self._parent_context(kwargs))
        self._push(self.tools, self._tool_key(kwargs), opened)

    def post_tool_call(self, kwargs: dict[str, Any]) -> None:
        status = str(kwargs.get("status") or "ok").lower()
        error = None
        if status != "ok":
            error = _text(kwargs.get("error_message") or status, self.content_limit)
        attributes: dict[str, Any] = {
            "uuma.duration_ms": _duration_ms(kwargs),
            "uuma.tool.status": status,
            "error.type": kwargs.get("error_type"),
            "error.message": error,
        }
        if self.capture_content:
            attributes.update(
                {
                    "output.value": _bounded_json(kwargs.get("result"), self.content_limit),
                    "output.mime_type": "application/json",
                }
            )
        self._finish(self._pop(self.tools, self._tool_key(kwargs)), attributes=attributes, error=error)

    def pre_approval_request(self, kwargs: dict[str, Any]) -> None:
        attributes: dict[str, Any] = {
            "openinference.span.kind": "GUARDRAIL",
            "uuma.agent.profile": self.profile,
            "uuma.approval.surface": kwargs.get("surface"),
            "uuma.approval.pattern": kwargs.get("pattern_key"),
        }
        if self.capture_content:
            attributes["input.value"] = _text(kwargs.get("description") or kwargs.get("command"), self.content_limit)
        opened = self._start("approval.request", attributes, self._parent_context(kwargs))
        self._push(self.approvals, self._approval_key(kwargs), opened)

    def post_approval_response(self, kwargs: dict[str, Any]) -> None:
        choice = str(kwargs.get("choice") or "unknown")
        error = "approval denied" if choice in {"deny", "timeout"} else None
        self._finish(
            self._pop(self.approvals, self._approval_key(kwargs)),
            attributes={"uuma.approval.choice": choice},
            error=error,
        )

    def subagent_start(self, kwargs: dict[str, Any]) -> None:
        child_session = str(kwargs.get("child_session_id") or "")
        attributes: dict[str, Any] = {
            "openinference.span.kind": "AGENT",
            "agent.name": kwargs.get("child_role") or "subagent",
            "session.id": kwargs.get("parent_session_id"),
            "uuma.agent.profile": self.profile,
            "uuma.parent.turn_id": kwargs.get("parent_turn_id"),
            "uuma.child.session_id": child_session,
            "uuma.child.subagent_id": kwargs.get("child_subagent_id"),
        }
        if self.capture_content:
            attributes["input.value"] = _text(kwargs.get("child_goal"), self.content_limit)
        opened = self._start("agent.delegate", attributes, self._parent_context(kwargs))
        self._push(self.delegations, self._delegation_key(kwargs), opened)
        if child_session:
            self.session_parents[child_session] = opened.context

    def subagent_stop(self, kwargs: dict[str, Any]) -> None:
        child_session = str(kwargs.get("child_session_id") or "")
        status = str(kwargs.get("child_status") or kwargs.get("status") or "ok").lower()
        error = None if status in {"ok", "completed", "success"} else status
        attributes: dict[str, Any] = {
            "uuma.duration_ms": _duration_ms(kwargs),
            "uuma.child.status": status,
            "uuma.child.tool_call_count": len(kwargs.get("tool_call_history") or []),
        }
        if self.capture_content:
            attributes["output.value"] = _text(kwargs.get("child_summary"), self.content_limit)
        self._finish(
            self._pop(self.delegations, self._delegation_key(kwargs)),
            attributes=attributes,
            error=error,
        )
        if child_session:
            self.session_parents.pop(child_session, None)

    def close_session(self, session_id: str, *, interrupted: bool = False, reason: str = "") -> None:
        prefix = f"{session_id}:"
        error = reason or ("interrupted" if interrupted else "turn ended without post_llm_call")
        for key in [key for key in self.turns if key.startswith(prefix)]:
            while key in self.turns:
                self._finish(self._pop(self.turns, key), error=error)
        self.session_parents.pop(session_id, None)

    def shutdown(self) -> None:
        with _LOCK:
            for mapping in (self.apis, self.tools, self.approvals, self.delegations, self.turns):
                for key in list(mapping):
                    while key in mapping:
                        self._finish(self._pop(mapping, key), error="telemetry shutdown")
            force_flush = getattr(self.provider, "force_flush", None)
            if callable(force_flush):
                try:
                    force_flush(timeout_millis=2000)
                except Exception:
                    pass


def _build_runtime() -> _Runtime | None:
    if not _env_bool("UUMA_PHOENIX_ENABLED"):
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode
        from phoenix.otel import register as register_phoenix

        endpoint = os.environ.get(
            "UUMA_PHOENIX_ENDPOINT",
            os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces"),
        ).strip()
        project = os.environ.get("UUMA_PHOENIX_PROJECT", "hermes").strip() or "hermes"
        protocol = os.environ.get("UUMA_PHOENIX_PROTOCOL", "http/protobuf").strip()
        provider = register_phoenix(
            project_name=project,
            endpoint=endpoint,
            protocol=protocol,
            batch=True,
        )
        tracer = trace.get_tracer("uuma.hermes.observability", _VERSION)

        def status_factory(code: str, description: str | None) -> Any:
            return Status(StatusCode.ERROR if code == "ERROR" else StatusCode.OK, description)

        return _Runtime(
            tracer,
            provider,
            trace.set_span_in_context,
            status_factory,
            profile=_profile(),
            capture_content=_env_bool("UUMA_OBSERVABILITY_CAPTURE_CONTENT"),
            content_limit=max(256, int(os.environ.get("UUMA_OBSERVABILITY_MAX_CONTENT_CHARS", "8000"))),
        )
    except Exception:
        return None


def _runtime() -> _Runtime | None:
    global _INITIALIZED, _RUNTIME
    if _INITIALIZED:
        return _RUNTIME
    with _LOCK:
        if not _INITIALIZED:
            _RUNTIME = _build_runtime()
            _INITIALIZED = True
    return _RUNTIME


def _dispatch(method: str, kwargs: dict[str, Any]) -> None:
    try:
        runtime = _runtime()
        if runtime is not None:
            with _LOCK:
                getattr(runtime, method)(kwargs)
    except Exception:
        # Observability must never alter Hermes behavior.
        pass


def _callback(method: str):
    def callback(**kwargs: Any) -> None:
        _dispatch(method, kwargs)

    return callback


def _on_session_end(**kwargs: Any) -> None:
    try:
        runtime = _runtime()
        if runtime is not None:
            with _LOCK:
                runtime.close_session(
                    str(kwargs.get("session_id") or ""),
                    interrupted=bool(kwargs.get("interrupted", False)),
                    reason=str(kwargs.get("reason") or ""),
                )
    except Exception:
        pass


def _on_session_reset(**kwargs: Any) -> None:
    try:
        runtime = _runtime()
        if runtime is not None:
            with _LOCK:
                runtime.close_session(str(kwargs.get("old_session_id") or ""), reason="session reset")
    except Exception:
        pass


def _shutdown() -> None:
    try:
        runtime = _RUNTIME
        if runtime is not None:
            runtime.shutdown()
    except Exception:
        pass


def register(ctx: Any) -> None:
    # Do not make Hermes construct observer payloads when export is disabled.
    if not _env_bool("UUMA_PHOENIX_ENABLED"):
        return
    for hook, method in (
        ("pre_llm_call", "pre_llm_call"),
        ("post_llm_call", "post_llm_call"),
        ("pre_api_request", "pre_api_request"),
        ("post_api_request", "post_api_request"),
        ("api_request_error", "api_request_error"),
        ("pre_tool_call", "pre_tool_call"),
        ("post_tool_call", "post_tool_call"),
        ("pre_approval_request", "pre_approval_request"),
        ("post_approval_response", "post_approval_response"),
        ("subagent_start", "subagent_start"),
        ("subagent_stop", "subagent_stop"),
    ):
        ctx.register_hook(hook, _callback(method))
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_finalize", _on_session_end)
    ctx.register_hook("on_session_reset", _on_session_reset)


atexit.register(_shutdown)
