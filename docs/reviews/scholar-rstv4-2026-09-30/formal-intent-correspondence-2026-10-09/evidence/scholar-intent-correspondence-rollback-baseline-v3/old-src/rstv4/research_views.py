"""Read-only, ownership-scoped FieldKG and Track work surfaces."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .fieldkg import digest
from .fieldkg_semantics import semantic_objects, semantic_runs
from .research_workspace import WorkspaceError, metadata_digest
from .skeleton_intent import intent_coverage
from .skeleton_outline import read_source_outline
from .source_review import current_source_reviews


def rows(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params)]


def require(conn: sqlite3.Connection, kind: str, object_id: str) -> dict[str, Any]:
    table, column = {
        "field": ("research_fields", "field_id"), "track": ("research_tracks", "track_id"),
        "build": ("fieldkg_builds", "build_id"), "snapshot": ("fieldkg_snapshots", "snapshot_id"),
        "candidate": ("fieldkg_evidence_candidates", "candidate_id"),
        "gap": ("fieldkg_candidate_gaps", "candidate_gap_id"),
    }[kind]
    record = conn.execute(f"SELECT * FROM {table} WHERE {column}=?", (object_id,)).fetchone()
    if record is None:
        raise WorkspaceError(404, f"Unknown {kind}")
    return dict(record)


def parse_record(row: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for name, value in row.items():
        if name.endswith("_json"):
            result[name.removesuffix("_json")] = json.loads(value) if value else None
        else:
            result[name] = value
    return result


def skeleton_source(conn: sqlite3.Connection, skeleton_id: str) -> dict[str, Any]:
    source = conn.execute(
        """SELECT ps.*,pv.paper_id,pv.version AS paper_version,pv.pdf_digest,pv.parsed_digest,
           pv.source_json,p.title,p.doi FROM paper_skeletons ps
           JOIN paper_versions pv ON pv.paper_version_id=ps.paper_version_id
           JOIN papers p ON p.paper_id=pv.paper_id WHERE ps.skeleton_id=?""", (skeleton_id,),
    ).fetchone()
    if source is None:
        raise WorkspaceError(404, "Unknown PaperSkeleton")
    result = parse_record(dict(source))
    # Old bridge records do not prove a parse_run/file_version identity. Keep unknowns explicit.
    result["file_version_id"] = (result.get("source") or {}).get("file_version_id")
    result["parse_run_id"] = (result.get("source") or {}).get("parse_run_id")
    result.pop("source", None)
    result["units"] = [parse_record(row) for row in rows(
        conn, "SELECT * FROM skeleton_units WHERE skeleton_id=? ORDER BY seq_idx,unit_id",
        (skeleton_id,),
    )]
    result["triplets"] = rows(
        conn, """SELECT st.* FROM skeleton_triplets st JOIN skeleton_units su ON su.unit_id=st.unit_id
                 WHERE su.skeleton_id=? ORDER BY su.seq_idx,st.triplet_id""", (skeleton_id,),
    )
    outline = read_source_outline(conn, result)
    if outline is not None:
        result["source_outline"] = outline
    result["context_sha256"] = digest(result)
    return result


def available_skeletons(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [skeleton_source(conn, row[0]) for row in conn.execute(
        "SELECT skeleton_id FROM paper_skeletons ORDER BY created_at DESC,skeleton_id"
    )]


def build_context(conn: sqlite3.Connection, build_id: str) -> dict[str, Any]:
    build = parse_record(require(conn, "build", build_id))
    build["papers"] = rows(conn, "SELECT * FROM fieldkg_build_papers WHERE build_id=? ORDER BY paper_version_id", (build_id,))
    build["evidence_candidates"] = rows(conn, "SELECT * FROM fieldkg_evidence_candidates WHERE build_id=? ORDER BY candidate_id", (build_id,))
    build["candidate_gaps"] = rows(conn, "SELECT * FROM fieldkg_candidate_gaps WHERE build_id=? ORDER BY candidate_gap_id", (build_id,))
    build["gap_contexts"] = [candidate_context(conn, "gap", row["candidate_gap_id"]) for row in build["candidate_gaps"]]
    build["sources"] = [skeleton_source(conn, paper["skeleton_id"]) for paper in build["papers"] if paper["skeleton_id"]]
    build["semantic_coverage"] = intent_coverage(build["sources"])
    build["semantic_objects"] = semantic_objects(conn,build['field_id'],build_id)
    build["semantic_runs"] = semantic_runs(conn,build['field_id'],build_id)
    build["context_sha256"] = digest(build)
    return build


def candidate_context(conn: sqlite3.Connection, kind: str, object_id: str) -> dict[str, Any]:
    record = require(conn, kind, object_id)
    build = require(conn, "build", record["build_id"])
    if record["field_id"] != build["field_id"]:
        raise WorkspaceError(409, "Candidate and Build ownership do not match")
    context: dict[str, Any] = {"record": record, "build": build}
    if kind == "candidate":
        unit = conn.execute("SELECT skeleton_id FROM skeleton_units WHERE unit_id=?", (record["unit_id"],)).fetchone()
        if unit is None:
            raise WorkspaceError(409, "Candidate source is missing")
        source = skeleton_source(conn, unit[0])
        if not conn.execute(
            "SELECT 1 FROM fieldkg_build_papers WHERE build_id=? AND skeleton_id=?",
            (record["build_id"], unit[0]),
        ).fetchone():
            raise WorkspaceError(409, "Candidate source does not belong to this Build")
        context["source"] = source
    else:
        context["references"] = []
        for reference_id in json.loads(record["evidence_ids_json"]) + json.loads(record["counterevidence_ids_json"]):
            candidate = conn.execute("SELECT * FROM fieldkg_evidence_candidates WHERE candidate_id=?", (reference_id,)).fetchone()
            evidence = conn.execute("SELECT * FROM evidence WHERE evidence_id=?", (reference_id,)).fetchone()
            if candidate is not None and candidate["field_id"] == record["field_id"]:
                original = candidate_context(conn, "candidate", reference_id)
                context["references"].append({"kind": "candidate", **original})
            elif evidence is not None and evidence["field_id"] == record["field_id"] and evidence["scope_kind"] == "FIELDKG":
                context["references"].append({"kind": "evidence", "record": dict(evidence)})
            else:
                context["references"].append({"kind": "unavailable", "id": reference_id})
    context["context_sha256"] = digest(context)
    return context


def track_context(conn: sqlite3.Connection, track_id: str) -> dict[str, Any]:
    track = require(conn, "track", track_id)
    track["metadata_digest"] = metadata_digest(conn, "track", track)
    result = {"track": track,
              "adoptions": rows(conn, "SELECT * FROM track_snapshot_adoptions WHERE track_id=? ORDER BY adoption_id", (track_id,)),
              "nodes": rows(conn, "SELECT * FROM research_nodes WHERE track_id=? ORDER BY node_id", (track_id,)),
              "milestones": rows(conn, "SELECT * FROM track_milestones WHERE track_id=? ORDER BY milestone", (track_id,))}
    result["context_sha256"] = digest(result)
    return result


def snapshot_view(conn: sqlite3.Connection, field_id: str, snapshot_id: str) -> dict[str, Any]:
    snapshot = require(conn, "snapshot", snapshot_id)
    if snapshot["field_id"] != field_id:
        raise WorkspaceError(404, "Snapshot does not belong to this Field")
    manifest = json.loads(snapshot.pop("manifest_json"))
    snapshot["manifest"] = manifest
    snapshot["digest_matches"] = digest(manifest) == snapshot["content_digest"]
    snapshot["members"] = rows(conn, "SELECT * FROM fieldkg_snapshot_members WHERE snapshot_id=? ORDER BY member_type,member_id", (snapshot_id,))
    expected = sorted((kind, row[key], row["digest"]) for kind, key, records in [
        ("EVIDENCE", "evidence_id", manifest.get("evidence", [])),
        ("CANDIDATE_GAP", "candidate_gap_id", manifest.get("candidate_gaps", [])),
        ("SEMANTIC_OBJECT", "object_id", manifest.get("semantic_objects", [])),
    ] for row in records)
    actual = sorted((row["member_type"], row["member_id"], row["member_digest"]) for row in snapshot["members"])
    snapshot["members_match"] = actual == expected
    snapshot["adoptions"] = rows(conn, """SELECT a.*,t.title FROM track_snapshot_adoptions a
        JOIN research_tracks t ON t.track_id=a.track_id WHERE a.snapshot_id=? ORDER BY a.adopted_at""", (snapshot_id,))
    # New snapshots hold their original source records. Legacy manifests keep explicit limitations.
    snapshot["sources"] = manifest.get("source_records", [])
    snapshot["frozen_evidence"] = manifest.get("frozen_evidence", [])
    snapshot["frozen_candidate_gaps"] = manifest.get("frozen_candidate_gaps", [])
    snapshot["frozen_semantic_objects"] = manifest.get("frozen_semantic_objects", [])
    declared={row['object_id']:row['digest'] for row in manifest.get('semantic_objects',[])}
    frozen=snapshot['frozen_semantic_objects']
    snapshot['members_match']=snapshot['members_match'] and (
        len(frozen)==len(declared) and all(obj['object_id'] in declared and digest(obj)==declared[obj['object_id']] for obj in frozen)
    )
    snapshot["source_records_available"] = "source_records" in manifest
    return snapshot


def field_workspace(conn: sqlite3.Connection, field_id: str, snapshot_id: str | None = None) -> dict[str, Any]:
    field = require(conn, "field", field_id)
    builds = [build_context(conn, row[0]) for row in conn.execute(
        "SELECT build_id FROM fieldkg_builds WHERE field_id=? ORDER BY created_at DESC,build_id", (field_id,),
    )]
    sources = {source["skeleton_id"]: source for build in builds for source in build["sources"]}
    evidence = [parse_record(row) for row in rows(conn, "SELECT * FROM evidence WHERE scope_kind='FIELDKG' AND field_id=? ORDER BY created_at,evidence_id", (field_id,))]
    candidates = [candidate_context(conn, "candidate", row[0]) for row in conn.execute(
        "SELECT candidate_id FROM fieldkg_evidence_candidates WHERE field_id=? ORDER BY created_at,candidate_id", (field_id,),
    )]
    gaps = [candidate_context(conn, "gap", row[0]) for row in conn.execute(
        "SELECT candidate_gap_id FROM fieldkg_candidate_gaps WHERE field_id=? ORDER BY created_at,candidate_gap_id", (field_id,),
    )]
    versions = rows(conn, "SELECT snapshot_id,field_id,version,build_id,status,content_digest,mapping_status,created_at FROM fieldkg_snapshots WHERE field_id=? ORDER BY version DESC", (field_id,))
    outbox = rows(conn, "SELECT job_id,aggregate_type,aggregate_id,status,attempts,last_error,created_at,updated_at FROM projection_outbox WHERE field_id=? ORDER BY created_at", (field_id,))
    tracks = [track_context(conn, row[0]) for row in conn.execute("SELECT track_id FROM research_tracks WHERE field_id=? ORDER BY title,track_id", (field_id,))]
    result = {"field": field, "topics": rows(conn, "SELECT t.* FROM topics t JOIN field_topics ft ON ft.topic_id=t.topic_id WHERE ft.field_id=? ORDER BY t.name", (field_id,)),
              "tracks": tracks, "builds": builds, "sources": list(sources.values()),
              "evidence": evidence, "candidates": candidates, "candidate_gaps": gaps,
              "semantic_objects": semantic_objects(conn,field_id),
              "semantic_runs": semantic_runs(conn,field_id),
              "snapshots": versions, "projection": {"outbox": outbox, "live_service_health": "NOT_PROBED"},
              "selected_snapshot": snapshot_view(conn, field_id, snapshot_id) if snapshot_id else None}
    paper_ids = {source["paper_id"] for source in sources.values()}
    # A normal Field query may not introduce an unseen paper from another Field through an edge.
    result["citations"] = [row for row in rows(conn, "SELECT * FROM citation_observations ORDER BY citation_id") if row["citing_paper_id"] in paper_ids and row["cited_paper_id"] in paper_ids]
    result["source_reviews"] = current_source_reviews(conn, field_id=field_id)
    result["context_sha256"] = digest(result)
    return result


def track_workspace(conn: sqlite3.Connection, track_id: str) -> dict[str, Any]:
    result = track_context(conn, track_id)
    track = result["track"]
    result["field"] = require(conn, "field", track["field_id"]) if track["field_id"] else None
    result["topics"] = rows(conn, "SELECT t.*,tt.role FROM topics t JOIN track_topics tt ON tt.topic_id=t.topic_id WHERE tt.track_id=? ORDER BY tt.role,t.name", (track_id,))
    result["nodes"] = [parse_record(row) for row in result["nodes"]]
    result["edges"] = rows(conn, """SELECT e.* FROM research_edges e
        JOIN research_nodes s ON s.node_id=e.source_node_id
        JOIN research_nodes t ON t.node_id=e.target_node_id
        WHERE e.track_id=? AND s.track_id=? AND t.track_id=? ORDER BY e.edge_id""", (track_id, track_id, track_id))
    result["decisions"] = rows(conn, "SELECT * FROM decisions WHERE track_id=? ORDER BY created_at,proposal_id", (track_id,))
    result["projects"] = [parse_record(row) for row in rows(conn, "SELECT * FROM projects WHERE track_id=? ORDER BY created_at,project_id", (track_id,))]
    result["plans"] = [parse_record(row) for row in rows(conn, "SELECT * FROM experiment_plans WHERE track_id=? ORDER BY created_at,plan_id", (track_id,))]
    result["runs"] = [parse_record(row) for row in rows(conn, "SELECT * FROM pipeline_runs WHERE track_id=? ORDER BY created_at,run_id", (track_id,))]
    result["evidence"] = [parse_record(row) for row in rows(conn, """SELECT DISTINCT e.* FROM evidence e
        LEFT JOIN node_evidence ne ON ne.evidence_id=e.evidence_id LEFT JOIN research_nodes n ON n.node_id=ne.node_id
        WHERE (e.scope_kind='TRACK' AND e.track_id=?) OR (n.track_id=? AND e.scope_kind='FIELDKG' AND e.field_id=?) ORDER BY e.created_at,e.evidence_id""", (track_id, track_id, track["field_id"]))]
    result["node_evidence"] = rows(conn, "SELECT ne.* FROM node_evidence ne JOIN research_nodes n ON n.node_id=ne.node_id WHERE n.track_id=?", (track_id,))
    result["adopted_snapshots"] = [snapshot_view(conn, track["field_id"], adoption["snapshot_id"]) for adoption in result["adoptions"]]
    result["available_snapshots"] = rows(conn, "SELECT snapshot_id,version,status,content_digest,created_at FROM fieldkg_snapshots WHERE field_id=? ORDER BY version DESC", (track["field_id"],))
    result["manuscripts"] = rows(conn, "SELECT * FROM manuscripts WHERE track_id=? ORDER BY created_at,manuscript_id", (track_id,))
    result["manuscript_projects"] = rows(conn, "SELECT mp.* FROM manuscript_projects mp JOIN manuscripts m ON m.manuscript_id=mp.manuscript_id JOIN projects p ON p.project_id=mp.project_id WHERE m.track_id=? AND p.track_id=?", (track_id, track_id))
    result["submission_events"] = rows(conn, "SELECT se.* FROM submission_events se JOIN manuscripts m ON m.manuscript_id=se.manuscript_id WHERE m.track_id=? ORDER BY se.created_at,se.event_id", (track_id,))
    result["source_reviews"] = current_source_reviews(conn, track_id=track_id)
    # Keep the original adoption CAS context separate from the richer display response.
    return result
