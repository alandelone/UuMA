"""Read the existing remote Wisdom owner without copying or opening a local domain store."""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import threading
import time
from pathlib import Path


def read_wisdom_snapshot(database: str) -> dict:
    """Standalone stdlib-only reader, also executed over the existing SSH connection."""
    import json
    import sqlite3
    import urllib.request
    from datetime import UTC, datetime
    from pathlib import Path

    path = Path(database)
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")

        def records(table):
            return [json.loads(row[0]) for row in connection.execute(
                f"SELECT record_json FROM {table} ORDER BY updated_sequence DESC"
            )]

        topics = records("knowledge_topics")
        orbits = records("question_orbits")
        questions = {q["question_id"]: q for q in records("questions")}
        for topic in topics:
            topic_id = topic["topic_id"]
            topic["ver_cnt"] = connection.execute(
                "SELECT COUNT(*) FROM topic_document_versions WHERE topic_id=?", (topic_id,)
            ).fetchone()[0]
            topic["links_cnt"] = connection.execute(
                "SELECT COUNT(*) FROM topic_knowledge_links WHERE topic_id=?", (topic_id,)
            ).fetchone()[0]

        for orbit in orbits:
            orbit_id = orbit["orbit_id"]
            notice = connection.execute(
                "SELECT record_json FROM orbit_notifications WHERE orbit_id=? "
                "AND json_extract(record_json,'$.event_type') IN "
                "('FAILED','BLOCKED','BUDGET_EXHAUSTED','USER_ACTION_REQUIRED') "
                "ORDER BY updated_sequence DESC LIMIT 1", (orbit_id,),
            ).fetchone()
            notice_record = json.loads(notice[0]) if notice else {}
            orbit["alert_delivery"] = {
                key: notice_record.get(key) for key in (
                    "event_type", "status", "attempts", "created_at", "updated_at", "sent_at",
                )
            }
            orbit["alert_delivery"]["receipt_scope"] = "transport_only_not_user_read"
            cycle = connection.execute(
                "SELECT status,record_json FROM orbit_cycles WHERE orbit_id=? "
                "ORDER BY updated_sequence DESC LIMIT 1", (orbit_id,)
            ).fetchone()
            orbit["last_cycle"] = json.loads(cycle["record_json"]) if cycle else {}
            # A configured/active orbit is not evidence of a currently executing worker.
            current_cycle = orbit["last_cycle"]
            try:
                lease_end = datetime.fromisoformat(
                    current_cycle.get("lease_expires_at", "")
                )
                orbit["runner_live"] = (
                    orbit["status"] == "ACTIVE" and current_cycle.get("status") == "RUNNING"
                    and bool(current_cycle.get("lease_owner")) and lease_end > datetime.now(UTC)
                )
            except (ValueError, TypeError):
                orbit["runner_live"] = False
            orbit["pipeline_items"] = []
            rows = connection.execute(
                "SELECT frontier_item_id,priority,status,record_json,updated_sequence "
                "FROM orbit_frontier WHERE orbit_id=? ORDER BY updated_sequence,frontier_item_id",
                (orbit_id,),
            ).fetchall()
            filled = [r for r in rows if r["status"] == "FILLED"]
            others = [r for r in rows if r["status"] != "FILLED"]
            attempted = set()
            if any(row["status"] == "OPEN" for row in others):
                attempted = {row[0] for row in connection.execute(
                    "SELECT DISTINCT json_extract(record_json,'$.frontier_item_id') "
                    "FROM orbit_cycles WHERE orbit_id=? AND status IN ('COMPLETED','FAILED')",
                    (orbit_id,),
                )}
            for index, row in enumerate(filled + others):
                record = json.loads(row["record_json"])
                question = questions.get(record.get("question_id"), {})
                item = {
                    "frontier_item_id": row["frontier_item_id"],
                    "orbit_id": orbit_id,
                    "priority": row["priority"],
                    "status": row["status"],
                    "updated_sequence": row["updated_sequence"],
                    "question_text": question.get("text") or record.get("rationale") or row["frontier_item_id"],
                    "rationale": record.get("rationale"),
                    "updated_at": record.get("updated_at"),
                }
                if row["status"] == "FILLED":
                    recent = index >= len(filled) - 2
                    item.update(stage="PASSED_RECENT" if recent else "PASSED_DIMMED",
                                badge="✓ 已攻关" if recent else "✓ 已归档过关", dimmed=not recent)
                elif orbit["runner_live"] and current_cycle.get("frontier_item_id") == row["frontier_item_id"]:
                    item.update(stage="RUNNING", badge="⚡ 正在攻关", dimmed=False, is_current=True)
                elif orbit["status"] in {"STOPPED", "FAILED", "BUDGET_EXHAUSTED", "PAUSED"}:
                    reason = {"STOPPED": "轨道已停止", "FAILED": "轨道失败",
                              "BUDGET_EXHAUSTED": "预算耗尽", "PAUSED": "轨道暂停"}[orbit["status"]]
                    item.update(stage="PAUSED", badge=f"⏸ 未完成 · {reason}", dimmed=False)
                elif row["status"] == "OPEN" and record.get("no_source_attempts", 0) > 0:
                    item.update(stage="ATTEMPTED", badge="已尝试 · 证据不足", dimmed=False)
                elif row["status"] == "OPEN" and row["frontier_item_id"] in attempted:
                    item.update(stage="ATTEMPTED", badge="已尝试 · 未完成", dimmed=False)
                else:
                    item.update(stage="QUEUED", badge="待执行", dimmed=False)
                orbit["pipeline_items"].append(item)
            root = questions.get(orbit.get("root_question_id"), {})
            orbit["question_text"] = root.get("text") or orbit.get("objective") or orbit_id
            run = connection.execute(
                "SELECT record_json FROM research_runs "
                "WHERE json_extract(record_json,'$.orbit_id')=? ORDER BY updated_sequence DESC LIMIT 1",
                (orbit_id,),
            ).fetchone()
            orbit["usage"] = json.loads(run[0]) if run else {}
            budget_limits_map = {
                "QUICK": {"active_seconds": 3600, "sources": 30, "model_tokens": 500000, "search_queries": 250},
                "STANDARD": {"active_seconds": 14400, "sources": 100, "model_tokens": 2000000, "search_queries": 1000},
                "DEEP": {"active_seconds": 216000, "sources": 500, "model_tokens": 10000000, "search_queries": 15000},
            }
            orbit["budget_limits"] = budget_limits_map.get(orbit.get("budget_tier"), budget_limits_map["DEEP"])
            orbit["cycle_explanation"] = orbit["last_cycle"].get("cycle_explanation")
            orbit["discovery_attempts"] = orbit["last_cycle"].get("discovery_attempts") or []
        last_event = connection.execute("SELECT MAX(occurred_at) FROM knowledge_events").fetchone()[0]
        # End the database snapshot before probing the independent runtime. A healthy
        # service does not change any historical investigation outcome.
        connection.rollback()
        runtime = {"checked_at": datetime.now(UTC).isoformat(), "kag_status": "UNKNOWN"}
        try:
            with urllib.request.urlopen("http://127.0.0.1:8891/health", timeout=2) as response:
                health = json.load(response)
            runtime["kag_status"] = "READY" if health.get("ready") is True else "UNAVAILABLE"
        except (OSError, ValueError):
            runtime["kag_status"] = "UNAVAILABLE"
        runtime["failed_alerts"] = [
            {"orbit_id": orbit["orbit_id"], **orbit["alert_delivery"]}
            for orbit in orbits
            if orbit["alert_delivery"].get("status") == "FAILED"
        ]
        return {"topics": topics, "orbits": orbits, "last_event_at": last_event,
                "runtime": runtime}
    finally:
        connection.close()


class RemoteWisdomReader:
    """Short-lived read transactions on the authoritative server; bounded shared cache."""

    def __init__(self, marker: Path):
        self.marker = marker
        self.snapshot: dict | None = None
        self.error: str | None = None
        self._checked = float("-inf")
        self._lock = threading.Lock()

    def read(self) -> dict | None:
        with self._lock:
            if time.monotonic() - self._checked < 15:
                return self.snapshot
            try:
                owner = json.loads(self.marker.read_text(encoding="utf-8"))
                if owner.get("agent") != "wisdom-oldman" or owner.get("owner_node") != "alandelone-server-001":
                    raise ValueError("Unrecognized Wisdom owner marker")
                database = owner["server_database"]
                if not isinstance(database, str) or not database.startswith("/"):
                    raise ValueError("Invalid server database location")
                # JSON is supplied over stdin, never interpolated into a shell command.
                script = "import json\n" + inspect.getsource(read_wisdom_snapshot)
                script += "\nprint(json.dumps(read_wisdom_snapshot(" + repr(database) + "),ensure_ascii=True))\n"
                result = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     os.environ.get("UUMA_OBSERVATORY_WISDOM_SSH_HOST", "ubuntu-server"),
                     "python3", "-B", "-"],
                    input=script, capture_output=True, text=True, encoding="utf-8", timeout=10,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode:
                    raise OSError("Remote Wisdom read failed; verify its owner and SSH connection")
                snapshot = json.loads(result.stdout)
                if (not isinstance(snapshot, dict)
                        or not isinstance(snapshot.get("topics"), list)
                        or not isinstance(snapshot.get("orbits"), list)):
                    raise TypeError("Invalid remote Wisdom snapshot")
                self.snapshot = snapshot
                self.error = None
            except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
                self.error = f"Remote Wisdom source unavailable ({type(exc).__name__})"
            self._checked = time.monotonic()
            return self.snapshot


def snapshot_items(snapshot: dict, view_base_url: str, view_token: str) -> list[dict]:
    """Keep all topic and orphan-orbit history, including terminal investigation records."""
    items = []
    runtime = snapshot.get("runtime") or {}
    if runtime:
        failed = len(runtime.get("failed_alerts") or [])
        ready = runtime.get("kag_status") == "READY"
        items.append({
            "agent_id": "wisdom-oldman", "item_id": "wisdom_runtime_health",
            "title": "当前服务与告警投递", "kind": "wisdom_runtime",
            "status": "READY" if ready and not failed else "WARNING",
            "updated_at": runtime.get("checked_at"),
            "summary": ("KAG 当前可用" if ready else "KAG 当前不可用或尚未确认")
                       + f"；{failed} 条关键告警投递失败。历史研究状态单独保留。",
            "source_ref": "alandelone-server-001:KAG health & wisdom.db",
            "payload": {"runtime": runtime},
        })
    topics = snapshot["topics"]
    topic_ids = {topic["topic_id"] for topic in topics}
    for topic in topics:
        topic_id = topic["topic_id"]
        investigations = [orbit for orbit in snapshot["orbits"] if orbit.get("topic_id") == topic_id]
        latest = investigations[0] if investigations else None
        payload = dict(topic, investigations=investigations, orbit_info=latest, runtime=runtime,
                       under_tasks=[], claims=[], gaps=[], claim_count=topic.get("claim_count"),
                       standalone_url=f"{view_base_url}/wisdom/topics/{topic_id}?token={view_token}")
        items.append({
            "agent_id": "wisdom-oldman", "item_id": f"wisdom_topic_{topic_id}",
            "title": "知识主题: " + topic.get("title", topic_id), "kind": "knowledge_topic",
            "status": topic["status"], "updated_at": topic.get("updated_at"),
            "summary": topic.get("summary") or "持久知识主题与调查历史",
            "source_ref": "alandelone-server-001:wisdom.db", "payload": payload,
        })
    for orbit in snapshot["orbits"]:
        if orbit.get("topic_id") in topic_ids:
            continue
        items.append({
            "agent_id": "wisdom-oldman", "item_id": "wisdom_orbit_" + orbit["orbit_id"],
            "title": "调查轨道: " + orbit["question_text"], "kind": "knowledge_orbit",
            "status": orbit["status"], "updated_at": orbit.get("updated_at"),
            "summary": orbit.get("stop_reason") or "保留原始调查轨道与缺口记录",
            "source_ref": "alandelone-server-001:wisdom.db",
            "payload": {"orbit_info": orbit, "title": orbit["question_text"],
                        "runtime": runtime},
        })
    return items
