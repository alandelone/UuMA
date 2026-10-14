"""Version-bound scientific proposals; approval still requires trusted user ingress."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .database import transaction
from .fieldkg import digest
from .models import DecisionProposalInput, StrictModel
from .research_views import (
    parse_record,
    require,
    rows,
    skeleton_source,
    track_workspace,
)
from .research_workspace import WorkspaceError
from .source_review import evidence_is_available
from .track_first import TrackFirstService, _now


class ScientificAction(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    field_id: str
    track_id: str
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]


class ProposeDecision(ScientificAction):
    operation: Literal["PROPOSE_DECISION"]
    proposal: DecisionProposalInput

    @model_validator(mode="after")
    def unique_dependencies(self):
        for values in [self.proposal.evidence_ids, self.proposal.upstream_node_ids]:
            if len(values) != len(set(values)) or len(values) > 500:
                raise ValueError("Select each scientific dependency once (maximum 500)")
        return self


class ApplyDecision(ScientificAction):
    operation: Literal["APPLY_DECISION"]
    proposal_id: str
    expected_revision: int = Field(ge=1)


TrackScientificAction = Annotated[ProposeDecision | ApplyDecision,
                                  Field(discriminator="operation")]


def scientific_context(conn: sqlite3.Connection, track_id: str) -> dict[str, Any]:
    view = track_workspace(conn, track_id)
    field_id = view["track"]["field_id"]
    evidence = rows(conn, """SELECT * FROM evidence WHERE
        (scope_kind='TRACK' AND track_id=?) OR (scope_kind='FIELDKG' AND field_id=?)
        ORDER BY evidence_id""", (track_id, field_id))
    adopted = {}
    for snapshot in view["adopted_snapshots"]:
        adoption = next(a for a in view["adoptions"] if a["snapshot_id"] == snapshot["snapshot_id"])
        if (snapshot["digest_matches"] and snapshot["members_match"]
                and adoption["snapshot_digest"] == snapshot["content_digest"]):
            for member in snapshot["members"]:
                if member["member_type"] == "EVIDENCE":
                    adopted.setdefault(member["member_id"], []).append({
                        "snapshot_id": snapshot["snapshot_id"], "version": snapshot["version"],
                        "evidence_digest": member["member_digest"],
                    })
    sources = {}
    for item in evidence:
        location = json.loads(item["location_json"])
        item["adopted_in"] = adopted.get(item["evidence_id"], [])
        item["source_available"] = evidence_is_available(conn, item)
        item["digest_matches"] = item["content_digest"] == digest([
            item["statement"], item["excerpt"], location,
        ])
        item["selectable"] = (item["source_available"] and item["digest_matches"] and (
            item["scope_kind"] == "TRACK" or any(
                a["evidence_digest"] == item["content_digest"] for a in item["adopted_in"]
            )
        ))
        skeleton_id = location.get("skeleton_id")
        if skeleton_id and skeleton_id not in sources:
            sources[skeleton_id] = skeleton_source(conn, skeleton_id)
    # Grants are deliberately outside this stamp: capturing user approval must not
    # alter the scientific content being compared. Membership/binding changes do.
    context = {"track": view["track"], "field": view["field"], "nodes": view["nodes"],
               "edges": view["edges"], "node_evidence": view["node_evidence"],
               "evidence": [parse_record(item) for item in evidence],
               "decisions": view["decisions"], "adoptions": view["adoptions"],
               "snapshots": view["adopted_snapshots"], "sources": list(sources.values()),
               "source_reviews": view["source_reviews"], "manuscripts": view["manuscripts"],
               "manuscript_nodes": rows(conn, """SELECT mn.* FROM manuscript_nodes mn
                   JOIN manuscripts m ON m.manuscript_id=mn.manuscript_id
                   WHERE m.track_id=? ORDER BY mn.manuscript_id,mn.node_id""", (track_id,))}
    context["context_sha256"] = digest(context)
    return context


def dependency_stamp(context: dict, proposal: DecisionProposalInput) -> dict:
    nodes = {n["node_id"]: n for n in context["nodes"]}
    required = set(proposal.upstream_node_ids)
    pending = list(required)
    while pending:
        node_id = pending.pop()
        for edge in context["edges"]:
            if edge["target_node_id"] == node_id and edge["source_node_id"] not in required:
                required.add(edge["source_node_id"])
                pending.append(edge["source_node_id"])
    evidence_ids = set(proposal.evidence_ids)
    evidence_ids.update(link["evidence_id"] for link in context["node_evidence"]
                        if link["node_id"] in required)
    evidence = [e for e in context["evidence"] if e["evidence_id"] in evidence_ids]
    skeleton_ids = {e["location"].get("skeleton_id") for e in evidence}
    return {"track_id": context["track"]["track_id"],
            "nodes": [nodes[nid] for nid in sorted(required) if nid in nodes],
            "evidence": evidence,
            "sources": [s for s in context["sources"] if s["skeleton_id"] in skeleton_ids],
            "replacement": nodes.get(proposal.supersedes_node_id)}


class TrackScientificWorkspace(TrackFirstService):
    def __init__(self, db_path: Path):
        # Browsing/applying must not initialize or migrate an existing user's catalog.
        self.db_path = db_path
        self.root = db_path.parent.parent
        self.artifacts_root = self.root / "data" / "artifacts"

    @staticmethod
    def _proposal(conn: sqlite3.Connection, proposal_id: str) -> dict:
        row = conn.execute("""SELECT d.*,n.statement,n.rationale,n.revision,n.payload_json
            FROM decisions d JOIN research_nodes n ON n.node_id=d.node_id
            WHERE d.proposal_id=?""", (proposal_id,)).fetchone()
        if row is None:
            raise WorkspaceError(404, "Scientific proposal not found")
        result = parse_record(dict(row))
        result["grant_available"] = bool(conn.execute("""SELECT 1 FROM approval_grants
            WHERE proposal_id=? AND proposal_type='decision' AND proposal_revision=?
            AND consumed_at IS NULL""", (proposal_id, result["revision"])).fetchone())
        return result

    def context(self, track_id: str) -> dict:
        if not self.db_path.is_file():
            raise WorkspaceError(503, "Catalog database is unavailable")
        with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            result = scientific_context(conn, track_id)
            result["proposals"] = [self._proposal(conn, item["proposal_id"])
                                   for item in result["decisions"]]
            result["receipts"] = [json.loads(row[0]) for row in conn.execute(
                """SELECT result_json FROM research_workspace_actions
                   WHERE object_type='track_scientific_decision' ORDER BY action_seq"""
            ) if json.loads(row[0]).get("track_id") == track_id]
            for proposal in result["proposals"]:
                proposal["basis_captured"] = any(
                    receipt["object_id"] == proposal["proposal_id"]
                    and receipt["operation"] == "PROPOSE_DECISION"
                    for receipt in result["receipts"]
                )
            return result

    @staticmethod
    def _validate_dependencies(context: dict, proposal: DecisionProposalInput) -> None:
        evidence = {e["evidence_id"]: e for e in context["evidence"]}
        if any(eid not in evidence or not evidence[eid]["selectable"]
               for eid in proposal.evidence_ids):
            raise WorkspaceError(409, "Evidence must be available in this Track or its adopted Snapshot")
        nodes = {n["node_id"]: n for n in context["nodes"]}
        pending = list(proposal.upstream_node_ids)
        visited = set()
        while pending:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            if node_id not in nodes or nodes[node_id]["status"] != "APPROVED":
                raise WorkspaceError(409, "Every scientific upstream dependency must be currently approved in this Track")
            for link in context["node_evidence"]:
                if link["node_id"] == node_id and (
                    link["evidence_id"] not in evidence or not evidence[link["evidence_id"]]["selectable"]
                ):
                    raise WorkspaceError(409, "An upstream scientific source requires review")
            pending.extend(e["source_node_id"] for e in context["edges"]
                           if e["target_node_id"] == node_id)

    def act(self, action: TrackScientificAction) -> dict:
        if not self.db_path.is_file():
            raise WorkspaceError(503, "Catalog database is unavailable")
        request_json = json.dumps(action.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT request_json,result_json FROM research_workspace_actions WHERE request_id=?", (action.request_id,)).fetchone()
            if old:
                if old["request_json"] != request_json:
                    raise WorkspaceError(409, "This request ID belongs to another scientific operation")
                return json.loads(old["result_json"])
            require(conn, "field", action.field_id)
            context = scientific_context(conn, action.track_id)
            if context["track"]["field_id"] != action.field_id:
                raise WorkspaceError(404, "Track does not belong to this Field")
            if context["context_sha256"] != action.expected_context_sha256:
                raise WorkspaceError(409, "Scientific content changed; refresh and compare the original basis")
            if isinstance(action, ProposeDecision):
                self._validate_dependencies(context, action.proposal)
                proposal_id = self._propose_decision(conn, action.track_id, action.proposal)
                dependency_basis = dependency_stamp(context, action.proposal)
            else:
                proposal_id = action.proposal_id
                proposal = self._proposal(conn, proposal_id)
                if proposal["track_id"] != action.track_id:
                    raise WorkspaceError(404, "Proposal does not belong to this Track")
                payload = DecisionProposalInput(kind=proposal["kind"], statement=proposal["statement"],
                    rationale=proposal["rationale"], **proposal["payload"],
                    supersedes_node_id=proposal["supersedes_node_id"])
                self._validate_dependencies(context, payload)
                original = conn.execute("""SELECT result_json FROM research_workspace_actions
                    WHERE object_type='track_scientific_decision' AND object_id=?
                    ORDER BY action_seq LIMIT 1""", (proposal_id,)).fetchone()
                dependency_basis = dependency_stamp(context, payload)
                if (original is None or digest(json.loads(original[0])["dependency_basis"])
                        != digest(dependency_basis)):
                    raise WorkspaceError(409, "Original proposal basis changed or was not captured; create a new reviewed proposal")
                self._approve_decision(conn, proposal_id, action.expected_revision)
            result = {"request_id": action.request_id, "operation": action.operation,
                      "field_id": action.field_id, "track_id": action.track_id,
                      "object_type": "track_scientific_decision", "object_id": proposal_id,
                      "proposal": self._proposal(conn, proposal_id), "basis": context,
                      "dependency_basis": dependency_basis}
            conn.execute("""INSERT INTO research_workspace_actions
                (request_id,request_json,object_type,object_id,result_json,created_at)
                VALUES(?,?,?,?,?,?)""", (action.request_id, request_json, result["object_type"],
                proposal_id, json.dumps(result, ensure_ascii=False), _now()))
            return result
