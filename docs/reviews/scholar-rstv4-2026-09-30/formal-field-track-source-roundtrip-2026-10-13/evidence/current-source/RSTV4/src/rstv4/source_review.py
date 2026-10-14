"""Current source eligibility and auditable impacts without rewriting frozen evidence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def source_impact(conn: sqlite3.Connection, file: dict[str, Any]) -> dict[str, Any]:
    versions = []
    for row in conn.execute("SELECT * FROM paper_versions WHERE paper_id=? ORDER BY paper_version_id", (file["paper_id"],)):
        version = dict(row)
        source = json.loads(version["source_json"] or "{}")
        if source.get("file_version_id") == file["file_version_id"] or version["pdf_digest"] == file["sha256"]:
            versions.append(version)
    version_ids = {row["paper_version_id"] for row in versions}
    evidence = [dict(row) for row in conn.execute("SELECT * FROM evidence WHERE paper_id=? ORDER BY evidence_id", (file["paper_id"],))
                if row["paper_version_id"] in version_ids]
    evidence_ids = {row["evidence_id"] for row in evidence}
    roots = [dict(row) for row in conn.execute("SELECT DISTINCT n.* FROM research_nodes n JOIN node_evidence ne ON ne.node_id=n.node_id ORDER BY n.node_id")
             if conn.execute("SELECT 1 FROM node_evidence WHERE node_id=?", (row["node_id"],)).fetchone()
             and any(item[0] in evidence_ids for item in conn.execute("SELECT evidence_id FROM node_evidence WHERE node_id=?", (row["node_id"],)))]
    affected = {row["node_id"]: row for row in roots}
    queue = list(roots)
    while queue:
        node = queue.pop()
        for row in conn.execute("SELECT n.* FROM research_edges e JOIN research_nodes n ON n.node_id=e.target_node_id WHERE e.source_node_id=? AND e.track_id=? AND n.track_id=? ORDER BY n.node_id",
                                (node["node_id"], node["track_id"], node["track_id"])):
            if row["node_id"] not in affected:
                item = dict(row);affected[item["node_id"]] = item;queue.append(item)
    manuscripts = []
    for row in conn.execute("SELECT * FROM manuscripts ORDER BY manuscript_id"):
        node_match = any(item[0] in affected for item in conn.execute("SELECT node_id FROM manuscript_nodes WHERE manuscript_id=?", (row["manuscript_id"],)))
        evidence_match = any(item[0] in evidence_ids for item in conn.execute("SELECT evidence_id FROM manuscript_evidence WHERE manuscript_id=?", (row["manuscript_id"],)))
        if node_match or evidence_match:
            manuscripts.append(dict(row))
    snapshots = []
    for row in conn.execute("SELECT snapshot_id,field_id,version,build_id,content_digest FROM fieldkg_snapshots ORDER BY snapshot_id"):
        if any(item[0] in version_ids for item in conn.execute("SELECT paper_version_id FROM fieldkg_build_papers WHERE build_id=?", (row["build_id"],))):
            snapshots.append(dict(row))
    parse_ids = {row[0] for row in conn.execute("SELECT parse_run_id FROM parse_runs WHERE file_version_id=?", (file["file_version_id"],))}
    jobs = []
    for row in conn.execute("SELECT * FROM acquisition_jobs WHERE paper_id=? AND status NOT IN ('SUCCEEDED','SKIPPED','FAILED_TERMINAL') ORDER BY job_id", (file["paper_id"],)):
        job = dict(row);inputs = json.loads(job["input_json"]);review = json.loads(job.get("result_json") or "{}").get("review", {})
        if (inputs.get("file_version_id") == file["file_version_id"] or inputs.get("parse_run_id") in parse_ids
                or inputs.get("paper_version_id") in version_ids or review.get("file_version_id") == file["file_version_id"]):
            jobs.append(job)
    return {"paper_version_ids": sorted(version_ids), "evidence_ids": sorted(evidence_ids),
            "nodes": [affected[key] for key in sorted(affected)], "manuscripts": manuscripts,
            "snapshots": snapshots, "jobs": jobs}


def invalidate_source(conn: sqlite3.Connection, impact: dict[str, Any], file: dict[str, Any],
                      action_id: str, reason: str, now: str) -> dict[str, Any]:
    invalidated = []
    for node in impact["nodes"]:
        if node["status"] == "APPROVED":
            conn.execute("UPDATE research_nodes SET status='STALE',revision=revision+1,updated_at=? WHERE node_id=? AND revision=? AND status='APPROVED'",
                         (now, node["node_id"], node["revision"]))
            invalidated.append(node["node_id"])
    for manuscript in impact["manuscripts"]:
        conn.execute("UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=? WHERE manuscript_id=? AND revision=?",
                     (now, manuscript["manuscript_id"], manuscript["revision"]))
    stopped = []
    for job in impact["jobs"]:
        old = json.loads(job.get("result_json") or "{}")
        review = {"kind": "PDF_IDENTITY", "file_version_id": file["file_version_id"],
                  "pdf_sha256": file["sha256"], "source_withdrawal_action_id": action_id,
                  "previous_status": job["status"], "previous_result": old,
                  "previous_error_code": job["last_error_code"], "previous_error_detail": job["last_error_detail"]}
        conn.execute("UPDATE acquisition_jobs SET status='NEEDS_HUMAN',fencing_token=fencing_token+1,lease_owner=NULL,lease_expires_at=NULL,last_error_code='SOURCE_REVIEW_REOPENED',last_error_detail=?,result_json=?,updated_at=? WHERE job_id=? AND fencing_token=? AND updated_at=?",
                     (reason, json.dumps({"review": review}, ensure_ascii=False), now, job["job_id"], job["fencing_token"], job["updated_at"]))
        stopped.append(job["job_id"])
    return {"invalidated_nodes": invalidated, "affected_manuscripts": [row["manuscript_id"] for row in impact["manuscripts"]],
            "stopped_jobs": stopped, "retained_paper_versions": impact["paper_version_ids"],
            "retained_evidence": impact["evidence_ids"], "retained_snapshots": [row["snapshot_id"] for row in impact["snapshots"]]}


def source_is_available(conn: sqlite3.Connection, paper_version_id: str | None) -> bool:
    if paper_version_id is None:
        return True
    version = conn.execute("SELECT source_json,paper_id,pdf_digest FROM paper_versions WHERE paper_version_id=?", (paper_version_id,)).fetchone()
    if version is None:
        return False
    source = json.loads(version[0] or "{}")
    file_id = source.get("file_version_id")
    if file_id is None:
        known = conn.execute("SELECT identity_status FROM source_file_versions WHERE paper_id=? AND sha256=?", (version[1], version[2])).fetchall()
        return not known or all(row[0] == "VERIFIED" for row in known)
    file = conn.execute("SELECT identity_status FROM source_file_versions WHERE file_version_id=?", (file_id,)).fetchone()
    return file is not None and file[0] == "VERIFIED"


def current_source_reviews(conn: sqlite3.Connection, *, field_id: str | None = None,
                           track_id: str | None = None) -> list[dict[str, Any]]:
    result = []
    for row in conn.execute("SELECT action_id,case_id,file_version_id,reason,result_json,created_at FROM catalog_review_actions WHERE action_kind='REOPEN_IDENTITY' ORDER BY rowid DESC"):
        value = dict(row);impact = json.loads(value.pop("result_json"))
        manuscripts = impact.get("affected_manuscripts", [])
        snapshots = impact.get("retained_snapshots", [])
        track_match = track_id is not None and any(conn.execute("SELECT 1 FROM manuscripts WHERE manuscript_id=? AND track_id=?", (ms, track_id)).fetchone() for ms in manuscripts)
        field_match = field_id is not None and any(conn.execute("SELECT 1 FROM fieldkg_snapshots WHERE snapshot_id=? AND field_id=?", (snapshot, field_id)).fetchone() for snapshot in snapshots)
        if track_match or field_match:
            file = conn.execute("SELECT identity_status FROM source_file_versions WHERE file_version_id=?", (value["file_version_id"],)).fetchone()
            value["current_file_status"] = file[0] if file else "UNAVAILABLE"
            value["impact"] = impact;result.append(value)
    return result


def evidence_is_available(conn: sqlite3.Connection, evidence: dict[str, Any]) -> bool:
    if not source_is_available(conn, evidence["paper_version_id"]):
        return False
    for row in conn.execute("SELECT result_json FROM catalog_review_actions WHERE action_kind='REOPEN_IDENTITY'"):
        if evidence["evidence_id"] in json.loads(row[0]).get("retained_evidence", []):
            return False
    return True
