"""Hermes observer plugin that durably spools and relays audit events."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

HOOKS = (
    "on_session_start",
    "on_session_end",
    "on_session_finalize",
    "on_session_reset",
    "pre_llm_call",
    "post_llm_call",
    "pre_api_request",
    "post_api_request",
    "api_request_error",
    "pre_tool_call",
    "post_tool_call",
    "pre_approval_request",
    "post_approval_response",
    "subagent_start",
    "subagent_stop",
)

_SENSITIVE_KEYS = (
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_ASSIGNMENT_RE = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*([^\s,;]+)")
_QUEUE: queue.Queue[tuple[Path, dict[str, Any]]] = queue.Queue(maxsize=2048)
_START_LOCK = threading.Lock()
_STARTED = False


def _profile() -> str:
    value = os.environ.get("HERMES_PROFILE") or os.environ.get("HERMES_PROFILE_NAME") or "default"
    return "orchestrator" if value == "default" else value


def _spool_dir() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return Path(os.environ.get("UUMA_AUDIT_SPOOL", local / "UuMA" / "spool" / "hermes"))


def _redact_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def _safe(value: Any, seen: set[int] | None = None) -> Any:
    seen = seen or set()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}

    identity = id(value)
    if identity in seen:
        return "[CYCLE]"
    seen.add(identity)
    try:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                result[str(key)] = (
                    "[REDACTED]"
                    if any(marker in normalized for marker in _SENSITIVE_KEYS)
                    else _safe(item, seen)
                )
            return result
        if isinstance(value, (list, tuple, set)):
            return [_safe(item, seen) for item in value]
        if hasattr(value, "model_dump"):
            return _safe(value.model_dump(mode="json"), seen)
        if hasattr(value, "__dict__"):
            return _safe(vars(value), seen)
        return _redact_text(repr(value))
    finally:
        seen.discard(identity)


def _load_token() -> str:
    direct = os.environ.get("UUMA_AUDIT_TOKEN", "").strip()
    if direct:
        return direct
    token_file = os.environ.get("UUMA_TOKEN_FILE", "").strip()
    if not token_file:
        return ""
    try:
        data = json.loads(Path(token_file).read_text(encoding="utf-8"))
        return str(data.get("audit") or "")
    except (OSError, ValueError, TypeError):
        return ""


def _post(event: dict[str, Any]) -> None:
    endpoint = os.environ.get("UUMA_INGEST_URL", "").strip()
    token = _load_token()
    if not endpoint or not token:
        return
    request = Request(
        endpoint,
        data=json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-UUMA-Identity": "audit",
            "X-UUMA-Profile": str(event["profile"]),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=1.0) as response:
            response.read(1)
    except (HTTPError, URLError, TimeoutError, OSError):
        pass


def _shipper() -> None:
    while True:
        _path, event = _QUEUE.get()
        try:
            _post(event)
        finally:
            _QUEUE.task_done()


def _ensure_shipper() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        threading.Thread(target=_shipper, name="uuma-audit-relay", daemon=True).start()
        _STARTED = True


def _emit(hook: str, kwargs: dict[str, Any]) -> None:
    try:
        event_id = f"hermes_{uuid4().hex}"
        now = datetime.now(UTC)
        event = {
            "telemetry_schema_version": "1.0",
            "uuma_event_id": event_id,
            "hook": hook,
            "profile": _profile(),
            "captured_at": now.isoformat(),
            "session_id": str(kwargs.get("session_id") or "unknown"),
            "task_id": kwargs.get("task_id"),
            "data": _safe(kwargs),
        }
        spool = _spool_dir()
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}_{event_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)
        try:
            _QUEUE.put_nowait((path, event))
        except queue.Full:
            pass
    except Exception:  # noqa: BLE001,S110
        # Observer hooks must never break the Agent's work.
        pass


def _capture_research_approval(hook: str, kwargs: dict[str, Any]) -> None:
    """Forward exact user approval messages to RSTV4's trusted intake process."""
    if hook != "pre_llm_call" or _profile() not in {"orchestrator", "scholar"}:
        return
    message = str(kwargs.get("user_message") or "").strip()
    if re.fullmatch(r"APPROVE\s+[a-z0-9_]+", message, re.IGNORECASE) is None:
        return
    root = os.environ.get("RSTV4_ROOT", "").strip()
    python_exe = os.environ.get("RSTV4_PYTHON", "").strip()
    if not root or not python_exe:
        return
    session_id = str(kwargs.get("session_id") or "unknown")
    message_id = str(
        kwargs.get("message_id")
        or hashlib.sha256(f"{session_id}\0{message}".encode()).hexdigest()
    )
    subprocess.run(
        [
            python_exe,
            "-m",
            "rstv4.approval_capture",
            "--root",
            root,
            "--profile",
            _profile(),
            "--session-id",
            session_id,
            "--message-id",
            message_id,
        ],
        input=message,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def _callback(hook: str):
    def callback(**kwargs: Any) -> None:
        try:
            _capture_research_approval(hook, kwargs)
        except Exception:  # noqa: BLE001,S110
            pass
        _emit(hook, kwargs)

    return callback


def register(ctx) -> None:
    _ensure_shipper()
    for hook in HOOKS:
        ctx.register_hook(hook, _callback(hook))
