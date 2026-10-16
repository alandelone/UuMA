from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class BrainstormerError(RuntimeError):
    pass


class RevisionConflict(BrainstormerError):
    pass


class CycleDetectedError(BrainstormerError):
    """Raised when an operation would create a directed cycle in the decision DAG."""


class ObjectKind(str, Enum):
    PROJECT = "project"
    TOPIC = "topic"
    DECISION = "decision"
    ASSUMPTION = "assumption"
    QUESTION = "question"
    CHECKPOINT = "checkpoint"
    EVIDENCE = "evidence"


class RelationCategory(str, Enum):
    HIERARCHY = "hierarchy"
    DEPENDENCY = "dependency"


class StandardRelation(str, Enum):
    # Hierarchy relations (归属关系)
    CONTAINS = "contains"
    SUBQUESTION = "subquestion"
    PARENT_OF = "parent_of"

    # Grounding / Dependency relations (依据/依赖关系)
    DEPENDS_ON = "depends_on"
    GROUNDS = "grounds"
    BASED_ON = "based_on"
    SUPPORTS = "supports"
    DECIDES = "decides"
    RESOLVES = "resolves"


def classify_relation(relation: str) -> RelationCategory:
    rel = relation.lower().strip()
    if rel in {
        "contains",
        "subquestion",
        "subquestion_of",
        "parent_of",
        "has_topic",
        "has_question",
        "has_subquestion",
        "hierarchy",
        "part_of",
        "belongs_to",
    }:
        return RelationCategory.HIERARCHY
    return RelationCategory.DEPENDENCY


def would_create_cycle(links: list[dict[str, Any]], source_id: str, target_id: str) -> bool:
    """Check if adding directed edge source_id -> target_id creates a cycle."""
    if source_id == target_id:
        return True
    adj: dict[str, list[str]] = {}
    for link in links:
        s = link.get("source_id")
        t = link.get("target_id")
        if s and t:
            adj.setdefault(s, []).append(t)

    visited: set[str] = set()
    queue = [target_id]
    visited.add(target_id)
    while queue:
        curr = queue.pop(0)
        if curr == source_id:
            return True
        for nxt in adj.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return False


class TransactionAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REOPEN = "REOPEN"
    SUPERSEDE = "SUPERSEDE"
    RESOLVE = "RESOLVE"
    LINK = "LINK"
    UNLINK = "UNLINK"
    CHECKPOINT = "CHECKPOINT"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StateOperation(StrictModel):
    action: TransactionAction
    kind: ObjectKind
    target_id: str
    expected_revision: int | None = Field(default=None, ge=0)
    values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_create_values(self) -> StateOperation:
        if (
            self.action in {TransactionAction.CREATE, TransactionAction.CHECKPOINT}
            and not self.values.get("title")
        ):
            raise ValueError("CREATE and CHECKPOINT require a title")
        return self


class StateTransaction(StrictModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    operations: list[StateOperation] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=8000)
    source_refs: list[str] = Field(default_factory=list)


class BrainstormerStore:
    """Versioned project JSON managed through validated transaction proposals."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.projects = self.root / "projects"
        self.proposals = self.root / "proposals"
        self._lock = threading.RLock()
        self.projects.mkdir(parents=True, exist_ok=True)
        self.proposals.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> BrainstormerStore:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data = Path(os.environ.get("UUMA_DATA_DIR", local / "UuMA"))
        return cls(data / "brainstormer")

    def propose(self, transaction: StateTransaction, *, requested_by: str) -> dict[str, Any]:
        with self._lock:
            current = self._load_project(transaction.project_id)
            self._validate_transaction_dag(current["links"], transaction.operations)
            proposal_id = _id("brainstorm")
            payload = {
                "proposal_id": proposal_id,
                "status": "PROPOSED",
                "requested_by": requested_by,
                "review_required": self._review_required(transaction),
                "created_at": _now(),
                "transaction": transaction.model_dump(mode="json"),
            }
            self._atomic_json(self._proposal_path(proposal_id), payload)
            return payload

    @staticmethod
    def _validate_transaction_dag(
        existing_links: list[dict[str, Any]], operations: list[StateOperation]
    ) -> None:
        simulated = [dict(link) for link in existing_links]
        for op in operations:
            if op.action is TransactionAction.UNLINK:
                val = op.values
                s_id = val.get("source_id")
                t_id = val.get("target_id")
                rel = val.get("relation")
                simulated = [
                    l for l in simulated
                    if not (
                        l.get("source_id") == s_id
                        and l.get("target_id") == t_id
                        and (rel is None or l.get("relation") == rel)
                    )
                ]
            elif op.action is TransactionAction.LINK:
                val = op.values
                s_id = val.get("source_id")
                t_id = val.get("target_id")
                if s_id and t_id:
                    if s_id == t_id:
                        raise CycleDetectedError(
                            f"Self-referential link is not allowed: '{s_id}' -> '{t_id}'"
                        )
                    if would_create_cycle(simulated, s_id, t_id):
                        raise CycleDetectedError(
                            f"Cycle detected: adding edge '{s_id}' -> '{t_id}' would create a directed cycle in the decision graph"
                        )
                    simulated.append({"source_id": s_id, "target_id": t_id})

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._proposal_path(proposal_id)
            if not path.is_file():
                raise BrainstormerError(f"Unknown proposal: {proposal_id}")
            return json.loads(path.read_text(encoding="utf-8"))

    def find_pending_topic_proposal(
        self, project_id: str, topic_id: str
    ) -> dict[str, Any] | None:
        """Reuse an unreviewed structural proposal instead of proposing a duplicate topic."""
        with self._lock:
            self._project_path(project_id)  # validate identifier
            for path in self.proposals.glob("*.json"):
                proposal = json.loads(path.read_text(encoding="utf-8"))
                transaction = proposal.get("transaction") or {}
                if (
                    proposal.get("status") != "PROPOSED"
                    or transaction.get("project_id") != project_id
                ):
                    continue
                if any(
                    operation.get("kind") == ObjectKind.TOPIC.value
                    and operation.get("action") == TransactionAction.CREATE.value
                    and operation.get("target_id") == topic_id
                    for operation in transaction.get("operations") or []
                ):
                    return proposal
        return None

    def review(
        self, proposal_id: str, *, actor_id: str, approve: bool, note: str
    ) -> dict[str, Any]:
        with self._lock:
            proposal = self.get_proposal(proposal_id)
            if proposal["status"] != "PROPOSED":
                raise RevisionConflict("Only a pending proposal may be reviewed")
            if approve:
                state = self._apply(
                    StateTransaction.model_validate(proposal["transaction"]), proposal
                )
                proposal["status"] = "APPROVED"
                proposal["project_revision"] = state["revision"]
            else:
                proposal["status"] = "REJECTED"
            proposal["reviewed_by"] = actor_id
            proposal["review_note"] = note
            proposal["reviewed_at"] = _now()
            self._atomic_json(self._proposal_path(proposal_id), proposal)
            return proposal

    def commit_safe(self, proposal_id: str, *, actor_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal["review_required"]:
            raise PermissionError("This transaction requires Orchestrator/user review")
        return self.review(
            proposal_id, actor_id=actor_id, approve=True, note="validated safe state"
        )

    def get_context(self, project_id: str, topic_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._load_project(project_id)
            objects = list(state["objects"].values())
            if topic_id:
                objects = [
                    item
                    for item in objects
                    if item["id"] == topic_id or item.get("topic_id") == topic_id
                ]
            return {
                "project_id": project_id,
                "revision": state["revision"],
                "objects": objects,
                "links": state["links"],
                "active_question_id": state.get("active_question_id"),
                "latest_checkpoint": next(
                    (item for item in reversed(objects) if item["kind"] == "checkpoint"), None
                ),
            }

    def set_active_question(
        self, project_id: str, question_id: str, *, actor_id: str = "user"
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load_project(project_id)
            if question_id not in state["objects"]:
                raise BrainstormerError(f"Question not found in project: {question_id}")
            target = state["objects"][question_id]
            if target["kind"] != ObjectKind.QUESTION.value:
                raise BrainstormerError(
                    f"Target object is not a question: {question_id} ({target['kind']})"
                )

            for obj in state["objects"].values():
                if obj["kind"] == ObjectKind.QUESTION.value:
                    obj["is_current"] = (obj["id"] == question_id)

            state["active_question_id"] = question_id
            state["revision"] += 1
            state["updated_at"] = _now()
            state["history"].append(
                {
                    "action": "SET_ACTIVE_QUESTION",
                    "target_id": question_id,
                    "actor_id": actor_id,
                    "revision": state["revision"],
                    "applied_at": state["updated_at"],
                }
            )
            self._atomic_json(self._project_path(project_id), state)
            return {
                "project_id": project_id,
                "active_question_id": question_id,
                "revision": state["revision"],
            }

    def get_decision_map(
        self, project_id: str, topic_id: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load_project(project_id)
            all_objects = deepcopy(state["objects"])
            all_links = deepcopy(state["links"])
            active_q_id = state.get("active_question_id")

            # Categorize objects by kind
            questions = {k: v for k, v in all_objects.items() if v.get("kind") == ObjectKind.QUESTION.value}
            decisions = {k: v for k, v in all_objects.items() if v.get("kind") == ObjectKind.DECISION.value}
            assumptions = {k: v for k, v in all_objects.items() if v.get("kind") == ObjectKind.ASSUMPTION.value}
            evidences = {k: v for k, v in all_objects.items() if v.get("kind") == ObjectKind.EVIDENCE.value}
            topics = {k: v for k, v in all_objects.items() if v.get("kind") == ObjectKind.TOPIC.value}

            # Graph relation maps
            parent_questions: dict[str, list[str]] = {q_id: [] for q_id in questions}
            subquestions: dict[str, list[str]] = {q_id: [] for q_id in questions}
            dependencies: dict[str, list[str]] = {q_id: [] for q_id in questions}
            dependents: dict[str, list[str]] = {q_id: [] for q_id in questions}
            question_groundings: dict[str, list[str]] = {q_id: [] for q_id in questions}
            decision_groundings: dict[str, list[str]] = {d_id: [] for d_id in decisions}

            for link in all_links:
                s = link.get("source_id")
                t = link.get("target_id")
                rel = link.get("relation", "relates_to").lower().strip()

                if rel in {"subquestion", "parent_of", "has_subquestion"}:
                    if s in questions and t in questions:
                        if t not in subquestions[s]:
                            subquestions[s].append(t)
                        if s not in parent_questions[t]:
                            parent_questions[t].append(s)
                elif rel == "subquestion_of" and s in questions and t in questions:
                    if s not in subquestions[t]:
                        subquestions[t].append(s)
                    if t not in parent_questions[s]:
                        parent_questions[s].append(t)

                if rel in {"depends_on", "prerequisite"}:
                    if s in questions and t in questions:
                        if t not in dependencies[s]:
                            dependencies[s].append(t)
                        if s not in dependents[t]:
                            dependents[t].append(s)
                elif rel in {"blocks", "prerequisite_for"} and s in questions and t in questions:
                    if s not in dependencies[t]:
                        dependencies[t].append(s)
                    if t not in dependents[s]:
                        dependents[s].append(t)

                if rel in {"grounds", "based_on", "supports", "evidences", "assumes", "decides", "resolves"}:
                    if (s in assumptions or s in evidences) and t in questions and s not in question_groundings[t]:
                        question_groundings[t].append(s)
                    if (s in questions or s in assumptions or s in evidences) and t in decisions and s not in decision_groundings[t]:
                        decision_groundings[t].append(s)
                    if rel == "based_on" and s in decisions and (t in questions or t in assumptions or t in evidences) and t not in decision_groundings[s]:
                        decision_groundings[s].append(t)

                if s in questions and t in decisions and s not in decision_groundings[t]:
                    decision_groundings[t].append(s)

            for q_id, q in questions.items():
                p_id = q.get("parent_question_id")
                if p_id and p_id in questions:
                    if q_id not in subquestions[p_id]:
                        subquestions[p_id].append(q_id)
                    if p_id not in parent_questions[q_id]:
                        parent_questions[q_id].append(p_id)

            q_progression: dict[str, dict[str, Any]] = {}
            for q_id, q in questions.items():
                is_resolved = q.get("status") in {"RESOLVED", "DECIDED"}
                if not is_resolved:
                    for d_id, g_ids in decision_groundings.items():
                        if q_id in g_ids and decisions[d_id].get("status") != "REJECTED":
                            is_resolved = True
                            break

                prereqs = dependencies.get(q_id, [])
                unresolved_prereqs = [
                    p for p in prereqs
                    if questions.get(p, {}).get("status") not in {"RESOLVED", "DECIDED"}
                ]
                is_blocked = (len(unresolved_prereqs) > 0) and not is_resolved
                is_ready = (not is_blocked) and (not is_resolved) and (q.get("status") != "SUPERSEDED")
                is_current = bool(q.get("is_current") or q_id == active_q_id)

                q_progression[q_id] = {
                    "is_resolved": is_resolved,
                    "is_blocked": is_blocked,
                    "is_ready": is_ready,
                    "is_current": is_current,
                    "unresolved_prereqs": unresolved_prereqs,
                    "prerequisites": prereqs,
                }

            current_q_id = None
            for q_id, prog in q_progression.items():
                if prog["is_current"]:
                    current_q_id = q_id
                    break

            ready_list = [q_id for q_id, p in q_progression.items() if p["is_ready"]]
            blocked_list = [
                {"id": q_id, "blocked_by": p["unresolved_prereqs"]}
                for q_id, p in q_progression.items()
                if p["is_blocked"]
            ]
            resolved_list = [q_id for q_id, p in q_progression.items() if p["is_resolved"]]

            def _q_sort_key(q_id: str) -> tuple:
                q = questions[q_id]
                unresolved_subs = sum(
                    1
                    for sub_id in subquestions.get(q_id, [])
                    if not q_progression.get(sub_id, {}).get("is_resolved")
                )
                has_unresolved_subs = 1 if unresolved_subs > 0 else 0
                is_subquestion = 0 if parent_questions.get(q_id) else 1
                priority = -int(q.get("priority", 0))
                created = q.get("created_at", "")
                return (has_unresolved_subs, is_subquestion, priority, created)

            ready_list.sort(key=_q_sort_key)
            recommended_next = (
                current_q_id
                if (current_q_id in ready_list)
                else (ready_list[0] if ready_list else None)
            )

            hierarchy: list[dict[str, Any]] = []
            topic_items = (
                list(topics.values())
                if topics
                else [{"id": "topic-general", "title": "General"}]
            )
            for t in topic_items:
                t_id = t["id"]
                t_questions = [
                    q_id
                    for q_id, q in questions.items()
                    if q.get("topic_id") == t_id or not q.get("topic_id")
                ]
                root_qs = [q_id for q_id in t_questions if not parent_questions.get(q_id)]

                def _build_tree(q_id: str, visited: set[str]) -> dict[str, Any]:
                    visited.add(q_id)
                    children = [
                        _build_tree(sub_id, visited)
                        for sub_id in subquestions.get(q_id, [])
                        if sub_id not in visited
                    ]
                    q = questions[q_id]
                    prog = q_progression[q_id]
                    return {
                        "id": q_id,
                        "title": q.get("title") or q_id,
                        "status": (
                            "RESOLVED"
                            if prog["is_resolved"]
                            else ("BLOCKED" if prog["is_blocked"] else "READY")
                        ),
                        "is_current": prog["is_current"],
                        "subquestions": children,
                    }

                t_tree = {
                    "topic_id": t_id,
                    "title": t.get("title") or t_id,
                    "questions": [_build_tree(rq, set()) for rq in root_qs],
                }
                hierarchy.append(t_tree)

            nodes: list[dict[str, Any]] = []
            target_objects = (
                [
                    v
                    for v in all_objects.values()
                    if v["id"] == topic_id or v.get("topic_id") == topic_id
                ]
                if topic_id
                else list(all_objects.values())
            )
            for obj in target_objects:
                kind = obj.get("kind", "topic")
                node: dict[str, Any] = {
                    "id": obj["id"],
                    "kind": kind,
                    "title": obj.get("title") or obj.get("id"),
                    "status": obj.get("status", "ACTIVE"),
                    "revision": obj.get("revision", 1),
                    "topic_id": obj.get("topic_id"),
                    "values": {
                        k: v
                        for k, v in obj.items()
                        if k not in {"id", "kind", "status", "revision", "title"}
                    },
                }
                if kind == ObjectKind.QUESTION.value:
                    prog = q_progression.get(obj["id"], {})
                    node.update(
                        {
                            "is_ready": prog.get("is_ready", True),
                            "is_blocked": prog.get("is_blocked", False),
                            "is_current": prog.get("is_current", False),
                            "unresolved_dependencies": prog.get("unresolved_prereqs", []),
                            "parent_question_ids": parent_questions.get(obj["id"], []),
                            "subquestion_ids": subquestions.get(obj["id"], []),
                            "grounding_ids": question_groundings.get(obj["id"], []),
                        }
                    )
                elif kind == ObjectKind.DECISION.value:
                    node.update(
                        {
                            "grounding_ids": decision_groundings.get(obj["id"], []),
                        }
                    )
                nodes.append(node)

            edges: list[dict[str, Any]] = []
            for idx, link in enumerate(all_links):
                s = link.get("source_id")
                t = link.get("target_id")
                rel = link.get("relation", "relates_to")
                cat = link.get("category") or classify_relation(rel).value
                edges.append(
                    {
                        "id": f"edge_{idx}_{s}_{t}",
                        "source": s,
                        "target": t,
                        "relation": rel,
                        "category": cat,
                    }
                )

            summary = {
                "total_objects": len(all_objects),
                "topics_count": len(topics),
                "questions_count": len(questions),
                "ready_questions_count": len(ready_list),
                "blocked_questions_count": len(blocked_list),
                "resolved_questions_count": len(resolved_list),
                "decisions_count": len(decisions),
                "assumptions_count": len(assumptions),
                "evidences_count": len(evidences),
                "edges_count": len(all_links),
            }

            return {
                "project_id": project_id,
                "revision": state["revision"],
                "active_question_id": current_q_id or recommended_next,
                "nodes": nodes,
                "edges": edges,
                "progression": {
                    "active_question_id": current_q_id or recommended_next,
                    "recommended_next_question_id": recommended_next,
                    "ready_questions": ready_list,
                    "blocked_questions": blocked_list,
                    "resolved_questions": resolved_list,
                },
                "hierarchy": hierarchy,
                "summary": summary,
                "latest_checkpoint": next(
                    (
                        item
                        for item in reversed(list(all_objects.values()))
                        if item.get("kind") == "checkpoint"
                    ),
                    None,
                ),
            }

    def search_topics(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            terms = query.casefold().split()
            results: list[dict[str, Any]] = []
            for path in self.projects.glob("*/state.json"):
                state = json.loads(path.read_text(encoding="utf-8"))
                for item in state["objects"].values():
                    if item["kind"] != "topic":
                        continue
                    text = json.dumps(item, ensure_ascii=False).casefold()
                    score = sum(term in text for term in terms)
                    if score:
                        results.append(
                            {"score": score, "project_id": state["project_id"], **item}
                        )
            return sorted(results, key=lambda item: (-item["score"], item["updated_at"]))[
                :limit
            ]

    def _apply(self, transaction: StateTransaction, proposal: dict[str, Any]) -> dict[str, Any]:
        current = self._load_project(transaction.project_id)
        state = deepcopy(current)
        for operation in transaction.operations:
            self._apply_operation(state, operation)
        state["revision"] += 1
        state["updated_at"] = _now()
        state["history"].append(
            {
                "proposal_id": proposal["proposal_id"],
                "revision": state["revision"],
                "requested_by": proposal["requested_by"],
                "rationale": transaction.rationale,
                "source_refs": transaction.source_refs,
                "applied_at": state["updated_at"],
            }
        )
        self._atomic_json(self._project_path(transaction.project_id), state)
        return state

    def _apply_operation(self, state: dict[str, Any], operation: StateOperation) -> None:
        objects = state["objects"]
        existing = objects.get(operation.target_id)
        if operation.action in {TransactionAction.CREATE, TransactionAction.CHECKPOINT}:
            if existing is not None:
                raise RevisionConflict(f"Object already exists: {operation.target_id}")
            if operation.expected_revision not in {None, 0}:
                raise RevisionConflict("New objects require expected_revision 0 or null")
            now = _now()
            objects[operation.target_id] = {
                "id": operation.target_id,
                "kind": operation.kind.value,
                "status": "ACTIVE",
                "revision": 1,
                "project_id": state["project_id"],
                "created_at": now,
                "updated_at": now,
                **operation.values,
            }
            return
        if existing is None:
            raise BrainstormerError(f"Unknown object: {operation.target_id}")
        if existing["kind"] != operation.kind.value:
            raise BrainstormerError(
                f"Object kind mismatch for {operation.target_id}: {existing['kind']}"
            )
        if operation.action in {TransactionAction.LINK, TransactionAction.UNLINK}:
            if (
                operation.expected_revision is not None
                and operation.expected_revision != existing["revision"]
            ):
                raise RevisionConflict(f"Stale object revision: {operation.target_id}")
        else:
            if operation.expected_revision != existing["revision"]:
                raise RevisionConflict(f"Stale object revision: {operation.target_id}")

        if operation.action is TransactionAction.LINK:
            link = operation.values
            source_id = link.get("source_id")
            target_id = link.get("target_id")
            if not source_id or not target_id:
                raise BrainstormerError("Links require source_id and target_id")
            if source_id not in objects or target_id not in objects:
                raise BrainstormerError("Links require existing source and target objects")
            if source_id == target_id:
                raise CycleDetectedError(
                    f"Self-referential link is not allowed: '{source_id}' -> '{target_id}'"
                )
            if would_create_cycle(state["links"], source_id, target_id):
                raise CycleDetectedError(
                    f"Cycle detected: adding edge '{source_id}' -> '{target_id}' would create a directed cycle in the decision graph"
                )
            relation = link.get("relation", "relates_to")
            category = link.get("category")
            if not category:
                category = classify_relation(relation).value
            elif isinstance(category, RelationCategory):
                category = category.value
            normalized_link = {
                "source_id": source_id,
                "target_id": target_id,
                "relation": relation,
                "category": category,
                **{k: v for k, v in link.items() if k not in {"source_id", "target_id", "relation", "category"}},
            }
            if not any(
                l.get("source_id") == source_id
                and l.get("target_id") == target_id
                and l.get("relation") == relation
                for l in state["links"]
            ):
                state["links"].append(normalized_link)
        elif operation.action is TransactionAction.UNLINK:
            val = operation.values
            s_id = val.get("source_id")
            t_id = val.get("target_id")
            rel = val.get("relation")
            state["links"] = [
                link for link in state["links"]
                if not (
                    link.get("source_id") == s_id
                    and link.get("target_id") == t_id
                    and (rel is None or link.get("relation") == rel)
                )
            ]
        else:
            status = {
                TransactionAction.REOPEN: "ACTIVE",
                TransactionAction.SUPERSEDE: "SUPERSEDED",
                TransactionAction.RESOLVE: "RESOLVED",
            }.get(operation.action)
            if status:
                existing["status"] = status
            existing.update(operation.values)
            existing["revision"] += 1
            existing["updated_at"] = _now()

    def _review_required(self, transaction: StateTransaction) -> bool:
        current = self._load_project(transaction.project_id)
        structural = {ObjectKind.PROJECT, ObjectKind.TOPIC, ObjectKind.DECISION}
        for operation in transaction.operations:
            existing = current["objects"].get(operation.target_id)
            actual_kind = ObjectKind(existing["kind"]) if existing else operation.kind
            if operation.action in {TransactionAction.LINK, TransactionAction.UNLINK}:
                link = operation.values
                s = current["objects"].get(link.get("source_id", ""))
                t = current["objects"].get(link.get("target_id", ""))
                if (s and s["kind"] == ObjectKind.DECISION.value) or (
                    t and t["kind"] == ObjectKind.DECISION.value
                ):
                    return True
                continue
            if actual_kind in structural or operation.action is TransactionAction.SUPERSEDE:
                return True
        return False

    def _load_project(self, project_id: str) -> dict[str, Any]:
        path = self._project_path(project_id)
        if not path.is_file():
            return {
                "schema_version": 1,
                "project_id": project_id,
                "revision": 0,
                "objects": {},
                "links": [],
                "history": [],
                "updated_at": _now(),
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def _project_path(self, project_id: str) -> Path:
        self._validate_identifier(project_id)
        return self.projects / project_id / "state.json"

    def _proposal_path(self, proposal_id: str) -> Path:
        self._validate_identifier(proposal_id)
        return self.proposals / f"{proposal_id}.json"

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if _IDENTIFIER.fullmatch(value) is None:
            raise BrainstormerError(f"Invalid identifier: {value!r}")

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)

