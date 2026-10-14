"""Immutable scientific binding proposals applied only through user approval grants."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from .acquisition import digest, stable_id, utc_now
from .approval import consume_grant
from .database import transaction
from .models import StrictModel
from .source_review import evidence_is_available


class ScientificBindingReviewInput(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    expected_revision: int = Field(ge=1)
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    node_ids: list[str] = Field(default_factory=list, max_length=200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=500)
    section_map: dict[str, list[str]] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def explicit_complete_binding(self):
        self.reason = self.reason.strip()
        if not self.reason or not self.node_ids and not self.evidence_ids:
            raise ValueError("Select reviewed scientific dependencies and give the review reason")
        if len(set(self.node_ids)) != len(self.node_ids) or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Scientific dependencies cannot be selected twice")
        mapped = [node for nodes in self.section_map.values() for node in nodes]
        if set(mapped) - set(self.node_ids) or len(mapped) != len(set(mapped)):
            raise ValueError("Section bindings must use selected nodes exactly once")
        return self


def bindings(conn: sqlite3.Connection, manuscript_id: str) -> dict[str, Any]:
    return {"nodes": [dict(row) for row in conn.execute("SELECT * FROM manuscript_nodes WHERE manuscript_id=? ORDER BY node_id", (manuscript_id,))],
            "evidence": [dict(row) for row in conn.execute("SELECT * FROM manuscript_evidence WHERE manuscript_id=? ORDER BY evidence_id", (manuscript_id,))]}


def scientific_binding_stamp(conn: sqlite3.Connection, manuscript_id: str) -> dict:
    event = conn.execute("SELECT event_id FROM manuscript_scientific_review_events WHERE manuscript_id=? ORDER BY rowid DESC LIMIT 1", (manuscript_id,)).fetchone()
    manuscript = conn.execute("SELECT needs_scientific_review FROM manuscripts WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    return {"event_id": event[0] if event else None, "bindings_sha256": digest(bindings(conn, manuscript_id)),
            "needs_scientific_review": bool(manuscript[0])}


def scientific_generation_is_stale(conn: sqlite3.Connection, manuscript_id: str, version_id: str | None) -> bool:
    if version_id is None:
        return False
    current = scientific_binding_stamp(conn, manuscript_id)
    version = conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=? AND manuscript_id=?", (version_id, manuscript_id)).fetchone()
    if version is None:
        return True
    saved = json.loads(version[0]).get("scientific_binding")
    if saved is None:
        return current["event_id"] is not None
    return saved != current


def scientific_context(conn: sqlite3.Connection, manuscript_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM manuscripts WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    if row is None:
        raise LookupError("Manuscript not found")
    manuscript = dict(row)
    track = conn.execute("SELECT * FROM research_tracks WHERE track_id=?", (manuscript["track_id"],)).fetchone()
    if track is None:
        raise ValueError("Manuscript owner Track is unavailable")
    nodes = [dict(row) for row in conn.execute("SELECT * FROM research_nodes WHERE track_id=? ORDER BY node_id", (manuscript["track_id"],))]
    evidence = [dict(row) for row in conn.execute("SELECT * FROM evidence WHERE (scope_kind='TRACK' AND track_id=?) OR (scope_kind='FIELDKG' AND field_id=?) ORDER BY evidence_id", (manuscript["track_id"], track["field_id"]))]
    for item in evidence:
        item["source_available"] = evidence_is_available(conn, item)
    context = {"manuscript": manuscript, "track": dict(track), "bindings": bindings(conn, manuscript_id),
               "nodes": nodes, "evidence": evidence,
               "edges": [dict(row) for row in conn.execute("SELECT * FROM research_edges WHERE track_id=? ORDER BY edge_id", (manuscript["track_id"],))],
               "node_evidence": [dict(row) for row in conn.execute("SELECT ne.* FROM node_evidence ne JOIN research_nodes n ON n.node_id=ne.node_id WHERE n.track_id=? ORDER BY ne.node_id,ne.evidence_id", (manuscript["track_id"],))]}
    document = conn.execute("SELECT revision,document_json FROM studio_documents WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    context["author_structure"] = {"revision": document[0], "sections": [{"id": section["id"], "title": section["title"]} for section in json.loads(document[1])["sections"]]} if document else None
    context["context_sha256"] = digest(context)
    return context


def validate_binding(conn: sqlite3.Connection, context: dict, payload: ScientificBindingReviewInput) -> dict:
    track_id = context["manuscript"]["track_id"]
    if context["track"]["mapping_status"] != "MAPPED":
        raise ValueError("Map the owner Track before scientific review")
    selected = {row["node_id"]: row for row in context["nodes"] if row["node_id"] in payload.node_ids}
    if set(selected) != set(payload.node_ids):
        raise ValueError("Selected scientific nodes must belong to this manuscript's Track")
    required = dict(selected)
    queue = list(selected)
    while queue:
        node_id = queue.pop()
        for row in conn.execute("SELECT n.* FROM research_edges e JOIN research_nodes n ON n.node_id=e.source_node_id WHERE e.target_node_id=? AND e.track_id=? AND n.track_id=?", (node_id, track_id, track_id)):
            if row["node_id"] not in required:
                required[row["node_id"]] = dict(row);queue.append(row["node_id"])
    if any(row["status"] != "APPROVED" for row in required.values()):
        raise ValueError("A selected scientific dependency or its upstream basis is not currently approved")
    evidence = {row["evidence_id"]: row for row in context["evidence"] if row["evidence_id"] in payload.evidence_ids}
    if set(evidence) != set(payload.evidence_ids):
        raise ValueError("Selected Evidence must belong to this Track or its Field")
    for node_id in required:
        for row in conn.execute("SELECT e.* FROM evidence e JOIN node_evidence ne ON ne.evidence_id=e.evidence_id WHERE ne.node_id=?", (node_id,)):
            item = dict(row)
            if not evidence_is_available(conn, item):
                raise ValueError("The new scientific dependency still relies on a source requiring review")
    if any(not row["source_available"] for row in evidence.values()):
        raise ValueError("Selected Evidence still requires a new source review")
    sections = {node: section for section, nodes in payload.section_map.items() for node in nodes}
    if context["author_structure"] is not None and set(payload.section_map) - {section["id"] for section in context["author_structure"]["sections"]}:
        raise ValueError("Scientific section bindings must use this manuscript's real section IDs")
    return {"nodes": [{"manuscript_id": context["manuscript"]["manuscript_id"], "node_id": node_id,
                       "section": sections.get(node_id), "node_revision": selected[node_id]["revision"]} for node_id in sorted(selected)],
            "evidence": [{"manuscript_id": context["manuscript"]["manuscript_id"], "evidence_id": evidence_id,
                          "evidence_digest": evidence[evidence_id]["content_digest"]} for evidence_id in sorted(evidence)]}


class ManuscriptScientificReview:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def context(self, manuscript_id: str) -> dict:
        with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row;conn.execute("PRAGMA query_only=ON")
            result = scientific_context(conn, manuscript_id)
            result["reviews"] = [self._proposal(conn, row[0]) for row in conn.execute("SELECT review_id FROM manuscript_scientific_review_requests WHERE manuscript_id=? ORDER BY created_at,review_id", (manuscript_id,))]
            return result

    @staticmethod
    def _proposal(conn: sqlite3.Connection, review_id: str) -> dict:
        row = conn.execute("SELECT * FROM manuscript_scientific_review_requests WHERE review_id=?", (review_id,)).fetchone()
        if row is None:
            raise LookupError("Scientific review proposal not found")
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"));result["context"] = json.loads(result.pop("context_json"))
        event = conn.execute("SELECT * FROM manuscript_scientific_review_events WHERE review_id=?", (review_id,)).fetchone()
        result["status"] = "APPLIED" if event else "PROPOSED"
        result["approval_phrase"] = "APPROVE " + review_id
        result["event"] = {**dict(event), "before": json.loads(event["before_json"]), "after": json.loads(event["after_json"])} if event else None
        result["grant_available"] = bool(conn.execute("SELECT 1 FROM approval_grants WHERE proposal_id=? AND proposal_type='manuscript_scientific_review' AND proposal_revision=? AND consumed_at IS NULL", (review_id, result["expected_revision"])).fetchone())
        return result

    def propose(self, manuscript_id: str, payload: ScientificBindingReviewInput) -> dict:
        request_json = json.dumps({"manuscript_id": manuscript_id, **payload.model_dump()}, ensure_ascii=False, sort_keys=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT review_id,request_json FROM manuscript_scientific_review_requests WHERE request_id=?", (payload.request_id,)).fetchone()
            if prior:
                if prior["request_json"] != request_json:
                    raise ValueError("Scientific review request ID belongs to another binding proposal")
                return self._proposal(conn, prior["review_id"])
            context = scientific_context(conn, manuscript_id)
            if context["manuscript"]["revision"] != payload.expected_revision or context["context_sha256"] != payload.expected_context_sha256:
                raise ValueError("Scientific context changed; compare the current bindings before proposing")
            after = validate_binding(conn, context, payload)
            context["proposed_bindings"] = after
            review_id = stable_id("manuscript_review", payload.request_id)
            conn.execute("INSERT INTO manuscript_scientific_review_requests VALUES(?,?,?,?,?,?,?,?,?)", (review_id, payload.request_id, manuscript_id, context["manuscript"]["track_id"], payload.expected_revision,
                         request_json, json.dumps(context, ensure_ascii=False, sort_keys=True), payload.expected_context_sha256, utc_now()))
            return self._proposal(conn, review_id)

    def apply(self, manuscript_id: str, review_id: str) -> dict:
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            proposal = self._proposal(conn, review_id)
            if proposal["manuscript_id"] != manuscript_id:
                raise LookupError("Scientific review does not belong to this manuscript")
            if proposal["status"] == "APPLIED":
                return proposal
            current = scientific_context(conn, manuscript_id)
            if current["context_sha256"] != proposal["context_sha256"] or current["manuscript"]["revision"] != proposal["expected_revision"]:
                raise ValueError("Scientific source or binding changed after the proposed review; approval is not applied")
            request = ScientificBindingReviewInput.model_validate({k:v for k,v in proposal["request"].items() if k!='manuscript_id'})
            after = validate_binding(conn, current, request)
            grant = consume_grant(conn, proposal_id=review_id, proposal_type="manuscript_scientific_review", revision=proposal["expected_revision"])
            if grant["track_id"] != proposal["track_id"]:
                raise PermissionError("Scientific review approval belongs to another Track")
            if grant["profile"] not in {"scholar", "orchestrator"} or not grant["session_id"] or not grant["message_id"] or not grant["user_message_digest"]:
                raise PermissionError("Scientific review requires a recorded approval from the trusted user boundary")
            before = {"bindings": current["bindings"], "revision": current["manuscript"]["revision"],
                      "needs_scientific_review": current["manuscript"]["needs_scientific_review"]}
            conn.execute("DELETE FROM manuscript_nodes WHERE manuscript_id=?", (manuscript_id,))
            conn.execute("DELETE FROM manuscript_evidence WHERE manuscript_id=?", (manuscript_id,))
            for row in after["nodes"]:
                conn.execute("INSERT INTO manuscript_nodes VALUES(?,?,?,?)", (manuscript_id, row["node_id"], row["section"], row["node_revision"]))
            for row in after["evidence"]:
                conn.execute("INSERT INTO manuscript_evidence VALUES(?,?,?)", (manuscript_id, row["evidence_id"], row["evidence_digest"]))
            if bindings(conn, manuscript_id) != after:
                raise ValueError("Scientific binding projection did not match the confirmed proposal")
            now = utc_now();revision = current["manuscript"]["revision"]+1
            conn.execute("UPDATE manuscripts SET needs_scientific_review=0,revision=?,updated_at=? WHERE manuscript_id=? AND revision=?", (revision, now, manuscript_id, current["manuscript"]["revision"]))
            event_id = stable_id("manuscript_review_event", review_id)
            conn.execute("INSERT INTO manuscript_scientific_review_events VALUES(?,?,?,?,?,?,?)", (event_id, review_id, manuscript_id, grant["grant_id"],
                         json.dumps(before, ensure_ascii=False, sort_keys=True), json.dumps({"bindings": after, "revision": revision, "needs_scientific_review": 0}, ensure_ascii=False, sort_keys=True), now))
            return self._proposal(conn, review_id)
