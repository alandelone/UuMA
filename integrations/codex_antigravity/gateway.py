"""Loopback Responses gateway: official OpenAI passthrough plus Antigravity via SSH."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

STATE = Path(os.environ["CODEX_AGY_STATE"])
SETTINGS = json.loads((STATE / "settings.json").read_text(encoding="utf-8"))
AUTH = Path.home() / ".codex/auth.json"
OFFICIAL = "https://chatgpt.com/backend-api/codex"
PREFIX = "antigravity/"
STATS = {"requests": 0, "antigravity_requests": 0, "active": 0, "last_route": None, "last": None}
HOP_HEADERS = {
    "host",
    "connection",
    "content-length",
    "transfer-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "upgrade",
}
INSTRUCTIONS = (
    "You are a coding assistant running in Codex on Windows. Work with the user's local "
    "workspace using only the tools provided by Codex. Follow AGENTS.md and user instructions. "
    "Do not claim to have executed anything without tool results."
)


def custom_models() -> list[dict]:
    cache = json.loads((STATE / "official-models.json").read_text(encoding="utf-8"))
    template = cache["models"][0]
    result = []
    for priority, (model, label) in enumerate(SETTINGS["models"].items()):
        entry = {
            k: template[k]
            for k in ("shell_type", "truncation_policy", "effective_context_window_percent")
            if k in template
        }
        entry.update(
            {
                "slug": PREFIX + model,
                "display_name": "Antigravity · " + label,
                "description": "Hermes antigravity-oauth via SSH; text and client-side tools.",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 100 + priority,
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [
                    {"effort": effort, "description": description}
                    for effort, description in (
                        [
                            ("low", "Faster responses"),
                            ("medium", "Balanced reasoning"),
                            ("high", "More reasoning"),
                        ]
                        if model.startswith("gemini-")
                        else [("medium", "Model default")]
                    )
                ],
                "upgrade": None,
                "service_tiers": [],
                "additional_speed_tiers": [],
                "input_modalities": ["text"],
                "context_window": 128000,
                "max_context_window": 128000,
                "support_verbosity": False,
                "default_reasoning_summary": "none",
                "supports_image_detail_original": False,
                "supports_search_tool": False,
                "supports_experimental_context": False,
                "supports_reasoning_effort_updates": False,
                "multi_agent_version": "disabled",
                "experimental_supported_tools": [],
                "apply_patch_tool_type": "freeform",
                "include_skills_usage_instructions": True,
                "include_plugin_usage_instructions": True,
                "include_apps_usage_instructions": True,
                "base_instructions": INSTRUCTIONS,
            }
        )
        result.append(entry)
    return result


def catalog() -> dict:
    official = json.loads((STATE / "official-models.json").read_text(encoding="utf-8"))
    return {"models": official["models"] + custom_models()}


def authenticate(request: Request) -> None:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Loopback access required")
    try:
        credentials = json.loads(AUTH.read_text(encoding="utf-8"))
        expected = credentials["tokens"]["access_token"]
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Sign in to Codex with ChatGPT") from None
    supplied = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(supplied, "Bearer " + expected):
        raise HTTPException(401, "Codex authentication required")


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(360, connect=20), follow_redirects=False
    ) as client:
        app.state.http = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {
        "status": "ready",
        "service": "codex-antigravity",
        "port": SETTINGS["port"],
        "pid": os.getpid(),
        "models": list(SETTINGS["models"]),
        **STATS,
    }


@app.get("/v1/models")
async def models(request: Request):
    authenticate(request)
    return catalog()


def text_content(content) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, dict):
        content = [content]
    result = []
    for item in content:
        if item.get("type") not in {"input_text", "output_text", "text"}:
            raise ValueError("Antigravity currently accepts text input only")
        result.append(item.get("text", ""))
    return "\n".join(result)


def tool_map(tools) -> tuple[list, dict]:
    flattened, mapping = [], {}

    def add(tool, namespace=None):
        kind = tool.get("type", "function")
        if kind == "namespace":
            for child in tool["tools"]:
                add(child, tool["name"])
            return
        if kind not in {"function", "custom"}:
            raise ValueError("Unsupported Antigravity tool type: " + kind)
        original = tool["name"]
        identity = (namespace + "__" if namespace else "") + original
        alias = re.sub(r"[^A-Za-z0-9_-]", "_", identity)
        if alias in mapping:
            raise ValueError("Ambiguous tool alias")
        mapping[alias] = {"name": original, "namespace": namespace, "type": kind}
        parameters = tool.get("parameters", {"type": "object", "properties": {}})
        description = tool.get("description", "")
        if kind == "custom":
            parameters = {
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"],
                "additionalProperties": False,
            }
            description += " Pass the complete tool input as the input string."
            if tool.get("format"):
                description += " Required input format: " + json.dumps(tool["format"])
        flattened.append(
            {
                "type": "function",
                "function": {"name": alias, "description": description, "parameters": parameters},
            }
        )

    for tool in tools:
        add(tool)
    return flattened, mapping


def resolve_call(name: str, mapping: dict) -> dict | None:
    """Accept an advertised alias or its exact, unambiguous namespace spelling."""
    if name in mapping:
        return mapping[name]
    matches = [
        meta
        for meta in mapping.values()
        if name == (meta["namespace"] + "." + meta["name"] if meta["namespace"] else meta["name"])
    ]
    return matches[0] if len(matches) == 1 else None


def custom_input(arguments: str) -> str:
    """Unwrap the bridge envelope or preserve a native freeform tool input.

    Codex owns grammar validation and tool permissions. The model may produce
    the original freeform input rather than the advertised JSON envelope.
    """
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if isinstance(value, dict) and "input" in value:
        if not isinstance(value["input"], str):
            raise ValueError("Custom tool input must be a string")
        return value["input"]
    return arguments


def translate(body: dict) -> tuple[dict, dict]:
    if body.get("previous_response_id"):
        raise ValueError("Replay conversation input; previous_response_id is not enabled")
    # Codex includes its optional hosted search definition even for models whose
    # catalog does not advertise it. This provider has no hosted search backend.
    # Exclude that optional offer, explicitly tell the model it is unavailable,
    # and continue to reject forced search and every other unknown tool type.
    hosted_search = {"web_search", "web_search_preview"}
    offered = body.get("tools", [])
    search_unavailable = any(tool.get("type") in hosted_search for tool in offered)
    tools, mapping = tool_map([tool for tool in offered if tool.get("type") not in hosted_search])
    reverse = {(v["namespace"], v["name"]): k for k, v in mapping.items()}
    messages = []
    if body.get("instructions"):
        messages.append({"role": "system", "content": body["instructions"]})
    if search_unavailable:
        messages.append(
            {
                "role": "system",
                "content": (
                    "This provider does not supply Codex hosted web search. Do not call or claim "
                    "to have used hosted web search. Use an explicitly provided client tool if "
                    "one can retrieve sources, or explain that live web retrieval is unavailable."
                ),
            }
        )
    items = body.get("input", [])
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    for item in items:
        kind = item.get("type", "message")
        if kind == "message":
            role = item["role"]
            if role == "developer":
                role = "system"
            messages.append({"role": role, "content": text_content(item.get("content"))})
        elif kind in {"function_call", "custom_tool_call"}:
            name = reverse.get((item.get("namespace"), item["name"]), item["name"])
            arguments = item.get("arguments", "{}")
            if kind == "custom_tool_call":
                arguments = json.dumps({"input": item["input"]})
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": item["call_id"],
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            )
        elif kind in {"function_call_output", "custom_tool_call_output"}:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": text_content(item.get("output")),
                }
            )
        elif kind == "reasoning":
            for part in item.get("summary", []):
                if part.get("text"):
                    messages.append({"role": "assistant", "content": part["text"]})
        else:
            raise ValueError("Unsupported Antigravity input item: " + kind)
    choice = body.get("tool_choice", "auto")
    if choice == "required" and not tools:
        raise ValueError("No supported client tool is available; hosted search is unavailable")
    if isinstance(choice, dict):
        if choice.get("type") not in {"function", "custom"}:
            raise ValueError("Unsupported tool choice")
        name = reverse.get((choice.get("namespace"), choice["name"]), choice["name"])
        if name not in mapping or mapping[name]["type"] != choice["type"]:
            raise ValueError("Forced tool is not available with the requested type")
        choice = {"type": "function", "function": {"name": name}}
    return {
        "model": body["model"].removeprefix(PREFIX),
        "messages": messages,
        "tools": tools,
        "tool_choice": choice,
        "reasoning_effort": (body.get("reasoning") or {}).get("effort", "medium"),
    }, mapping


def event_bytes(kind: str, sequence: int, **fields) -> bytes:
    value = {"type": kind, "sequence_number": sequence, **fields}
    return ("event: " + kind + "\ndata: " + json.dumps(value, ensure_ascii=True) + "\n\n").encode()


async def antigravity_stream(request: Request, body: dict, payload: dict, mapping: dict):
    started = time.monotonic()
    first_token = None
    response = {
        "id": "resp_agy_" + uuid.uuid4().hex,
        "object": "response",
        "created_at": int(time.time()),
        "model": body["model"],
        "status": "in_progress",
        "output": [],
        "error": None,
        "incomplete_details": None,
        "usage": None,
    }
    sequence = 0

    def emit(kind, **fields):
        nonlocal sequence
        result = event_bytes(kind, sequence, **fields)
        sequence += 1
        return result

    yield emit("response.created", response=response.copy())
    yield emit("response.in_progress", response=response.copy())
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = None
    message = None
    calls = {}
    usage = None
    completed = False
    provider_ready_seconds = None
    worker_startup_seconds = None
    actual_model = None
    record = {"model": body["model"], "status": "started"}
    failure_details = {}
    STATS["active"] += 1
    try:
        process = await asyncio.create_subprocess_exec(
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=2",
            SETTINGS["ssh_host"],
            SETTINGS["remote_python"],
            SETTINGS["remote_worker"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=flags,
            limit=4 * 1024 * 1024,
        )
        controlled = SETTINGS.get("worker_protocol") == "jsonline-v2"
        wire_payload = {**payload, "stream_control": controlled}
        process.stdin.write((json.dumps(wire_payload, ensure_ascii=True) + "\n").encode())
        await process.stdin.drain()
        if not controlled:
            process.stdin.close()
        while True:
            if await request.is_disconnected():
                raise asyncio.CancelledError()
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=15)
            except TimeoutError:
                if time.monotonic() - started > 330:
                    raise RuntimeError("upstream_timeout") from None
                yield b": keepalive\n\n"
                continue
            if not line:
                break
            data = json.loads(line)
            if data["event"] == "ready":
                provider_ready_seconds = time.monotonic() - started
                worker_startup_seconds = data.get("startup_seconds")
                actual_model = data.get("model")
                continue
            if data["event"] == "error":
                raise RuntimeError(data.get("code", "upstream_error"))
            if data["event"] == "done":
                completed = True
                break
            if data["event"] == "usage":
                usage = {
                    "input_tokens": data["input_tokens"],
                    "output_tokens": data["output_tokens"],
                    "total_tokens": data["input_tokens"] + data["output_tokens"],
                    "input_tokens_details": {"cached_tokens": data["cached_tokens"]},
                }
                continue
            text = data.get("text") or ""
            if text:
                if first_token is None:
                    first_token = time.monotonic() - started
                if message is None:
                    message = {
                        "id": "msg_agy_" + uuid.uuid4().hex,
                        "type": "message",
                        "role": "assistant",
                        "status": "in_progress",
                        "content": [],
                    }
                    yield emit("response.output_item.added", output_index=0, item=message.copy())
                    part = {"type": "output_text", "text": "", "annotations": [], "logprobs": []}
                    message["content"] = [part]
                    yield emit(
                        "response.content_part.added",
                        item_id=message["id"],
                        output_index=0,
                        content_index=0,
                        part=part.copy(),
                    )
                message["content"][0]["text"] += text
                yield emit(
                    "response.output_text.delta",
                    item_id=message["id"],
                    output_index=0,
                    content_index=0,
                    delta=text,
                    logprobs=[],
                )
            for call in data.get("calls", []):
                target = calls.setdefault(call["index"], {"name": "", "arguments": "", "id": ""})
                for key in ("id", "name"):
                    if call.get(key):
                        target[key] = call[key]
                target["arguments"] += call.get("arguments") or ""
        returncode = await asyncio.wait_for(process.wait(), 10)
        if not completed or returncode:
            raise RuntimeError("transport_incomplete")
        if message is None and not calls:
            raise RuntimeError("empty_model_reply")
        output = []
        if message:
            part = message["content"][0]
            message["status"] = "completed"
            yield emit(
                "response.output_text.done",
                item_id=message["id"],
                output_index=0,
                content_index=0,
                text=part["text"],
                logprobs=[],
            )
            yield emit(
                "response.content_part.done",
                item_id=message["id"],
                output_index=0,
                content_index=0,
                part=part,
            )
            yield emit("response.output_item.done", output_index=0, item=message)
            output.append(message)
        for call in calls.values():
            meta = resolve_call(call["name"], mapping)
            if meta is None:
                failure_details = {
                    "unknown_tool_name": call["name"][:160],
                    "offered_tool_aliases": sorted(mapping),
                }
                raise RuntimeError("unknown_tool_call")
            item = {
                "id": "fc_agy_" + uuid.uuid4().hex,
                "call_id": call["id"] or uuid.uuid4().hex,
                "type": "function_call",
                "name": meta["name"],
                "status": "in_progress",
                "arguments": "",
            }
            if meta["namespace"]:
                item["namespace"] = meta["namespace"]
            argument_key, event_name = "arguments", "function_call_arguments"
            arguments = call["arguments"]
            if meta["type"] == "custom":
                arguments = custom_input(arguments)
                item.pop("arguments")
                item.update(type="custom_tool_call", input="")
                argument_key, event_name = "input", "custom_tool_call_input"
            # Forward function arguments verbatim. Native Codex validates them
            # and can return a tool error for the model to correct, rather than
            # aborting the whole conversation at the transport boundary.
            index = len(output)
            yield emit("response.output_item.added", output_index=index, item=item.copy())
            yield emit(
                "response." + event_name + ".delta",
                item_id=item["id"],
                output_index=index,
                delta=arguments,
            )
            item[argument_key] = arguments
            item["status"] = "completed"
            yield emit(
                "response." + event_name + ".done",
                item_id=item["id"],
                output_index=index,
                **{argument_key: arguments},
            )
            yield emit("response.output_item.done", output_index=index, item=item)
            output.append(item)
        response.update(status="completed", output=output, usage=usage)
        yield emit("response.completed", response=response)
        record = {
            "model": body["model"],
            "actual_model": actual_model,
            "status": "completed",
            "seconds": round(time.monotonic() - started, 2),
            "first_token_seconds": round(first_token, 2) if first_token else None,
            "provider_ready_seconds": (
                round(provider_ready_seconds, 2) if provider_ready_seconds is not None else None
            ),
            "worker_startup_seconds": worker_startup_seconds,
            "client_payload_chars": len(json.dumps(payload, ensure_ascii=False)),
            "client_tool_count": len(payload.get("tools", [])),
            "usage": usage,
        }
    except asyncio.CancelledError:
        record = {"model": body["model"], "status": "cancelled"}
        raise
    except Exception as error:  # noqa: BLE001 - isolate errors at the SSE transport boundary
        code = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        response.update(
            status="failed", error={"code": "antigravity_error", "message": "Antigravity: " + code}
        )
        yield emit("response.failed", response=response)
        record = {
            "model": body["model"],
            "status": "failed",
            "code": code,
            "seconds": round(time.monotonic() - started, 2),
            **failure_details,
        }
    finally:
        if process and process.stdin and not process.stdin.is_closing():
            process.stdin.close()
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        STATS["active"] -= 1
        STATS["last"] = record
        with (STATE / "events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"time": int(time.time()), **record}) + "\n")


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "DELETE"])
async def route(path: str, request: Request):
    authenticate(request)
    raw = await request.body()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Request exceeds bridge limit")
    STATS["requests"] += 1
    request_model = None
    if raw:
        try:
            request_model = json.loads(raw).get("model")
        except (ValueError, AttributeError):
            pass
    route_record = {
        "time": int(time.time()),
        "path": path,
        "method": request.method,
        "model": request_model,
    }
    STATS["last_route"] = route_record
    with (STATE / "routing.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(route_record) + "\n")
    if path == "responses" and request.method == "POST":
        body = json.loads(raw)
        if str(body.get("model", "")).startswith(PREFIX):
            if body["model"].removeprefix(PREFIX) not in SETTINGS["models"]:
                raise HTTPException(404, "Unknown Antigravity model")
            if not body.get("stream", False):
                raise HTTPException(400, "Enable stream for the Antigravity Codex bridge")
            try:
                payload, mapping = translate(body)
            except (ValueError, KeyError, TypeError) as error:
                raise HTTPException(400, str(error)) from None
            STATS["antigravity_requests"] += 1
            return StreamingResponse(
                antigravity_stream(request, body, payload, mapping),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
    if request.method == "POST" and raw:
        try:
            model = json.loads(raw).get("model", "")
        except (ValueError, AttributeError):
            model = ""
        if str(model).startswith(PREFIX):
            raise HTTPException(
                400, "Antigravity supports streamed Responses only; use local compaction"
            )
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
    headers["accept-encoding"] = "identity"
    url = OFFICIAL + "/" + path
    if request.url.query:
        url += "?" + request.url.query
    try:
        upstream = await app.state.http.send(
            app.state.http.build_request(request.method, url, headers=headers, content=raw),
            stream=True,
        )
    except httpx.HTTPError:
        return JSONResponse({"error": {"message": "Official OpenAI connection failed"}}, 502)

    async def forward():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        forward(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in HOP_HEADERS},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=SETTINGS["port"], access_log=False)
