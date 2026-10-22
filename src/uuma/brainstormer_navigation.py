"""Personal discussion navigation, hosted by the shared state daemon.

Canonical objects stay in BrainstormerStore; bindings and raw turns use navigation persistence.
Only an explicit create command performs user-reviewed structural creation.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from uuma.brainstormer_state import BrainstormerError, StateOperation, StateTransaction


class BrainstormerNavigation:
    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.lock = threading.RLock()

    def topics(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.daemon.store.projects.glob("*/state.json")):
            state = json.loads(path.read_text(encoding="utf-8"))
            for item in state["objects"].values():
                if item["kind"] == "topic":
                    rows.append({**item, "project_id": state["project_id"]})
        return rows

    def context(self, user_id: str) -> dict[str, Any]:
        binding = self.daemon.db.get_binding(user_id)
        if not binding or not binding.get("active_topic_id"):
            return {"binding": binding, "context": None}
        project, topic = binding["active_project_id"], binding["active_topic_id"]
        with self.daemon.get_project_lock(project):
            context = self.daemon.store.get_context(project, topic)
            if not any(x["id"] == topic and x["kind"] == "topic" for x in context["objects"]):
                raise BrainstormerError("当前议题不存在；请用 /topics 重新选择。")
            graph = self.daemon.store.get_decision_map(project, topic)
        return {"binding": binding, "context": context, "decision_map": graph}

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self._execute(request)

    def _execute(self, request: dict[str, Any]) -> dict[str, Any]:
        action, user = request["action"], request["user_id"]
        actor = request.get("authenticated_actor", user)
        if action == "list":
            return {"topics": self.topics(), **self.context(user)}
        if action == "context":
            return self.context(user)
        if action == "switch":
            selector = request.get("selector", "").strip().casefold()
            rows = self.topics()
            exact = [
                x
                for x in rows
                if selector
                in {
                    x["id"].casefold(),
                    str(x.get("title", "")).casefold(),
                    f"{x['project_id']}/{x['id']}".casefold(),
                }
            ]
            matches = exact or [
                x for x in rows if selector and selector in str(x.get("title", "")).casefold()
            ]
            if len(matches) != 1:
                return {"status": "ambiguous" if matches else "not_found", "matches": matches}
            target = matches[0]
            # Existing checkpoints are append-only. Switching never resolves the old topic.
            self.daemon.db.set_binding(user, target["project_id"], target["id"])
            return {"status": "switched", **self.context(user)}
        if action == "create":
            title = request.get("title", "").strip()
            ref = request.get("source_ref", "").strip()
            if not title or len(title) > 160 or not ref:
                raise BrainstormerError("请使用 /topics new 议题名称（最多160字）。")
            # Identity from transport makes retries idempotent, never merges same-name topics.
            digest = hashlib.sha256(f"{user}:{ref}".encode()).hexdigest()[:24]
            project, topic = f"discussion_{digest}", f"topic_{digest}"
            with self.daemon.get_project_lock(project):
                current = self.daemon.store.get_context(project, topic)
                if not current["objects"]:
                    tx = StateTransaction(
                        project_id=project,
                        rationale="Explicit user topic creation",
                        source_refs=[ref],
                        operations=[
                            StateOperation(
                                action="CREATE",
                                kind="project",
                                target_id=project,
                                values={"title": title},
                            ),
                            StateOperation(
                                action="CREATE",
                                kind="topic",
                                target_id=topic,
                                values={"title": title},
                            ),
                        ],
                    )
                    proposal = self.daemon.store.propose(tx, requested_by=actor)
                    self.daemon.store.review(
                        proposal["proposal_id"],
                        actor_id=request.get("authenticated_actor", "user"),
                        approve=True,
                        note=f"Explicit /topics new command: {ref}",
                    )
            self.daemon.db.set_binding(user, project, topic)
            return {"status": "created", **self.context(user)}
        if action == "turn":
            project, topic = request.get("project_id"), request.get("topic_id")
            text, ref = request.get("text", ""), request.get("source_ref", "")
            if not project or not topic or not text or not ref:
                raise BrainstormerError("讨论记录缺少议题、内容或来源。")
            role = request.get("role", "user")
            if role not in {"user", "assistant"}:
                raise BrainstormerError("Invalid discussion role")
            target = "checkpoint_" + hashlib.sha256(f"{ref}:{role}".encode()).hexdigest()[:24]
            with self.daemon.get_project_lock(project):
                state = self.daemon.store.get_context(project, topic)
                if not any(x["kind"] == "topic" and x["id"] == topic for x in state["objects"]):
                    raise BrainstormerError("Unknown discussion topic")
                if any(x["id"] == target for x in state["objects"]):
                    return {"status": "already_saved"}
                tx = StateTransaction(
                    project_id=project,
                    rationale="Preserve authored discussion turn without inferring decisions",
                    source_refs=[ref],
                    operations=[
                        StateOperation(
                            action="CHECKPOINT",
                            kind="checkpoint",
                            target_id=target,
                            values={
                                "title": "讨论进度",
                                "topic_id": topic,
                                "role": role,
                                "text": text,
                                "source_ref": ref,
                                "record_type": "conversation_turn",
                            },
                        )
                    ],
                )
                proposal = self.daemon.store.propose(tx, requested_by=actor)
                receipt = self.daemon.store.commit_safe(proposal["proposal_id"], actor_id=actor)
            return {"status": "saved", "revision": receipt["project_revision"]}
        raise BrainstormerError("Unknown navigation action")
