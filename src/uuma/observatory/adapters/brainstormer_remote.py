"""Read Brainstormer through its server-owned navigation API without local state replicas."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import threading
import time
from pathlib import Path


def read_brainstormer_snapshot(user_id: str) -> dict:
    """Standalone SSH payload: only semantic reads; credentials stay on the owner node."""
    import json
    from datetime import UTC, datetime
    from pathlib import Path
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    tokens = json.loads((Path.home() / ".local/share/uuma/data/tokens.json").read_text())

    def read(path: str, body: dict | None = None) -> dict:
        request = Request(
            "http://127.0.0.1:8773" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + tokens["brainstormer"],
                     "X-Uuma-Identity": "brainstormer", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=4) as response:
            return json.load(response)

    health = read("/health")
    if health.get("status") != "ok" or health.get("service") != "uuma-state-daemon":
        raise ValueError("Brainstormer navigation owner is unavailable")
    navigation = read("/api/v1/navigation", {"action": "list", "user_id": user_id})
    projects = sorted({row["project_id"] for row in (
        *navigation["topics"], *navigation["topic_groups"],
    )})
    graphs = [read("/api/v1/graph/" + quote(project, safe="")) for project in projects]
    return {
        "owner_node": "alandelone-server-001", "agent": "brainstormer",
        "read_at": datetime.now(UTC).isoformat(), "navigation": navigation, "graphs": graphs,
    }


class RemoteBrainstormerReader:
    """Short shared cache of live semantic responses; failures never use obsolete local data."""

    def __init__(self, marker: Path) -> None:
        self.marker = marker
        self.error: str | None = None
        self._snapshot: dict | None = None
        self._checked = float("-inf")
        self._lock = threading.Lock()

    def read(self) -> dict | None:
        with self._lock:
            if time.monotonic() - self._checked < 10:
                return self._snapshot
            try:
                owner = json.loads(self.marker.read_text(encoding="utf-8"))
                if (owner.get("agent") != "brainstormer"
                        or owner.get("owner_node") != "alandelone-server-001"):
                    raise ValueError("Unrecognized Brainstormer owner marker")
                user = owner["navigation_user_id"]
                if not isinstance(user, str) or not user.isdecimal() or len(user) > 32:
                    raise ValueError("Invalid navigation user scope")
                script = inspect.getsource(read_brainstormer_snapshot)
                script += "\nimport json\nprint(json.dumps(read_brainstormer_snapshot("
                script += repr(user) + "),ensure_ascii=True))\n"
                result = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     os.environ.get("UUMA_OBSERVATORY_BRAINSTORMER_SSH_HOST", "ubuntu-server"),
                     "python3", "-B", "-"],
                    input=script, capture_output=True, text=True, encoding="utf-8", timeout=18,
                    check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode:
                    raise OSError("Owner navigation API or SSH unavailable")
                snapshot = json.loads(result.stdout)
                if (snapshot.get("agent") != "brainstormer"
                        or snapshot.get("owner_node") != "alandelone-server-001"
                        or not isinstance(snapshot.get("graphs"), list)
                        or not isinstance(snapshot.get("navigation"), dict)):
                    raise ValueError("Invalid Brainstormer snapshot")
                self._snapshot = snapshot
                self.error = None
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                self._snapshot = None
                self.error = f"服务器议题来源暂不可用（{type(exc).__name__}）；请检查连接。"
            self._checked = time.monotonic()
            return self._snapshot


def snapshot_items(snapshot: dict) -> list[dict]:
    """Project actual semantic nodes into the Observatory's existing topic/detail presentation."""
    items = []
    navigation = snapshot["navigation"]
    binding = navigation.get("binding") or {}
    for graph in snapshot["graphs"]:
        project = graph["project_id"]
        source = "alandelone-server-001:brainstormer:" + project
        nodes = graph["nodes"]
        updated = max((n.get("values", {}).get("updated_at", "") for n in nodes), default="")
        all_topics = [row for row in [*navigation["topics"], *navigation["topic_groups"]]
                      if row["project_id"] == project]
        topics = []
        categories = {"question": "questions", "decision": "decisions",
                      "assumption": "assumptions", "evidence": "evidences",
                      "checkpoint": "checkpoints"}
        for entry in all_topics:
            topic_id = entry["id"]
            topic = {
                "topic_id": topic_id, "title": entry["title"],
                "description": entry.get("description") or entry.get("summary") or "",
                "icon": entry.get("icon") or "◈",
                "is_canonical_topic": entry.get("is_canonical_topic", False),
                "is_current": binding.get("active_project_id") == project
                and binding.get("active_topic_id") == topic_id,
                "latest_updated_at": updated,
                **{name: [] for name in categories.values()},
            }
            for node in nodes:
                category = categories.get(node["kind"])
                values = node.get("values") or {}
                if not category or values.get("topic_id") != topic_id:
                    continue
                record = {
                    **values, "id": node["id"], "type": node["kind"],
                    "title": node["title"], "status": node["status"], "topic_id": topic_id,
                    "body": values.get("body") or values.get("content") or values.get("text")
                    or values.get("summary") or "",
                    "rationale": values.get("rationale") or "",
                    "is_current": node.get("is_current", False),
                    "parent_question_ids": node.get("parent_question_ids") or [],
                    "in_links": [edge for edge in graph["edges"]
                                 if edge["target"] == node["id"]],
                    "out_links": [edge for edge in graph["edges"]
                                  if edge["source"] == node["id"]],
                }
                topic[category].append(record)
            topics.append(topic)
        grouped = {name: [row for topic in topics for row in topic[name]]
                   for name in categories.values()}
        pending = [d for d in grouped["decisions"] if d["status"] not in {
            "CONFIRMED", "APPROVED", "ACCEPTED", "RESOLVED", "accepted",
        }]
        confirmed = [d for d in grouped["decisions"] if d not in pending]
        canonical = sum(topic["is_canonical_topic"] for topic in topics)
        summary = (f"正式议题 {canonical} 个 · 问题 {len(grouped['questions'])} 个 · "
                   f"待确认假设 {len(grouped['assumptions'])} 项 · "
                   f"检查点 {len(grouped['checkpoints'])} 个 · 修订 r{graph['revision']}")
        links = [{**edge, "source_id": edge["source"], "target_id": edge["target"]}
                 for edge in graph["edges"]]
        payload = {
            "project_id": project, "revision": graph["revision"], "updated_at": updated,
            "summary": summary, "topics": topics, "topics_count": canonical,
            "topic_groups_count": len(topics) - canonical,
            "discussed_decisions": grouped["decisions"], "confirmed_decisions": confirmed,
            "pending_decisions": pending, "open_questions": grouped["questions"],
            "assumptions": grouped["assumptions"], "evidences": grouped["evidences"],
            "checkpoints": grouped["checkpoints"], "dag_links": links,
            "raw_objects_count": len(nodes), "active_question_id": graph["active_question_id"],
            "progression": graph["progression"], "hierarchy": graph["hierarchy"],
            "latest_checkpoint": graph.get("latest_checkpoint"), "binding": binding,
            "source_owner": snapshot["owner_node"], "source_read_at": snapshot["read_at"],
        }
        project_node = next((n for n in nodes if n["kind"] == "project"), {})
        items.append({
            "agent_id": "brainstormer", "item_id": "bs_dag_" + project,
            "title": project_node.get("title") or "当前研讨计划", "kind": "decision_dag",
            "status": "ACTIVE", "health": "HEALTHY", "updated_at": updated,
            "summary": summary, "source_ref": source, "payload": payload,
        })
        for topic in topics:
            items.append({
                "agent_id": "brainstormer",
                "item_id": "bs_top_" + project + "_" + topic["topic_id"],
                "title": "议题: " + topic["title"], "kind": "architecture_topic",
                "status": "ACTIVE" if topic["is_canonical_topic"] else "INFERRED",
                "health": "HEALTHY", "updated_at": updated,
                "summary": (f"问题 {len(topic['questions'])} 个 · 假设 {len(topic['assumptions'])} 项"
                            f" · 检查点 {len(topic['checkpoints'])} 个"),
                "source_ref": source + ":" + topic["topic_id"],
                "payload": {"topic": topic, "project_id": project, "revision": graph["revision"],
                            "is_canonical_topic": topic["is_canonical_topic"],
                            "all_topics": [{"topic_id": t["topic_id"], "title": t["title"]}
                                           for t in topics],
                            "active_question_id": graph["active_question_id"],
                            "progression": graph["progression"], "hierarchy": graph["hierarchy"],
                            "source_owner": snapshot["owner_node"]},
            })
        for question in grouped["questions"]:
            items.append({
                "agent_id": "brainstormer", "item_id": "bs_que_" + question["id"],
                "title": "待讨论问题: " + question["title"], "kind": "open_question",
                "status": question["status"], "health": "HEALTHY", "updated_at": updated,
                "summary": "当前讨论问题" if question["is_current"] else "保留原始问题状态与来源",
                "source_ref": source + ":" + question["id"],
                "payload": {"question": question, "project_id": project},
            })
    if not items:
        items.append({
            "agent_id": "brainstormer", "item_id": "bs_server_empty",
            "title": "服务器暂无议题", "kind": "source_status", "status": "IDLE",
            "health": "HEALTHY", "summary": "服务器连接正常，尚无已保存的议题。",
            "source_ref": "alandelone-server-001:brainstormer:navigation",
            "payload": {"source_read_at": snapshot["read_at"]},
        })
    return items
