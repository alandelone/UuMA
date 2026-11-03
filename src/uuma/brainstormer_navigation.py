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
from uuma.brainstormer_topic_groups import TOPIC_GROUP_METADATA, topic_group_title


class BrainstormerNavigation:
    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.lock = threading.RLock()

    @staticmethod
    def _counts(objects: list[dict[str, Any]], topic_id: str) -> dict[str, int]:
        records = [
            obj
            for obj in objects
            if obj.get("kind") != "topic"
            and (obj.get("topic_id") or "topic_general_architecture") == topic_id
        ]
        questions = [obj for obj in records if obj.get("kind") == "question"]
        return {
            "object_count": len(records),
            "question_count": len(questions),
            "open_question_count": sum(
                1
                for item in questions
                if str(item.get("status", "OPEN")).upper()
                not in {"RESOLVED", "DECIDED", "SUPERSEDED", "REJECTED"}
            ),
            "decision_count": sum(1 for item in records if item.get("kind") == "decision"),
            "assumption_count": sum(
                1 for item in records if item.get("kind") == "assumption"
            ),
            "evidence_count": sum(1 for item in records if item.get("kind") == "evidence"),
            "checkpoint_count": sum(
                1 for item in records if item.get("kind") == "checkpoint"
            ),
        }

    def _entries(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        topics: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        for path in sorted(self.daemon.store.projects.glob("*/state.json")):
            state = json.loads(path.read_text(encoding="utf-8"))
            project_id = state.get("project_id") or path.parent.name
            objects = list(state["objects"].values())
            project_topics = {
                item["id"]: item for item in objects if item.get("kind") == "topic"
            }
            for item in project_topics.values():
                topics.append(
                    {
                        **item,
                        "project_id": project_id,
                        "is_canonical_topic": True,
                        **self._counts(objects, item["id"]),
                    }
                )

            group_ids = {
                item.get("topic_id") or "topic_general_architecture"
                for item in objects
                if item.get("kind") != "topic"
            } - set(project_topics)
            for topic_id in sorted(group_ids):
                metadata = TOPIC_GROUP_METADATA.get(topic_id, {})
                groups.append(
                    {
                        "id": topic_id,
                        "topic_id": topic_id,
                        "kind": "topic_group",
                        "title": topic_group_title(topic_id),
                        "button_title": metadata.get("button_title", topic_group_title(topic_id)),
                        "description": metadata.get("description", ""),
                        "icon": metadata.get("icon", "◈"),
                        "status": "INFERRED",
                        "project_id": project_id,
                        "is_canonical_topic": False,
                        **self._counts(objects, topic_id),
                    }
                )
        topics.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        groups.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        return topics, groups

    def topics(self) -> list[dict[str, Any]]:
        return self._entries()[0]

    def topic_groups(self) -> list[dict[str, Any]]:
        return self._entries()[1]

    def _find_entry(self, project_id: str, topic_id: str) -> dict[str, Any] | None:
        topics, groups = self._entries()
        return next(
            (
                item
                for item in (*topics, *groups)
                if item["project_id"] == project_id and item["id"] == topic_id
            ),
            None,
        )

    def context(self, user_id: str) -> dict[str, Any]:
        binding = self.daemon.db.get_binding(user_id)
        if not binding or not binding.get("active_topic_id"):
            return {"binding": binding, "context": None, "selected_topic": None}
        project, topic = binding["active_project_id"], binding["active_topic_id"]
        with self.daemon.get_project_lock(project):
            context = self.daemon.store.get_context(project, topic)
            selected = self._find_entry(project, topic)
            if selected is None:
                raise BrainstormerError("当前议题不存在；请用 /topics 重新选择。")
            graph = self.daemon.store.get_decision_map(project, topic)
        return {
            "binding": binding,
            "context": context,
            "decision_map": graph,
            "selected_topic": selected,
        }

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self._execute(request)

    def _execute(self, request: dict[str, Any]) -> dict[str, Any]:
        action, user = request["action"], request["user_id"]
        actor = request.get("authenticated_actor", user)
        if action == "list":
            topics, groups = self._entries()
            return {"topics": topics, "topic_groups": groups, **self.context(user)}
        if action == "context":
            return self.context(user)
        if action == "switch":
            selector = request.get("selector", "").strip().casefold()
            topics, groups = self._entries()
            rows = [*topics, *groups]
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
        if action == "question":
            title = request.get("title", "").strip()
            ref = request.get("source_ref", "").strip()
            parent_id = request.get("selector", "").strip()
            binding = self.daemon.db.get_binding(user)
            if not title or not ref or not binding or not binding.get("active_topic_id"):
                raise BrainstormerError(
                    "先选择议题，再使用 /issue new 问题；子问题使用 /issue sub 问题ID 内容。"
                )
            project, topic = binding["active_project_id"], binding["active_topic_id"]
            digest = hashlib.sha256(f"{user}:{ref}".encode()).hexdigest()[:24]
            target = f"que_{digest}"
            with self.daemon.get_project_lock(project):
                state = self.daemon.store.get_context(project, topic)
                if self._find_entry(project, topic) is None:
                    raise BrainstormerError("当前议题已不存在；请用 /topics 重新选择。")
                existing = next(
                    (item for item in state["objects"] if item["id"] == target),
                    None,
                )
                if existing:
                    return {"status": "already_saved", "question_id": target}
                if parent_id and not any(
                    item["id"] == parent_id and item["kind"] == "question"
                    for item in state["objects"]
                ):
                    raise BrainstormerError("找不到这个议题下的问题；请先用 /agenda 查看问题ID。")
                values: dict[str, Any] = {
                    "title": title,
                    "topic_id": topic,
                    "status": "OPEN",
                }
                if parent_id:
                    values["parent_question_id"] = parent_id
                tx = StateTransaction(
                    project_id=project,
                    rationale="Explicit Telegram command to record an open question",
                    source_refs=[ref],
                    operations=[
                        StateOperation(
                            action="CREATE",
                            kind="question",
                            target_id=target,
                            values=values,
                        )
                    ],
                )
                proposal = self.daemon.store.propose(tx, requested_by=actor)
                receipt = self.daemon.store.commit_safe(
                    proposal["proposal_id"], actor_id=actor
                )
            return {
                "status": "created",
                "question_id": target,
                "revision": receipt["project_revision"],
            }
        if action == "checkpoint":
            text = request.get("text", "").strip()
            ref = request.get("source_ref", "").strip()
            binding = self.daemon.db.get_binding(user)
            if not text or len(text) > 4000 or not ref:
                raise BrainstormerError("请使用 /checkpoint 进度摘要（最多4000字）。")
            if not binding or not binding.get("active_topic_id"):
                raise BrainstormerError("先用 /topics 选择议题，再保存检查点。")
            project, topic = binding["active_project_id"], binding["active_topic_id"]
            digest = hashlib.sha256(f"{user}:{ref}".encode()).hexdigest()[:24]
            target = f"checkpoint_{digest}"
            with self.daemon.get_project_lock(project):
                state = self.daemon.store.get_context(project, topic)
                if self._find_entry(project, topic) is None:
                    raise BrainstormerError("当前议题已不存在；请用 /topics 重新选择。")
                if any(item["id"] == target for item in state["objects"]):
                    return {"status": "already_saved", "checkpoint_id": target}
                tx = StateTransaction(
                    project_id=project,
                    rationale="Explicit Telegram command to preserve a discussion checkpoint",
                    source_refs=[ref],
                    operations=[
                        StateOperation(
                            action="CHECKPOINT",
                            kind="checkpoint",
                            target_id=target,
                            values={
                                "title": "研讨进度检查点",
                                "summary": text,
                                "text": text,
                                "topic_id": topic,
                                "source_ref": ref,
                                "record_type": "user_checkpoint",
                            },
                        )
                    ],
                )
                proposal = self.daemon.store.propose(tx, requested_by=actor)
                receipt = self.daemon.store.commit_safe(
                    proposal["proposal_id"], actor_id=actor
                )
            return {
                "status": "saved",
                "checkpoint_id": target,
                "revision": receipt["project_revision"],
            }
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
                if self._find_entry(project, topic) is None:
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
