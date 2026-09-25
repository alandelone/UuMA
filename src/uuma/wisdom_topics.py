from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Iterable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .knowledge_models import (
    GapRecord,
    GapType,
    KnowledgeTopicRecord,
    QuestionRecord,
    TopicDocumentRecord,
    TopicDocumentVersionRecord,
    TopicKnowledgeLinkRecord,
    TopicQuestionLinkRecord,
    TopicRouteRecord,
)
from .knowledge_service import KnowledgeService, json_record

_GENERIC_PREFIXES = (
    "我想了解", "我想知道", "请研究", "请介绍", "帮我研究", "帮我了解", "关于",
    "针对", "tell me about", "research", "explain", "learn about",
)
_CONTINUATION_MARKERS = (
    "more detail", "more details", "go deeper", "continue", "继续", "详细一点",
    "更详细", "深入一点", "展开", "补充",
)
_FOCUS_MARKERS = ("重点", "focus", "着重", "主要研究", "方向是", "优先")


def normalize_topic_text(text: str) -> str:
    value = text.casefold().strip()
    value = re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)
    for prefix in _GENERIC_PREFIXES:
        normalized_prefix = re.sub(r"[\s\W_]+", "", prefix.casefold())
        value = value.removeprefix(normalized_prefix)
    return value[:2000] or "topic"


def is_machine_error_payload(text: str) -> bool:
    """A pasted API error is diagnostic input, never a research topic."""
    try:
        value = json.loads(text.strip())
    except (ValueError, TypeError):
        return False
    return (
        isinstance(value, dict)
        and bool(value)
        and set(value) <= {"detail", "error", "message", "status", "status_code"}
        and any(key in value for key in ("detail", "error"))
    )


def grounded_answer(answer: dict[str, Any]) -> dict[str, Any]:
    """Do not relay an uncited KAG retrieval as a factual answer."""
    if answer.get("citations"):
        return answer
    return answer | {
        "answer": "No relevant, traceable evidence is available yet. Research is needed before answering.",
        "conditions": [],
        "conflicts": [],
        "satisfaction_level": "INSUFFICIENT",
        "satisfaction_rationale": "The retrieved answer had no traceable citations and was withheld.",
    }


def is_progress_request(text: str) -> bool:
    """Recognize standalone operational questions; domain research is resolved separately."""
    value = re.sub(r"[\s?.!？！。]+", " ", text.casefold()).strip()
    return value in {
        "how is your progress", "what is your progress", "any progress", "progress",
        "status", "what is the status", "how is it going", "are you still researching",
        "research status", "research progress", "进度", "研究进度", "现在进度怎样",
        "进展如何", "有什么进展", "你研究到哪里了", "你做到哪里了", "还在研究吗",
    }


def _features(text: str) -> set[str]:
    lowered = text.casefold()
    latin = set(re.findall(r"[a-z0-9]+", lowered))
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk: set[str] = set()
    for run in cjk_runs:
        cjk.update(run)
        cjk.update(run[index:index + 2] for index in range(max(0, len(run) - 1)))
    return latin | cjk


def _similarity(left: str, right: str) -> float:
    left_features = _features(left)
    right_features = _features(right)
    if not left_features or not right_features:
        return 0.0
    overlap = left_features & right_features
    return (2 * len(overlap)) / (len(left_features) + len(right_features))


def _route_key(route: dict[str, str] | None) -> str | None:
    if not route or not route.get("platform"):
        return None
    stable = {
        key: str(route.get(key) or "")
        for key in ("platform", "chat_id", "thread_id")
    }
    if not stable["chat_id"]:
        stable["session_id"] = str(route.get("session_id") or "")
    material = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def ensure_view_token(data_dir: Path) -> str:
    path = data_dir / "wisdom-view-token"
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(token)
    except FileExistsError:
        existing = path.read_text(encoding="utf-8").strip()
        return existing or token
    return token


class TopicKnowledgeService:
    """Durable topic/question organization and versioned human-readable research documents."""

    def __init__(
        self,
        knowledge: KnowledgeService,
        *,
        view_base_url: str = "http://127.0.0.1:8767",
        view_token: str | None = None,
    ) -> None:
        self.knowledge = knowledge
        self.store = knowledge.store
        self.view_base_url = view_base_url.rstrip("/")
        self.view_token = view_token

    def topic_url(self, topic_id: str, anchor: str | None = None) -> str:
        url = f"{self.view_base_url}/wisdom/topics/{topic_id.replace('_', '%5F')}"
        if self.view_token:
            url += f"?token={self.view_token.replace('_', '%5F')}"
        if anchor:
            url += f"#{anchor}"
        return url

    def _insert(self, conn, table: str, model, event_type: str, actor_id: str) -> dict[str, Any]:
        record = json_record(model)
        record_id = record[self.store_id(table)]
        event = self.store.append_event(
            conn,
            event_type=event_type,
            aggregate_type=self.knowledge.AGGREGATE_TYPES[table],
            aggregate_id=record_id,
            actor_id=actor_id,
            payload={"record": record},
        )
        self.store.insert_record(conn, table, record, event.sequence)
        return record

    def _update(
        self,
        conn,
        table: str,
        before: dict[str, Any],
        after: dict[str, Any],
        event_type: str,
        actor_id: str,
    ) -> dict[str, Any]:
        record_id = after[self.store_id(table)]
        event = self.store.append_event(
            conn,
            event_type=event_type,
            aggregate_type=self.knowledge.AGGREGATE_TYPES[table],
            aggregate_id=record_id,
            actor_id=actor_id,
            payload={"before": before, "after": after},
        )
        self.store.update_record(conn, table, after, event.sequence)
        return after

    @staticmethod
    def store_id(table: str) -> str:
        from .knowledge_store import TABLE_IDS

        return TABLE_IDS[table]

    @staticmethod
    def _continuation(text: str) -> bool:
        lowered = text.casefold().strip()
        return any(marker in lowered for marker in _CONTINUATION_MARKERS)

    @staticmethod
    def _focus_request(text: str) -> bool:
        lowered = text.casefold()
        return any(marker in lowered for marker in _FOCUS_MARKERS)

    @staticmethod
    def is_broad_topic_request(text: str) -> bool:
        lowered = text.casefold().strip()
        specific_markers = (
            "为什么", "怎么", "如何", "是否", "哪一个", "比较", "原因", "机制",
            "why", "how", "which", "compare", "is it", "does",
        )
        return not any(marker in lowered for marker in specific_markers)

    @staticmethod
    def _title(text: str) -> str:
        title = text.strip(" \t\r\n，。！？,.!?:：;；")
        for prefix in _GENERIC_PREFIXES:
            if title.casefold().startswith(prefix.casefold()):
                title = title[len(prefix):].strip(" ，。:：")
        return (title or text.strip())[:160]

    def _topic_candidates(self, conn) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        topics = [
            json.loads(row["record_json"])
            for row in conn.execute(
                "SELECT record_json FROM knowledge_topics WHERE status = 'ACTIVE'"
            ).fetchall()
        ]
        candidates: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for topic in topics:
            rows = conn.execute(
                "SELECT q.record_json FROM questions q JOIN topic_question_links l "
                "ON q.question_id = l.question_id WHERE l.topic_id = ?",
                (topic["topic_id"],),
            ).fetchall()
            candidates.append((topic, [json.loads(row["record_json"]) for row in rows]))
        return candidates

    def resolve_question(
        self,
        text: str,
        *,
        actor_id: str,
        route: dict[str, str] | None = None,
        allow_new_topic: bool = False,
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        text = text.strip()
        if not text:
            raise ValueError("Question must not be empty.")
        if is_machine_error_payload(text):
            raise ValueError("This is an API error response, not a research question.")
        if is_progress_request(text):
            raise ValueError("This is a progress request, not a research question.")
        now = datetime.now(UTC).isoformat()
        normalized = normalize_topic_text(text)
        route_key = _route_key(route)
        with self.store.transaction() as conn:
            current_route = None
            if route_key:
                row = conn.execute(
                    "SELECT record_json FROM topic_routes WHERE route_key = ?", (route_key,)
                ).fetchone()
                current_route = json.loads(row["record_json"]) if row else None

            candidates = self._topic_candidates(conn)
            selected: dict[str, Any] | None = None
            questions: list[dict[str, Any]] = []
            match_kind = "new_topic"
            score = 0.0
            route_topic = (
                self.knowledge._require("knowledge_topics", current_route["topic_id"], conn)
                if current_route and (self._continuation(text) or self._focus_request(text))
                else None
            )
            if route_topic and route_topic["status"] == "ACTIVE":
                selected = route_topic
                questions = next(
                    (items for topic, items in candidates if topic["topic_id"] == selected["topic_id"]),
                    [],
                )
                match_kind = "current_topic"
                score = 1.0
            else:
                for topic, topic_questions in candidates:
                    texts = [topic["title"], *topic.get("aliases", [])]
                    texts.extend(item["text"] for item in topic_questions)
                    candidate_score = max((_similarity(text, item) for item in texts), default=0.0)
                    if candidate_score > score:
                        selected, questions, score = topic, topic_questions, candidate_score
                if score < 0.26:
                    selected, questions = None, []
                elif selected:
                    match_kind = "related_question"

            if selected is None:
                if not allow_new_topic:
                    return {
                        "requires_topic_approval": True,
                        "proposed_topic": {
                            "question": text,
                            "title": self._title(text),
                            "scope": text,
                        },
                        "instruction": (
                            "Ask the user whether to create this topic and start research. "
                            "Wait for explicit approval; no topic, document or Orbit exists yet."
                        ),
                    }
                selected = self._insert(
                    conn,
                    "knowledge_topics",
                    KnowledgeTopicRecord(
                        title=self._title(text),
                        normalized_key=normalized,
                        aliases=[text],
                    ),
                    "KNOWLEDGE_TOPIC_CREATED",
                    actor_id,
                )
                question = self._insert(
                    conn,
                    "questions",
                    QuestionRecord(
                        text=text,
                        why_worth_knowing=f"Build a sourced, reusable understanding of {selected['title']}.",
                    ),
                    "QUESTION_ADDED",
                    actor_id,
                )
                self._insert(
                    conn,
                    "topic_question_links",
                    TopicQuestionLinkRecord(
                        topic_id=selected["topic_id"],
                        question_id=question["question_id"],
                        relationship="ROOT",
                        rationale="This question established the topic.",
                    ),
                    "TOPIC_QUESTION_LINKED",
                    actor_id,
                )
                self._insert(
                    conn,
                    "topic_documents",
                    TopicDocumentRecord(
                        topic_id=selected["topic_id"],
                        title=selected["title"],
                    ),
                    "TOPIC_DOCUMENT_CREATED",
                    actor_id,
                )
                questions = [question]
            else:
                exact = next(
                    (item for item in questions if normalize_topic_text(item["text"]) == normalized),
                    None,
                )
                if exact:
                    question = exact
                    match_kind = "exact_question"
                elif (
                    self._continuation(text) and current_route
                    and current_route["topic_id"] == selected["topic_id"]
                ):
                    question = self.knowledge._require(
                        "questions", current_route["question_id"], conn
                    )
                    match_kind = "same_question_followup"
                else:
                    parent_id = current_route["question_id"] if (
                        current_route and current_route["topic_id"] == selected["topic_id"]
                    ) else (
                        questions[0]["question_id"] if questions else None
                    )
                    relationship = "FOCUS" if self._focus_request(text) else "RELATED"
                    question = self._insert(
                        conn,
                        "questions",
                        QuestionRecord(
                            text=text,
                            why_worth_knowing=(
                                "The user identified this as a priority direction."
                                if relationship == "FOCUS"
                                else f"This question extends the {selected['title']} topic."
                            ),
                            parent_question_id=parent_id,
                        ),
                        "QUESTION_ADDED",
                        actor_id,
                    )
                    self._insert(
                        conn,
                        "topic_question_links",
                        TopicQuestionLinkRecord(
                            topic_id=selected["topic_id"],
                            question_id=question["question_id"],
                            relationship=relationship,
                            rationale=question["why_worth_knowing"],
                        ),
                        "TOPIC_QUESTION_LINKED",
                        actor_id,
                    )
                    match_kind = "focus_question" if relationship == "FOCUS" else match_kind
                    if relationship == "FOCUS" and text not in selected.get("focus", []):
                        updated = selected | {
                            "focus": [*selected.get("focus", []), text],
                            "updated_at": now,
                        }
                        selected = self._update(
                            conn,
                            "knowledge_topics",
                            selected,
                            updated,
                            "KNOWLEDGE_TOPIC_FOCUS_UPDATED",
                            actor_id,
                        )

            if route_key:
                if current_route:
                    updated_route = current_route | {
                        "topic_id": selected["topic_id"],
                        "question_id": question["question_id"],
                        "updated_at": now,
                    }
                    self._update(
                        conn,
                        "topic_routes",
                        current_route,
                        updated_route,
                        "TOPIC_ROUTE_UPDATED",
                        actor_id,
                    )
                else:
                    self._insert(
                        conn,
                        "topic_routes",
                        TopicRouteRecord(
                            route_key=route_key,
                            topic_id=selected["topic_id"],
                            question_id=question["question_id"],
                        ),
                        "TOPIC_ROUTE_CREATED",
                        actor_id,
                    )
        return {
            "topic": selected,
            "question": question,
            "match_kind": match_kind,
            "match_score": round(score, 4),
            "document_url": self.topic_url(selected["topic_id"]),
        }

    def ensure_research_framework(
        self,
        topic_id: str,
        root_question_id: str,
        *,
        actor_id: str,
    ) -> list[str]:
        """Create a reusable first-principles frontier once for a broad new topic."""
        self.knowledge.require_writer(actor_id)
        aspects = (
            (
                "范围、术语与关键分类",
                "Clarify scope, terminology, important variants, and what belongs outside the topic.",
                GapType.TERMINOLOGY,
            ),
            (
                "原理、机制与依赖条件",
                "Explain the mechanisms, causal dependencies, and boundary conditions.",
                GapType.MISSING_MECHANISM,
            ),
            (
                "实践方法、构成要素与关键参数",
                "Establish practical methods, components, specifications, and condition-sensitive parameters.",
                GapType.COVERAGE,
            ),
            (
                "替代方案、失败模式与风险",
                "Compare alternatives and identify common failure modes, risks, and mitigations.",
                GapType.FAILURE_MODE,
            ),
            (
                "证据质量、争议与最新进展",
                "Assess source authority, conflicting evidence, freshness, and current developments.",
                GapType.FRESHNESS,
            ),
        )
        created: list[str] = []
        with self.store.transaction() as conn:
            topic = self.knowledge._require("knowledge_topics", topic_id, conn)
            existing = conn.execute(
                "SELECT 1 FROM topic_question_links WHERE topic_id = ? AND relationship = 'SUBQUESTION'",
                (topic_id,),
            ).fetchone()
            if existing:
                rows = conn.execute(
                    "SELECT g.record_json FROM gaps g JOIN topic_question_links l "
                    "ON json_extract(g.record_json, '$.question_id') = l.question_id "
                    "WHERE l.topic_id = ? AND g.status = 'OPEN' "
                    "ORDER BY g.updated_sequence",
                    (topic_id,),
                ).fetchall()
                return [json.loads(row["record_json"])["gap_id"] for row in rows]
            for title, rationale, gap_type in aspects:
                question = self._insert(
                    conn,
                    "questions",
                    QuestionRecord(
                        text=f"{topic['title']}：{title}",
                        why_worth_knowing=rationale,
                        parent_question_id=root_question_id,
                    ),
                    "QUESTION_ADDED",
                    actor_id,
                )
                self._insert(
                    conn,
                    "topic_question_links",
                    TopicQuestionLinkRecord(
                        topic_id=topic_id,
                        question_id=question["question_id"],
                        relationship="SUBQUESTION",
                        rationale=rationale,
                    ),
                    "TOPIC_QUESTION_LINKED",
                    actor_id,
                )
                gap = self._insert(
                    conn,
                    "gaps",
                    GapRecord(
                        gap_type=gap_type,
                        reason=f"The topic document still needs a sourced section on {title}.",
                        why_worthwhile=rationale,
                        question_id=question["question_id"],
                    ),
                    "GAP_ADDED",
                    actor_id,
                )
                created.append(gap["gap_id"])
        return created

    def _citation_records(
        self,
        conn,
        answer: dict[str, Any],
        source_ids: Iterable[str],
        evidence_ids: Iterable[str],
    ) -> list[dict[str, Any]]:
        citations: dict[str, dict[str, Any]] = {}
        for raw in answer.get("citations", []):
            if not isinstance(raw, dict) or not raw.get("source_id"):
                continue
            citations[str(raw["source_id"])] = dict(raw)
        for source_id in source_ids:
            citations.setdefault(str(source_id), {"source_id": str(source_id)})
        evidence_by_source: dict[str, dict[str, Any]] = {}
        for evidence_id in evidence_ids:
            evidence = self.store.get_record("evidence", str(evidence_id), conn)
            if evidence:
                evidence_by_source.setdefault(evidence["source_id"], evidence)
        output: list[dict[str, Any]] = []
        for source_id, citation in citations.items():
            source = self.store.get_record("sources", source_id, conn)
            if not source:
                continue
            evidence = evidence_by_source.get(source_id)
            output.append(
                {
                    "source_id": source_id,
                    "evidence_id": citation.get("evidence_id") or (
                        evidence.get("evidence_id") if evidence else None
                    ),
                    "title": source.get("title") or source.get("locator"),
                    "locator": citation.get("locator") or source.get("locator"),
                    "location": citation.get("location") or (
                        evidence.get("location") if evidence else None
                    ),
                    "rationale": citation.get("rationale"),
                }
            )
        return output

    def _render_markdown(
        self,
        topic: dict[str, Any],
        sections: list[dict[str, Any]],
        *,
        status: str,
        rationale: str,
        updated_at: str,
    ) -> str:
        lines = [f"# {topic['title']}", "", f"最后更新：{updated_at}", ""]
        if topic.get("focus"):
            lines.extend(["## 当前研究重点", ""])
            lines.extend(f"- {item}" for item in topic["focus"])
            lines.append("")
        for section in sections:
            lines.extend([f"<a id=\"{section['anchor']}\"></a>", f"## {section['title']}", ""])
            lines.extend([section["body"].strip(), ""])
            if section.get("conditions"):
                lines.extend(["### 适用条件", ""])
                lines.extend(f"- {item}" for item in section["conditions"])
                lines.append("")
            if section.get("conflicts"):
                lines.extend(["### 证据与争议", ""])
                lines.extend(f"- {item}" for item in section["conflicts"])
                lines.append("")
            if section.get("citations"):
                lines.extend(["### 来源", ""])
                for citation in section["citations"]:
                    location = f" — {citation['location']}" if citation.get("location") else ""
                    lines.append(f"- [{citation['title']}]({citation['locator']}){location}")
                lines.append("")
        lines.extend(["## 研究状态", "", f"- 状态：{status}", f"- 判断：{rationale}", ""])
        return "\n".join(lines).strip() + "\n"

    def publish_answer(
        self,
        topic_id: str,
        question_id: str,
        answer: dict[str, Any],
        *,
        actor_id: str,
        research_status: str,
        orbit_id: str | None = None,
        orbit_cycle_id: str | None = None,
        source_ids: list[str] | None = None,
        evidence_ids: list[str] | None = None,
        conn=None,
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        context = nullcontext(conn) if conn is not None else self.store.transaction()
        with context as active:
            if orbit_cycle_id:
                row = active.execute(
                    "SELECT record_json FROM topic_document_versions WHERE orbit_cycle_id = ?",
                    (orbit_cycle_id,),
                ).fetchone()
                if row:
                    return json.loads(row["record_json"])
            topic = self.knowledge._require("knowledge_topics", topic_id, active)
            question = self.knowledge._require("questions", question_id, active)
            row = active.execute(
                "SELECT record_json FROM topic_documents WHERE topic_id = ?", (topic_id,)
            ).fetchone()
            if not row:
                document = self._insert(
                    active,
                    "topic_documents",
                    TopicDocumentRecord(topic_id=topic_id, title=topic["title"]),
                    "TOPIC_DOCUMENT_CREATED",
                    actor_id,
                )
            else:
                document = json.loads(row["record_json"])
            previous = None
            if document.get("latest_version_id"):
                previous = self.knowledge._require(
                    "topic_document_versions", document["latest_version_id"], active
                )
            sections = list(previous.get("sections", [])) if previous else []
            links = active.execute(
                "SELECT relationship FROM topic_question_links WHERE topic_id = ? AND question_id = ?",
                (topic_id, question_id),
            ).fetchone()
            root = bool(links and links["relationship"] == "ROOT")
            anchor = "overview" if root else f"question-{question_id.removeprefix('question_')[:12]}"
            citations = self._citation_records(
                active, answer, source_ids or [], evidence_ids or []
            )
            if not citations:
                answer = grounded_answer(answer | {"citations": []})
            section = {
                "anchor": anchor,
                "title": "主题概览" if root else question["text"],
                "question_id": question_id,
                "body": str(answer.get("answer") or "当前没有足够证据形成答案。"),
                "conditions": list(answer.get("conditions") or []),
                "conflicts": list(answer.get("conflicts") or []),
                "citations": citations,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            replaced = False
            for index, existing in enumerate(sections):
                if existing.get("question_id") == question_id:
                    sections[index] = section
                    replaced = True
                    break
            if not replaced:
                sections.append(section)
            now = datetime.now(UTC).isoformat()
            body = self._render_markdown(
                topic,
                sections,
                status=research_status,
                rationale=str(answer.get("satisfaction_rationale") or "尚未评估。"),
                updated_at=now,
            )
            version_number = int(document.get("current_version", 0)) + 1
            version = self._insert(
                active,
                "topic_document_versions",
                TopicDocumentVersionRecord(
                    topic_document_id=document["topic_document_id"],
                    topic_id=topic_id,
                    version=version_number,
                    body_markdown=body,
                    sections=sections,
                    change_summary=(
                        f"更新“{section['title']}”章节；纳入 {len(citations)} 个可追溯来源；"
                        f"研究状态为 {research_status}。"
                    ),
                    source_ids=list(dict.fromkeys(source_ids or [
                        item["source_id"] for item in citations
                    ])),
                    evidence_ids=list(dict.fromkeys(evidence_ids or [])),
                    orbit_id=orbit_id,
                    orbit_cycle_id=orbit_cycle_id,
                    research_status=research_status,
                ),
                "TOPIC_DOCUMENT_VERSION_PUBLISHED",
                actor_id,
            )
            updated_document = document | {
                "current_version": version_number,
                "latest_version_id": version["topic_document_version_id"],
                "updated_at": now,
            }
            self._update(
                active,
                "topic_documents",
                document,
                updated_document,
                "TOPIC_DOCUMENT_ADVANCED",
                actor_id,
            )
            for citation in citations:
                self._ensure_knowledge_link(
                    active,
                    topic_id,
                    "source",
                    citation["source_id"],
                    "SUPPORTS",
                    "This source is cited by the topic document.",
                    actor_id,
                )
                if citation.get("evidence_id"):
                    self._ensure_knowledge_link(
                        active,
                        topic_id,
                        "evidence",
                        citation["evidence_id"],
                        "SUPPORTS",
                        "This located evidence supports the topic document.",
                        actor_id,
                    )
            return version | {
                "document_url": self.topic_url(topic_id, anchor),
                "topic_title": topic["title"],
                "section_anchor": anchor,
            }

    def _ensure_knowledge_link(
        self,
        conn,
        topic_id: str,
        target_kind: str,
        target_id: str,
        relationship: str,
        rationale: str,
        actor_id: str,
    ) -> None:
        existing = conn.execute(
            "SELECT 1 FROM topic_knowledge_links WHERE topic_id = ? AND target_kind = ? "
            "AND target_id = ? AND relationship = ?",
            (topic_id, target_kind, target_id, relationship),
        ).fetchone()
        if existing:
            return
        self._insert(
            conn,
            "topic_knowledge_links",
            TopicKnowledgeLinkRecord(
                topic_id=topic_id,
                target_kind=target_kind,
                target_id=target_id,
                relationship=relationship,
                rationale=rationale,
            ),
            "TOPIC_KNOWLEDGE_LINKED",
            actor_id,
        )

    def retract_invalid_topic(
        self, topic_id: str, *, actor_id: str, reason: str,
        correction: str | None = None,
    ) -> dict[str, Any]:
        """Archive a polluted topic and publish a visible correction without erasing history."""
        self.knowledge.require_writer(actor_id)
        with self.store.transaction() as conn:
            topic = self.knowledge._require("knowledge_topics", topic_id, conn)
            if topic["status"] != "ACTIVE":
                raise ValueError("Topic is already archived.")
            row = conn.execute(
                "SELECT record_json FROM topic_documents WHERE topic_id = ?", (topic_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Topic document is missing.")
            document = json.loads(row["record_json"])
            now = datetime.now(UTC).isoformat()
            correction = correction or (
                "This page was created from an API error response, not a research request. "
                "The previous content was unrelated and had no traceable sources. "
                "It has been retracted; the original version remains in version history for audit."
            )
            previous = self.knowledge._require(
                "topic_document_versions", document["latest_version_id"], conn
            ) if document.get("latest_version_id") else {}
            anchors = list(dict.fromkeys([
                "overview", *[item["anchor"] for item in previous.get("sections", [])]
            ]))
            section = {
                "anchor": "overview",
                "title": "Correction and retraction",
                "body": correction,
                "conditions": [],
                "conflicts": [],
                "citations": [],
                "updated_at": now,
            }
            version = self._insert(
                conn,
                "topic_document_versions",
                TopicDocumentVersionRecord(
                    topic_document_id=document["topic_document_id"],
                    topic_id=topic_id,
                    version=int(document["current_version"]) + 1,
                    body_markdown=(
                        "# Correction and retraction\n\n"
                        + "\n".join(f'<a id="{anchor}"></a>' for anchor in anchors) + "\n"
                        f"## Correction and retraction\n\n{correction}\n\nReason: {reason}\n"
                    ),
                    sections=[section],
                    change_summary=f"Retracted unrelated, uncited content. {reason}",
                    research_status="STOPPED",
                ),
                "TOPIC_DOCUMENT_VERSION_RETRACTED",
                actor_id,
            )
            self._update(
                conn,
                "topic_documents",
                document,
                document | {
                    "current_version": version["version"],
                    "latest_version_id": version["topic_document_version_id"],
                    "updated_at": now,
                },
                "TOPIC_DOCUMENT_ADVANCED",
                actor_id,
            )
            self._update(
                conn,
                "knowledge_topics",
                topic,
                topic | {"status": "ARCHIVED", "summary": correction, "updated_at": now},
                "KNOWLEDGE_TOPIC_ARCHIVED",
                actor_id,
            )
            return version | {"document_url": self.topic_url(topic_id, "overview")}

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        topic = self.knowledge._require("knowledge_topics", topic_id)
        with self.store.connect() as conn:
            document_row = conn.execute(
                "SELECT record_json FROM topic_documents WHERE topic_id = ?", (topic_id,)
            ).fetchone()
            document = json.loads(document_row["record_json"]) if document_row else None
            latest = None
            if document and document.get("latest_version_id"):
                latest = self.knowledge._require(
                    "topic_document_versions", document["latest_version_id"], conn
                )
            question_rows = conn.execute(
                "SELECT q.record_json, l.record_json AS link_json FROM questions q "
                "JOIN topic_question_links l ON q.question_id = l.question_id "
                "WHERE l.topic_id = ? ORDER BY l.updated_sequence",
                (topic_id,),
            ).fetchall()
            questions = [
                {"question": json.loads(row["record_json"]), "link": json.loads(row["link_json"])}
                for row in question_rows
            ]
            versions = [
                json.loads(row["record_json"])
                for row in conn.execute(
                    "SELECT record_json FROM topic_document_versions WHERE topic_id = ? "
                    "ORDER BY version DESC LIMIT 100",
                    (topic_id,),
                ).fetchall()
            ]
            orbits = [
                json.loads(row["record_json"])
                for row in conn.execute(
                    "SELECT record_json FROM question_orbits "
                    "WHERE json_extract(record_json, '$.topic_id') = ? ORDER BY updated_sequence DESC",
                    (topic_id,),
                ).fetchall()
            ]
        return {
            "topic": topic,
            "document": document,
            "latest_version": latest,
            "questions": questions,
            "versions": versions,
            "orbits": orbits,
            "document_url": self.topic_url(topic_id),
        }

    def conversation_status(self, route: dict[str, str]) -> dict[str, Any]:
        """Read the persisted task state for this conversation without invoking retrieval."""
        key = _route_key(route)
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM topic_routes WHERE route_key = ?", (key,)
            ).fetchone() if key else None
        if not row:
            return {"status": "NO_CONTEXT", "tasks": [], "document_url": None}
        context = self.get_topic(json.loads(row["record_json"])["topic_id"])
        tasks = [{
            "orbit_id": item["orbit_id"], "status": item["status"],
            "updated_at": item["updated_at"], "stop_reason": item.get("stop_reason"),
        } for item in context["orbits"]]
        return {
            "topic_id": context["topic"]["topic_id"],
            "topic_title": context["topic"]["title"],
            "status": context["topic"]["status"],
            "tasks": tasks,
            "document_version": (context.get("document") or {}).get("current_version", 0),
            "document_url": context["document_url"],
        }

    def list_topics(self, *, limit: int = 100) -> dict[str, Any]:
        records = self.store.list_records("knowledge_topics", limit=limit)
        return {"count": len(records), "records": records}

    def graph(self, topic_id: str) -> dict[str, Any]:
        data = self.get_topic(topic_id)
        nodes = [{"id": topic_id, "kind": "topic", "label": data["topic"]["title"]}]
        edges: list[dict[str, str]] = []
        with self.store.connect() as conn:
            for item in data["questions"]:
                question = item["question"]
                link = item["link"]
                nodes.append(
                    {"id": question["question_id"], "kind": "question", "label": question["text"]}
                )
                edges.append(
                    {
                        "source": topic_id,
                        "target": question["question_id"],
                        "kind": link["relationship"],
                    }
                )
                gap_rows = conn.execute(
                    "SELECT record_json FROM gaps WHERE json_extract(record_json, '$.question_id') = ?",
                    (question["question_id"],),
                ).fetchall()
                for row in gap_rows:
                    gap = json.loads(row["record_json"])
                    nodes.append({"id": gap["gap_id"], "kind": "gap", "label": gap["reason"]})
                    edges.append(
                        {"source": question["question_id"], "target": gap["gap_id"], "kind": "GAP"}
                    )
            knowledge_rows = conn.execute(
                "SELECT record_json FROM topic_knowledge_links WHERE topic_id = ?",
                (topic_id,),
            ).fetchall()
            for row in knowledge_rows:
                link = json.loads(row["record_json"])
                target = self.store.get_record(
                    {"source": "sources", "evidence": "evidence", "claim": "claims",
                     "entity": "entities", "relation": "relations"}[link["target_kind"]],
                    link["target_id"],
                    conn,
                )
                if not target:
                    continue
                label = (
                    target.get("title") or target.get("statement") or target.get("canonical_name")
                    or target.get("excerpt") or target.get("predicate") or link["target_id"]
                )
                nodes.append(
                    {"id": link["target_id"], "kind": link["target_kind"], "label": str(label)[:500]}
                )
                edges.append(
                    {"source": topic_id, "target": link["target_id"], "kind": link["relationship"]}
                )
        unique_nodes = {node["id"]: node for node in nodes}
        return {"topic_id": topic_id, "nodes": list(unique_nodes.values()), "edges": edges}
