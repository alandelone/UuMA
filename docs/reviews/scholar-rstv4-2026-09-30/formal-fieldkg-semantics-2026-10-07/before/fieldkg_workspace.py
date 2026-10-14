"""Explicit FieldKG review/seal/adoption actions with atomic, replayable receipts."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from .database import WORKSPACE_ACTION_SCHEMA
from .fieldkg import EVIDENCE_INTENTS, digest, stable_id
from .models import StrictModel, new_id
from .research_views import (
    build_context,
    candidate_context,
    require,
    skeleton_source,
    snapshot_view,
    track_context,
)
from .research_workspace import WorkspaceError
from .source_review import evidence_is_available, source_is_available


class ConfirmedAction(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    field_id: str
    confirmed: Literal[True]


class CreateBuild(ConfirmedAction):
    operation: Literal["CREATE_BUILD"]
    sources: dict[str, str] = Field(min_length=1, max_length=500)


class ReviewCandidate(ConfirmedAction):
    operation: Literal["REVIEW_CANDIDATE", "REVIEW_GAP"]
    object_id: str
    expected_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["ACCEPTED", "REJECTED"]
    rationale: str = Field(min_length=1, max_length=8000)


class BuildAction(ConfirmedAction):
    operation: Literal["READY_BUILD", "SEAL_SNAPSHOT"]
    build_id: str
    expected_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdoptSnapshot(ConfirmedAction):
    operation: Literal["ADOPT_SNAPSHOT"]
    track_id: str
    snapshot_id: str
    expected_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


FieldKGAction = Annotated[CreateBuild | ReviewCandidate | BuildAction | AdoptSnapshot,
                          Field(discriminator="operation")]


def _owned(record: dict, field_id: str) -> None:
    if record["field_id"] != field_id:
        raise WorkspaceError(404, "Object does not belong to this Field")


def _current(context: dict, expected: str) -> None:
    if context["context_sha256"] != expected:
        raise WorkspaceError(409, "The record or its sources changed. Refresh and compare again.")


def _enqueue(conn: sqlite3.Connection, kind: str, object_id: str, field_id: str,
             payload: dict, now: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO projection_outbox VALUES(?,?,?,?,?,?,'PENDING',0,NULL,?,?)",
        (stable_id("projection", kind, object_id, "UPSERT", digest(payload)), kind, object_id,
         field_id, "UPSERT", json.dumps(payload, ensure_ascii=False), now, now),
    )


def _create_build(conn: sqlite3.Connection, action: CreateBuild, now: str) -> dict:
    sources = []
    for skeleton_id, expected in action.sources.items():
        source = skeleton_source(conn, skeleton_id)
        _current(source, expected)
        if not source["units"]:
            raise WorkspaceError(422, "A selected PaperSkeleton has no source units")
        sources.append(source)
    build_id = new_id("fieldkg_build")
    scope = {"source": "EXISTING_PAPERSKELETON", "selected_skeletons": list(action.sources),
             "paper_ids": sorted({source["paper_id"] for source in sources})}
    conn.execute("INSERT INTO fieldkg_builds VALUES(?,?,'EXTRACTING_EVIDENCE',?,1,?,?)",
                 (build_id, action.field_id, json.dumps(scope), now, now))
    for source in sources:
        if any(item["paper_version_id"] == source["paper_version_id"] for item in sources
               if item["skeleton_id"] != source["skeleton_id"]):
            raise WorkspaceError(422, "Select one PaperSkeleton version per PaperVersion")
        conn.execute("INSERT INTO fieldkg_build_papers VALUES(?,?,?,'IMPORTED',NULL)",
                     (build_id, source["paper_version_id"], source["skeleton_id"]))
        for unit in source["units"]:
            intent = str((unit["layer3"] or {}).get("intent") or "").removeprefix("[Intent: ").removesuffix("]")
            if intent not in EVIDENCE_INTENTS:
                continue
            statement = str((unit["layer1"] or {}).get("coref_resolved") or unit["raw_text"])
            candidate_id = stable_id("evidence_candidate", build_id, unit["unit_id"], statement)
            relation = "CONTEXTUALIZES" if intent in {"Research_Gap", "Future_Work", "Boundary_Condition", "Critical_Evaluation"} else "SUPPORTS"
            confidence = float((unit["layer3"] or {}).get("confidence") or 0)
            if not 0 <= confidence <= 1:
                raise WorkspaceError(422, "Source candidate confidence is outside 0..1")
            conn.execute("INSERT INTO fieldkg_evidence_candidates VALUES(?,?,?,?,?,?,?,?, 'PROPOSED',NULL,1,?,NULL)",
                         (candidate_id, build_id, action.field_id, unit["unit_id"], statement,
                          unit["raw_text"], relation, confidence, now))
            if intent == "Research_Gap":
                gap_id = stable_id("candidate_gap", build_id, unit["unit_id"], statement)
                conn.execute("INSERT INTO fieldkg_candidate_gaps VALUES(?,?,?,?,?,?,?,?,?,?,'PROPOSED',1,?,NULL)",
                             (gap_id, build_id, action.field_id, statement,
                              "Reported gap in the selected source; not an approved scientific Gap.",
                              json.dumps([candidate_id]), "[]", "[]", source["extractor_model"],
                              source["prompt_version"], now))
    return {"object_type": "build", "object_id": build_id, "build": build_context(conn, build_id)}


def _review(conn: sqlite3.Connection, action: ReviewCandidate, now: str) -> dict:
    kind = "candidate" if action.operation == "REVIEW_CANDIDATE" else "gap"
    context = candidate_context(conn, kind, action.object_id)
    record, build = context["record"], context["build"]
    _owned(record, action.field_id)
    _current(context, action.expected_context_sha256)
    if record["status"] != "PROPOSED" or build["status"] == "SEALED":
        raise WorkspaceError(409, "This candidate is already reviewed or its Build is sealed")
    if kind == "gap" and action.decision == "ACCEPTED":
        for reference in context["references"]:
            target = reference.get("record")
            if target is None or target["field_id"] != action.field_id:
                raise WorkspaceError(422, "Gap evidence is unavailable or belongs to another Field")
            if reference["kind"] == "candidate" and target["status"] != "ACCEPTED":
                raise WorkspaceError(422, "Review the Gap's evidence candidates before accepting it")
    if kind == "candidate":
        conn.execute("UPDATE fieldkg_evidence_candidates SET status=?,rationale=?,revision=revision+1,reviewed_at=? WHERE candidate_id=?",
                     (action.decision, action.rationale, now, action.object_id))
        if action.decision == "ACCEPTED":
            source = context["source"]
            if not source_is_available(conn, source["paper_version_id"]):
                raise WorkspaceError(409, "Original file identity requires review before accepting its Evidence")
            unit = next(unit for unit in source["units"] if unit["unit_id"] == record["unit_id"])
            expected_statement = str((unit["layer1"] or {}).get("coref_resolved") or unit["raw_text"])
            if record["excerpt"] != unit["raw_text"] or record["statement"] != expected_statement:
                raise WorkspaceError(409, "Candidate no longer matches its original source text")
            location = {"unit_id": unit["unit_id"], "page": unit["page_idx"], "section": unit["section"],
                        "sequence": unit["seq_idx"], "skeleton_id": source["skeleton_id"],
                        "skeleton_digest": source["content_digest"], "unit_digest": unit["content_digest"]}
            evidence_id = stable_id("evidence", action.object_id, record["statement"])
            evidence_digest = digest([record["statement"], record["excerpt"], location])
            conn.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (evidence_id, "FIELDKG", action.field_id, None, source["paper_id"],
                          source["paper_version_id"], None, record["statement"], record["excerpt"],
                          json.dumps(location), record["relation"], record["confidence"],
                          source["extractor_model"], source["prompt_version"], evidence_digest, now))
            _enqueue(conn, "Evidence", evidence_id, action.field_id,
                     {"statement": record["statement"], "excerpt": record["excerpt"],
                      "location": location, "content_digest": evidence_digest}, now)
    else:
        # Keep the source rationale; the review reason is saved in the immutable action receipt.
        conn.execute("UPDATE fieldkg_candidate_gaps SET status=?,revision=revision+1,reviewed_at=? WHERE candidate_gap_id=?",
                     (action.decision, now, action.object_id))
        if action.decision == "ACCEPTED":
            _enqueue(conn, "CandidateGap", action.object_id, action.field_id,
                     require(conn, "gap", action.object_id), now)
    return {"object_type": kind, "object_id": action.object_id,
            "review": candidate_context(conn, kind, action.object_id)}


def _reviewed_evidence(conn: sqlite3.Connection, candidate: dict, field_id: str) -> dict:
    current = candidate_context(conn, "candidate", candidate["candidate_id"])
    _owned(candidate, field_id)
    if candidate["status"] != "ACCEPTED":
        raise WorkspaceError(422, "Referenced evidence candidate is not accepted")
    evidence_id = stable_id("evidence", candidate["candidate_id"], candidate["statement"])
    row = conn.execute("SELECT * FROM evidence WHERE evidence_id=? AND field_id=? AND scope_kind='FIELDKG'", (evidence_id, field_id)).fetchone()
    if row is None:
        raise WorkspaceError(422, "Accepted candidate has no matching evidence record")
    source = current["source"]
    unit = next(item for item in source["units"] if item["unit_id"] == candidate["unit_id"])
    location = json.loads(row["location_json"])
    expected_statement = str((unit["layer1"] or {}).get("coref_resolved") or unit["raw_text"])
    if (row["statement"] != candidate["statement"] or row["excerpt"] != candidate["excerpt"]
            or candidate["statement"] != expected_statement or candidate["excerpt"] != unit["raw_text"]
            or row["paper_id"] != source["paper_id"] or row["paper_version_id"] != source["paper_version_id"]
            or location.get("unit_id") != unit["unit_id"] or location.get("skeleton_id") != source["skeleton_id"]
            or location.get("unit_digest") != unit["content_digest"]
            or row["content_digest"] != digest([row["statement"], row["excerpt"], location])):
        raise WorkspaceError(409, "Accepted evidence no longer matches its reviewed source")
    return dict(row)


def _build_action(conn: sqlite3.Connection, action: BuildAction, now: str) -> dict:
    build = build_context(conn, action.build_id)
    _owned(build, action.field_id)
    _current(build, action.expected_context_sha256)
    if build["status"] == "SEALED":
        raise WorkspaceError(409, "This Build is already sealed")
    if not build["papers"] or len(build["sources"]) != len(build["papers"]) or any(
        paper["status"] != "IMPORTED" for paper in build["papers"]
    ):
        raise WorkspaceError(422, "Build has missing or failed source artifacts")
    if action.operation == "READY_BUILD":
        conn.execute("UPDATE fieldkg_builds SET status='READY_FOR_REVIEW',revision=revision+1,updated_at=? WHERE build_id=?", (now, action.build_id))
        return {"object_type": "build", "object_id": action.build_id,
                "build": build_context(conn, action.build_id)}
    if build["status"] != "READY_FOR_REVIEW":
        raise WorkspaceError(409, "Mark the Build ready for review before sealing")
    if not build["semantic_coverage"]["complete"]:
        raise WorkspaceError(422, "Build has source units without structured Intent; explicitly reread the source before sealing")
    if any(row["status"] == "PROPOSED" for row in build["evidence_candidates"] + build["candidate_gaps"]):
        raise WorkspaceError(422, "Review every evidence and Gap candidate before sealing")
    evidence = []
    for candidate in build["evidence_candidates"]:
        if candidate["status"] != "ACCEPTED":
            continue
        evidence.append(_reviewed_evidence(conn, candidate, action.field_id))
    gaps = [row for row in build["candidate_gaps"] if row["status"] == "ACCEPTED"]
    gap_references = {}
    for gap in gaps:
        context = candidate_context(conn, "gap", gap["candidate_gap_id"])
        for reference in context["references"]:
            if reference["kind"] == "unavailable":
                raise WorkspaceError(422, "Gap evidence is unavailable or outside this Field")
            if reference["kind"] == "candidate":
                reference["accepted_evidence"] = _reviewed_evidence(conn, reference["record"], action.field_id)
            else:
                row = reference["record"]
                if row["content_digest"] != digest([row["statement"], row["excerpt"], json.loads(row["location_json"])]):
                    raise WorkspaceError(409, "Referenced Gap evidence changed")
        gap_references[gap["candidate_gap_id"]] = context["references"]
    paper_ids = {source["paper_id"] for source in build["sources"]}
    citations = [dict(row) for row in conn.execute("SELECT * FROM citation_observations ORDER BY citation_id")
                 if row["citing_paper_id"] in paper_ids and row["cited_paper_id"] in paper_ids]
    manifest = {"field_id": action.field_id, "build_id": action.build_id, "papers": build["papers"],
                "evidence": [{"evidence_id": row["evidence_id"], "digest": row["content_digest"]} for row in evidence],
                "candidate_gaps": [{"candidate_gap_id": row["candidate_gap_id"], "digest": digest(row)} for row in gaps],
                "source_records": build["sources"], "frozen_evidence": evidence,
                "frozen_candidate_gaps": gaps, "reviewed_candidates": build["evidence_candidates"],
                "gap_references": gap_references, "citations": citations}
    snapshot_id = new_id("fieldkg_snapshot")
    version = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM fieldkg_snapshots WHERE field_id=?", (action.field_id,)).fetchone()[0]
    conn.execute("INSERT INTO fieldkg_snapshots VALUES(?,?,?,?,'SEALED',?,?,'MAPPED',?)",
                 (snapshot_id, action.field_id, version, action.build_id,
                  json.dumps(manifest, ensure_ascii=False), digest(manifest), now))
    for kind, records, id_name in [("EVIDENCE", manifest["evidence"], "evidence_id"),
                                   ("CANDIDATE_GAP", manifest["candidate_gaps"], "candidate_gap_id")]:
        for row in records:
            conn.execute("INSERT INTO fieldkg_snapshot_members VALUES(?,?,?,?)", (snapshot_id, kind, row[id_name], row["digest"]))
    conn.execute("UPDATE fieldkg_builds SET status='SEALED',revision=revision+1,updated_at=? WHERE build_id=?", (now, action.build_id))
    _enqueue(conn, "FieldKGSnapshot", snapshot_id, action.field_id, manifest, now)
    return {"object_type": "snapshot", "object_id": snapshot_id,
            "snapshot": require(conn, "snapshot", snapshot_id)}


def _adopt(conn: sqlite3.Connection, action: AdoptSnapshot, now: str) -> dict:
    context = track_context(conn, action.track_id)
    _owned(context["track"], action.field_id)
    _current(context, action.expected_context_sha256)
    snapshot = require(conn, "snapshot", action.snapshot_id)
    _owned(snapshot, action.field_id)
    if snapshot["status"] != "SEALED" or snapshot["content_digest"] != action.expected_snapshot_digest or digest(json.loads(snapshot["manifest_json"])) != snapshot["content_digest"]:
        raise WorkspaceError(409, "Snapshot is not sealed or its fixed content changed")
    fixed = snapshot_view(conn, action.field_id, action.snapshot_id)
    for source in fixed["sources"]:
        if not source_is_available(conn, source.get("paper_version_id")):
            raise WorkspaceError(409, "Snapshot source file is under review")
    for frozen in fixed["frozen_evidence"]:
        if not evidence_is_available(conn, frozen):
            raise WorkspaceError(409, "Snapshot Evidence requires a new source review")
    if not fixed["members_match"]:
        raise WorkspaceError(409, "Snapshot members no longer match its fixed manifest")
    adoption_id = stable_id("adoption", action.track_id, action.snapshot_id)
    conn.execute("INSERT OR IGNORE INTO track_snapshot_adoptions VALUES(?,?,?,?,?)",
                 (adoption_id, action.track_id, action.snapshot_id, snapshot["content_digest"], now))
    adoption = dict(conn.execute("SELECT * FROM track_snapshot_adoptions WHERE adoption_id=?", (adoption_id,)).fetchone())
    if adoption["snapshot_digest"] != snapshot["content_digest"]:
        raise WorkspaceError(409, "Existing adoption points to different snapshot content")
    return {"object_type": "adoption", "object_id": adoption_id, "adoption": adoption}


def record_fieldkg_action(path: Path, action: FieldKGAction) -> dict[str, Any]:
    if not path.is_file():
        raise WorkspaceError(503, "Catalog database is unavailable")
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for statement in WORKSPACE_ACTION_SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        request_json = json.dumps(action.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        old = conn.execute("SELECT request_json,result_json FROM research_workspace_actions WHERE request_id=?", (action.request_id,)).fetchone()
        if old:
            if old["request_json"] != request_json:
                raise WorkspaceError(409, "This request ID was used for a different action")
            conn.rollback()
            return json.loads(old["result_json"])
        require(conn, "field", action.field_id)
        now = datetime.now(UTC).isoformat()
        if isinstance(action, CreateBuild):
            result = _create_build(conn, action, now)
        elif isinstance(action, ReviewCandidate):
            result = _review(conn, action, now)
        elif isinstance(action, BuildAction):
            result = _build_action(conn, action, now)
        else:
            result = _adopt(conn, action, now)
        result.update(operation=action.operation, request_id=action.request_id, field_id=action.field_id)
        conn.execute("INSERT INTO research_workspace_actions(request_id,request_json,object_type,object_id,result_json,created_at) VALUES(?,?,?,?,?,?)",
                     (action.request_id, request_json, result["object_type"], result["object_id"],
                      json.dumps(result, ensure_ascii=False), now))
        conn.commit()
        return result
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
