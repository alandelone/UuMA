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


class ObjectKind(str, Enum):
    PROJECT = "project"
    TOPIC = "topic"
    DECISION = "decision"
    ASSUMPTION = "assumption"
    QUESTION = "question"
    CHECKPOINT = "checkpoint"


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

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._proposal_path(proposal_id)
            if not path.is_file():
                raise BrainstormerError(f"Unknown proposal: {proposal_id}")
            return json.loads(path.read_text(encoding="utf-8"))

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
                "latest_checkpoint": next(
                    (item for item in reversed(objects) if item["kind"] == "checkpoint"), None
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
        if operation.expected_revision != existing["revision"]:
            raise RevisionConflict(f"Stale object revision: {operation.target_id}")
        if operation.action is TransactionAction.LINK:
            link = operation.values
            if link.get("source_id") not in objects or link.get("target_id") not in objects:
                raise BrainstormerError("Links require existing source and target objects")
            if link not in state["links"]:
                state["links"].append(link)
        elif operation.action is TransactionAction.UNLINK:
            state["links"] = [link for link in state["links"] if link != operation.values]
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
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(path)
