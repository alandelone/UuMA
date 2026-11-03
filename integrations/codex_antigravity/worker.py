"""One isolated inference request over SSH; credentials stay on the Hermes host."""

from __future__ import annotations

import importlib
import json
import logging
import os
import shlex
import sys
import tempfile
import threading
import time
import types
from pathlib import Path


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=True), flush=True)


def full_prompt(messages, model=None, tools=None, tool_choice=None, **_):
    """Preserve the complete replay instead of the Hermes transcript truncation policy."""
    return (
        "You are the inference backend for Codex, running on the user's Windows computer. "
        "You have NO native tools or access to the user's workspace on this host. "
        "Never invoke Antigravity native tools. Codex executes all tools on the client. "
        "Follow the system/developer instructions in the JSON conversation. "
        "To request a provided tool, emit only <tool_call> followed by a JSON object with "
        "id, type='function', function={name, arguments}, then </tool_call>. "
        "The arguments field must be a JSON-encoded string. Stop after tool calls; "
        "never invent tool results. Use only the exact callable names in the tools array. "
        "Names mentioned within code-mode documentation are not extra top-level tools: "
        "invoke the exposed code execution tool with code to use those APIs. "
        "Otherwise answer the user normally.\n"
        "Callable names: "
        + ", ".join(t["function"]["name"] for t in tools or [])
        + "\n"
        + json.dumps(
            {"messages": messages, "tools": tools or [], "tool_choice": tool_choice},
            ensure_ascii=False,
        )
    )


def main() -> None:
    started = time.monotonic()
    logging.disable(logging.CRITICAL)
    base = Path.home() / ".local/share/uuma"
    allowed = {"ANTIGRAVITY_COMMAND", "UUMA_AGY_POOL_ROOT", "PYTHONPATH"}
    for line in (base / "pilot/gateway.env").read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            os.environ[key] = shlex.split(value)[0] if value else ""
    for path in reversed(os.environ["PYTHONPATH"].split(os.pathsep)):
        sys.path.insert(0, path)
    plugin = base / "pilot/home/plugins/antigravity-oauth"
    package = types.ModuleType("_codex_antigravity_provider")
    package.__path__ = [str(plugin)]
    sys.modules[package.__name__] = package
    module = importlib.import_module(package.__name__ + ".client")
    module._format_messages_as_prompt = full_prompt

    class InferenceClient(module.AntigravityClient):
        def _sync_workspace_rules(self, messages):
            # This request's Codex instructions are authoritative, not a Hermes SOUL file.
            return False

    request = json.loads(sys.stdin.readline())
    with (
        tempfile.TemporaryDirectory(prefix="codex-agy-") as workspace,
        InferenceClient(command=os.environ["ANTIGRAVITY_COMMAND"], cwd=workspace) as client,
    ):
        cancelled = threading.Event()

        def watch_connection():
            # Gateway keeps stdin open during a request. SSH disconnect/EOF
            # closes the provider subprocess, including before its first token.
            if not os.read(sys.stdin.fileno(), 1):
                cancelled.set()
                client.close()

        if request.get("stream_control"):
            threading.Thread(target=watch_connection, daemon=True).start()
        actual_model, _ = client._resolve_model_and_effort(
            request["model"], request.get("reasoning_effort", "medium")
        )
        emit(
            {
                "event": "ready",
                "model": actual_model,
                "startup_seconds": round(time.monotonic() - started, 3),
            }
        )
        stream = client.chat.completions.create(
            model=request["model"],
            messages=request["messages"],
            tools=request.get("tools"),
            tool_choice=request.get("tool_choice"),
            reasoning_effort=request.get("reasoning_effort", "medium"),
            timeout=300,
            stream=True,
        )
        try:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                    details = getattr(usage, "prompt_tokens_details", None)
                    emit(
                        {
                            "event": "usage",
                            "input_tokens": usage.prompt_tokens,
                            "output_tokens": usage.completion_tokens,
                            "cached_tokens": getattr(details, "cached_tokens", 0),
                        }
                    )
                for choice in chunk.choices:
                    delta = choice.delta
                    calls = []
                    for call in getattr(delta, "tool_calls", None) or []:
                        function = call.function
                        calls.append(
                            {
                                "index": call.index,
                                "id": call.id,
                                "name": function.name,
                                "arguments": function.arguments or "",
                            }
                        )
                    emit(
                        {
                            "event": "delta",
                            "text": delta.content or "",
                            "calls": calls,
                            "finish_reason": choice.finish_reason,
                        }
                    )
            if not cancelled.is_set():
                emit({"event": "done"})
        finally:
            stream.close()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
    except Exception as error:  # noqa: BLE001 - emit a sanitized worker-boundary failure
        detail = str(error).lower()
        code = "upstream_error"
        if any(word in detail for word in ("quota", "429", "exhaust", "cooldown")):
            code = "quota_exhausted"
        elif any(word in detail for word in ("auth", "token", "login")):
            code = "authentication_required"
        elif "timeout" in detail or "timed out" in detail:
            code = "upstream_timeout"
        emit({"event": "error", "code": code, "error_type": type(error).__name__})
        raise SystemExit(1) from None
