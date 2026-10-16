"""Harvester engine for background ingestion and two-phase audit backfill."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import ActivityEvent, BackfillProgress, SourceFreshness
from .storage import ObservatoryStorage

logger = logging.getLogger("uuma.observatory.harvester")


def _normalize_agent_id(profile: str) -> str:
    raw = (profile or "").strip().lower()
    if raw in {"default", "orchestrator"}:
        return "orchestrator"
    if raw in {"forge", "forge-lab-bot", "labbot", "lab_bot", "锻造lab_bot"}:
        return "forge-lab-bot"
    if raw in {"wisdom", "wisdom-oldman", "oldman"}:
        return "wisdom-oldman"
    if raw in {"scholar"}:
        return "scholar"
    if raw in {"brainstormer"}:
        return "brainstormer"
    if raw in {"yonc"}:
        return "yonc"
    if raw in {"honc"}:
        return "honc"
    return raw or "unknown"


def _format_event_summary(hook: str, tool_name: str | None, data: dict[str, Any]) -> str:
    args = data.get("args") or {}
    if tool_name:
        if tool_name == "terminal":
            cmd = args.get("command") or ""
            return f"Terminal: {cmd[:120]}" if cmd else "Terminal command executed"
        if tool_name == "web_search":
            q = args.get("query") or ""
            return f"Web Search: {q[:120]}" if q else "Web search executed"
        if tool_name in {"file_write", "write_to_file", "patch_file"}:
            path = args.get("path") or args.get("TargetFile") or ""
            return f"File Write: {path}"
        if tool_name in {"file_read", "view_file"}:
            path = args.get("path") or args.get("AbsolutePath") or ""
            return f"File Read: {path}"
        if tool_name.startswith("kanban_"):
            action = tool_name[7:]
            if action == "show":
                return f"Kanban Show: {args.get('task_id', '')}"
            if action == "heartbeat":
                note = args.get("note") or ""
                return f"Kanban Heartbeat: {note[:60]}" if note else "Kanban Heartbeat"
            if action == "complete":
                summ = args.get("summary") or args.get("result") or ""
                return f"Kanban Complete: {summ[:80]}" if summ else "Kanban Complete"
            if action == "block":
                reason = args.get("reason") or ""
                return f"Kanban Block: {reason[:80]}" if reason else "Kanban Block"
            if action == "create":
                title = args.get("title") or ""
                return f"Kanban Create: {title[:80]}" if title else "Kanban Create"
            if action == "comment":
                return f"Kanban Comment: {args.get('task_id', '')}"
            return f"Kanban [{action}]"
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__")
            server = parts[1] if len(parts) > 1 else ""
            fn = parts[2] if len(parts) > 2 else parts[-1]
            return f"MCP [{server}:{fn}]"
        return f"Tool [{tool_name}] called"

    if hook in {"session_start", "on_session_start"}:
        model = data.get("model") or ""
        platform = data.get("platform") or ""
        extra = f" ({model})" if model else (f" [{platform}]" if platform else "")
        return f"Session started{extra}"
    if hook in {"session_end", "on_session_end"}:
        return "Session completed"
    if hook == "on_session_finalize":
        reason = data.get("reason") or "completed"
        return f"Session finalized ({reason})"
    if hook == "api_request_error":
        err = data.get("error") or {}
        err_msg = ""
        if isinstance(err, dict):
            err_msg = err.get("message") or err.get("error", {}).get("message") or str(err)
        elif isinstance(err, str):
            err_msg = err
        status = data.get("status_code") or data.get("reason") or ""
        model = data.get("model") or ""
        prefix = f"API Error [{status}]" if status else "API Error"
        if model:
            prefix += f" ({model})"
        return f"{prefix}: {err_msg[:90]}" if err_msg else prefix
    if hook == "pre_llm_call":
        user_msg = data.get("user_message") or ""
        model = data.get("model") or ""
        if user_msg:
            lines = [l.strip() for l in user_msg.splitlines() if l.strip()]
            display_line = ""
            for l in lines:
                if not l.startswith("[") and not l.startswith("<!--") and not l.startswith("#"):
                    display_line = l
                    break
            if not display_line and lines:
                display_line = lines[0]
            prefix = f"Thinking ({model})" if model else "Thinking"
            return f"{prefix}: {display_line[:80]}"
        return f"Thinking ({model})" if model else "Thinking..."
    if hook == "pre_api_request":
        model = data.get("model") or ""
        call_count = data.get("api_call_count")
        count_str = f" #{call_count}" if call_count else ""
        return f"Requesting LLM{count_str} ({model})" if model else f"Requesting LLM{count_str}"
    if hook == "post_api_request":
        finish_reason = data.get("finish_reason") or "ok"
        duration = data.get("api_duration")
        dur_str = f" in {duration:.1f}s" if isinstance(duration, (int, float)) else ""
        return f"LLM Response ({finish_reason}{dur_str})"
    if hook == "pre_tool_call":
        t = data.get("tool_name") or "tool"
        return f"Invoking {t}"
    if hook == "post_tool_call":
        t = data.get("tool_name") or "tool"
        return f"Finished {t}"
    if hook == "user_prompt":
        msg = data.get("prompt") or data.get("message") or ""
        return f"User Prompt: {msg[:100]}"
    return f"Activity ({hook})"


def parse_spool_file(file_path: Path) -> ActivityEvent | None:
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        payload = json.loads(content)
        data = payload.get("data") or {}
        captured_at = payload.get("captured_at") or datetime.now(UTC).isoformat()
        profile = payload.get("profile") or data.get("profile") or "orchestrator"
        agent_id = _normalize_agent_id(profile)
        hook = payload.get("hook") or "activity"
        tool_name = data.get("tool_name")
        event_id = payload.get("uuma_event_id") or f"spool_{file_path.stem}"
        summary = _format_event_summary(hook, tool_name, data)

        raw_snippet = json.dumps(
            {"args": data.get("args"), "task_id": payload.get("task_id")},
            ensure_ascii=False,
        )[:500]

        return ActivityEvent(
            event_id=event_id,
            agent_id=agent_id,
            hook=hook,
            captured_at=captured_at,
            tool_name=tool_name,
            summary=summary,
            source_path=str(file_path),
            raw_snippet=raw_snippet,
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.debug("Failed to parse spool file %s: %s", file_path, exc)
        return None


class Harvester:
    """Manages two-phase indexing of audit spools and periodic source probes."""

    def __init__(
        self,
        storage: ObservatoryStorage,
        spool_dir: Path | str,
        uuma_db_path: Path | str | None = None,
        on_new_event: Callable[[ActivityEvent], None] | None = None,
        on_progress: Callable[[BackfillProgress], None] | None = None,
    ) -> None:
        self.storage = storage
        self.spool_dir = Path(spool_dir)
        self.uuma_db_path = Path(uuma_db_path) if uuma_db_path else None
        self.on_new_event = on_new_event
        self.on_progress = on_progress

        self.progress = BackfillProgress()
        self._running = False
        self._thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._known_event_ids: set[str] = set()

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        self._fast_initial_harvest()

        self._thread = threading.Thread(target=self._run_backfill, daemon=True, name="ObsHarvesterBackfill")
        self._thread.start()

        self._poll_thread = threading.Thread(target=self._run_periodic_poll, daemon=True, name="ObsHarvesterPoll")
        self._poll_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

    def _fast_initial_harvest(self) -> None:
        """Scan most recent files (last 24 hours or up to 500) for instant startup."""
        if not self.spool_dir.exists():
            return

        try:
            cutoff = (datetime.now(UTC) - timedelta(hours=24)).timestamp()
            entries = []
            for entry in os.scandir(self.spool_dir):
                if entry.name.endswith(".json") and entry.is_file():
                    stat = entry.stat()
                    if stat.st_mtime >= cutoff:
                        entries.append((stat.st_mtime, Path(entry.path)))

            entries.sort(key=lambda x: x[0], reverse=True)
            recent_files = [p for _, p in entries[:500]]

            events = []
            for p in recent_files:
                ev = parse_spool_file(p)
                if ev:
                    events.append(ev)
                    self._known_event_ids.add(ev.event_id)

            if events:
                self.storage.insert_events(events)

            self.storage.update_source_health(
                SourceFreshness(
                    source_name="hermes_spool",
                    is_available=True,
                    last_event_at=events[0].captured_at if events else None,
                )
            )
        except (OSError, ValueError) as exc:
            logger.error("Fast initial harvest error: %s", exc)

    def _run_backfill(self) -> None:
        """Background thread crawling all remaining files to complete history index."""
        if not self.spool_dir.exists():
            self.progress.is_complete = True
            return

        try:
            all_files: list[Path] = []
            for entry in os.scandir(self.spool_dir):
                if entry.name.endswith(".json") and entry.is_file():
                    all_files.append(Path(entry.path))

            total = len(all_files)
            self.progress.total_files = total

            all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            batch: list[ActivityEvent] = []
            for indexed, p in enumerate(all_files, start=1):
                if not self._running:
                    break

                ev = parse_spool_file(p)
                if ev:
                    batch.append(ev)
                    self._known_event_ids.add(ev.event_id)

                if len(batch) >= 200:
                    self.storage.insert_events(batch)
                    batch.clear()

                    self.progress.indexed_files = indexed
                    self.progress.percent = round((indexed / total) * 100, 1) if total > 0 else 100.0
                    self.progress.current_file = p.name

                    if self.on_progress:
                        self.on_progress(self.progress)

                    time.sleep(0.02)

            if batch:
                self.storage.insert_events(batch)

            self.progress.indexed_files = total
            self.progress.percent = 100.0
            self.progress.is_complete = True
            if self.on_progress:
                self.on_progress(self.progress)

        except (OSError, ValueError) as exc:
            logger.error("Backfill error: %s", exc)

    def _run_periodic_poll(self) -> None:
        """Polls every 2s for newly arrived spool files and uuma.db events."""
        last_check_mtime = time.time() - 30.0

        while self._running:
            time.sleep(2.0)
            try:
                new_events: list[ActivityEvent] = []

                if self.spool_dir.exists():
                    now = time.time()
                    for entry in os.scandir(self.spool_dir):
                        if entry.name.endswith(".json") and entry.is_file():
                            stat = entry.stat()
                            if stat.st_mtime >= last_check_mtime:
                                ev = parse_spool_file(Path(entry.path))
                                if ev and ev.event_id not in self._known_event_ids:
                                    new_events.append(ev)
                                    self._known_event_ids.add(ev.event_id)
                    last_check_mtime = now

                if self.uuma_db_path and self.uuma_db_path.exists():
                    uuma_events = self._read_recent_uuma_events()
                    for ev in uuma_events:
                        if ev.event_id not in self._known_event_ids:
                            new_events.append(ev)
                            self._known_event_ids.add(ev.event_id)

                if new_events:
                    self.storage.insert_events(new_events)
                    for ev in new_events:
                        if self.on_new_event:
                            self.on_new_event(ev)

                if len(self._known_event_ids) > 10000:
                    self._known_event_ids.clear()

            except (OSError, ValueError) as exc:
                logger.debug("Periodic poll exception: %s", exc)

    def _read_recent_uuma_events(self) -> list[ActivityEvent]:
        """Read recent events from uuma.db using strict read-only connection."""
        if not self.uuma_db_path or not self.uuma_db_path.exists():
            return []
        events: list[ActivityEvent] = []
        try:
            uri = f"{self.uuma_db_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT event_id, event_type, occurred_at, aggregate_type, aggregate_id, payload_json
                    FROM events
                    ORDER BY sequence DESC LIMIT 30
                    """
                )
                for row in cursor.fetchall():
                    payload_raw = row["payload_json"] or "{}"
                    try:
                        p_dict = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                    except (json.JSONDecodeError, ValueError):
                        p_dict = {}

                    contract_dict = p_dict.get("contract", {}) if isinstance(p_dict.get("contract"), dict) else {}
                    res_dict = p_dict.get("result", {}) if isinstance(p_dict.get("result"), dict) else {}
                    reg_dict = p_dict.get("registration", {}) if isinstance(p_dict.get("registration"), dict) else {}
                    agent_id = _normalize_agent_id(p_dict.get("agent_id") or res_dict.get("agent_id") or reg_dict.get("agent_id") or "orchestrator")
                    task_id = row["aggregate_id"] if row["aggregate_type"] == "task" else p_dict.get("task_id") or res_dict.get("task_id") or reg_dict.get("task_id") or ""

                    ev_type = row["event_type"]
                    summary = f"UuMA Event [{ev_type}] {task_id}".strip()
                    if ev_type == "TASK_CREATED":
                        obj = contract_dict.get("objective") or ""
                        summary = f"Task Created: {obj[:80]}" if obj else f"Task Created {task_id}"
                    elif ev_type == "TASK_ASSIGNED":
                        summary = f"Task Assigned to {agent_id}"
                    elif ev_type == "RUN_REGISTERED":
                        run_id = reg_dict.get("run_id") or row["aggregate_id"]
                        summary = f"Run Started: {run_id}"
                    elif ev_type == "RUN_RESULT_SUBMITTED":
                        summ = res_dict.get("summary") or res_dict.get("outcome") or ""
                        outcome = res_dict.get("outcome") or "DONE"
                        summary = f"Result ({outcome}): {summ[:80]}" if summ else f"Result ({outcome})"
                    elif ev_type == "RUN_FAILED":
                        reason = p_dict.get("reason") or p_dict.get("error") or ""
                        summary = f"Run Failed: {reason[:80]}" if reason else "Run Failed"
                    elif ev_type == "RUN_HEARTBEAT":
                        summary = f"Run Heartbeat: {row['aggregate_id']}"
                    elif ev_type == "RUN_VERIFIED_COMPLETED":
                        summary = f"Run Verified: {row['aggregate_id']}"

                    events.append(
                        ActivityEvent(
                            event_id=row["event_id"],
                            agent_id=agent_id,
                            hook=row["event_type"],
                            captured_at=row["occurred_at"],
                            tool_name=None,
                            summary=summary,
                            source_path=str(self.uuma_db_path),
                            raw_snippet=payload_raw[:500],
                        )
                    )
        except sqlite3.Error:
            pass
        return events
