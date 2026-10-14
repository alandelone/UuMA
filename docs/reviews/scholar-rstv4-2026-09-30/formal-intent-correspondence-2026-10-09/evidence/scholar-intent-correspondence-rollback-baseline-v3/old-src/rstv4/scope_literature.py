"""Read-only literature unions with explicit association provenance, never scientific approval."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .acquisition import AcquisitionService
from .fieldkg import digest
from .research_workspace import WorkspaceError


class LiteratureScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["field", "topic", "track", "question"]
    field_id: str
    object_id: str
    include_excluded: bool = False


class ScopeLiteratureIndex:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.fields = {row["field_id"]: dict(row) for row in conn.execute("SELECT * FROM research_fields")}
        self.topics = {row["topic_id"]: dict(row) for row in conn.execute("SELECT * FROM topics")}
        self.field_topics = {(row[0], row[1]) for row in conn.execute("SELECT field_id,topic_id FROM field_topics")}
        self.tracks = {row["track_id"]: dict(row) for row in conn.execute("SELECT * FROM research_tracks")}
        self.questions = {row["node_id"]: dict(row) for row in conn.execute("SELECT * FROM research_nodes WHERE lower(node_type)='research_question'")}
        self.track_topics: dict[str, set[str]] = defaultdict(set)
        for row in conn.execute("SELECT track_id,topic_id FROM track_topics"):
            self.track_topics[row[0]].add(row[1])
        for track in self.tracks.values():
            if track["primary_topic_id"]:
                self.track_topics[track["track_id"]].add(track["primary_topic_id"])
        self.visible = {row[0] for row in conn.execute("SELECT paper_id FROM papers WHERE NOT EXISTS(SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=papers.paper_id)")}
        self.links: dict[tuple[str, str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        self.unavailable: list[dict] = []
        screenings = {}
        for row in conn.execute("SELECT a.*,s.collection_id,s.context_sha256 FROM paper_assessments a JOIN screening_input_snapshots s ON s.assessment_id=a.assessment_id WHERE a.assessment_type='SCREEN' AND a.status='COMPLETED' ORDER BY a.created_at,a.rowid"):
            current = AcquisitionService._screening_context(conn, row["collection_id"], row["paper_id"])
            if digest(current) == row["context_sha256"]:
                screenings[row["collection_id"], row["paper_id"]] = {
                    "assessment_id": row["assessment_id"],
                    "category": json.loads(row["result_json"]).get("category", "UNKNOWN"),
                    "context_sha256": row["context_sha256"],
                }
        for raw in conn.execute("SELECT c.*,m.paper_id,m.discovery_kind,m.discovered_from_paper_id,m.status AS membership_status FROM collections c JOIN collection_memberships m ON m.collection_id=c.collection_id ORDER BY c.collection_id,m.paper_id"):
            row = dict(raw)
            screen = screenings.get((row["collection_id"], row["paper_id"]))
            reason = {"kind": "collection", "collection_id": row["collection_id"], "name": row["name"],
                      "discovery_kind": row["discovery_kind"], "membership_status": row["membership_status"],
                      "discovered_from_paper_id": row["discovered_from_paper_id"], "screening": screen,
                      "association_status": "CONFIRMED" if row["discovery_kind"] in {"CATALOG_SELECTION", "SEED"} else "CANDIDATE",
                      "excluded": bool(screen and screen["category"] == "IRRELEVANT")}
            self._add(row["paper_id"], row["field_id"], row["track_id"], row.get("topic_id"), reason)
        for row in conn.execute("SELECT b.field_id,b.build_id,bp.status,pv.paper_id,pv.paper_version_id,bp.skeleton_id FROM fieldkg_builds b JOIN fieldkg_build_papers bp ON bp.build_id=b.build_id JOIN paper_versions pv ON pv.paper_version_id=bp.paper_version_id WHERE bp.status='IMPORTED' ORDER BY b.build_id,pv.paper_id"):
            self._add(row["paper_id"], row["field_id"], None, None,
                      {"kind": "fieldkg_build", "build_id": row["build_id"], "paper_version_id": row["paper_version_id"],
                       "skeleton_id": row["skeleton_id"], "association_status": "CONFIRMED", "excluded": False})
        for raw in conn.execute("SELECT a.*,s.field_id,s.status,s.manifest_json,s.content_digest,s.version FROM track_snapshot_adoptions a JOIN fieldkg_snapshots s ON s.snapshot_id=a.snapshot_id ORDER BY a.adoption_id"):
            row = dict(raw)
            track = self.tracks.get(row["track_id"])
            manifest = json.loads(row["manifest_json"])
            valid = track and track["field_id"] == row["field_id"] and manifest.get("field_id") == row["field_id"] and row["status"] == "SEALED" and row["snapshot_digest"] == row["content_digest"] == digest(manifest)
            if not valid or "source_records" not in manifest:
                self.unavailable.append({"track_id": row["track_id"], "snapshot_id": row["snapshot_id"], "reason": "快照来源未保存或摘要／归属不符；未用 Living 替代。"})
                continue
            for source in manifest["source_records"]:
                self._add(source["paper_id"], row["field_id"], row["track_id"], None,
                          {"kind": "adopted_snapshot", "snapshot_id": row["snapshot_id"], "snapshot_version": row["version"],
                           "adoption_id": row["adoption_id"], "paper_version_id": source["paper_version_id"],
                           "skeleton_id": source["skeleton_id"], "association_status": "CONFIRMED", "excluded": False})
        for row in conn.execute("SELECT n.node_id,n.node_type,n.track_id,t.field_id,e.paper_id,e.evidence_id,e.scope_kind,e.track_id AS evidence_track,e.field_id AS evidence_field FROM node_evidence ne JOIN research_nodes n ON n.node_id=ne.node_id JOIN research_tracks t ON t.track_id=n.track_id JOIN evidence e ON e.evidence_id=ne.evidence_id ORDER BY n.node_id,e.evidence_id"):
            if not ((row["scope_kind"] == "TRACK" and row["evidence_track"] == row["track_id"]) or (row["scope_kind"] == "FIELDKG" and row["evidence_field"] == row["field_id"])):
                continue
            reason = {"kind": "node_evidence", "node_id": row["node_id"], "evidence_id": row["evidence_id"],
                      "association_status": "CONFIRMED", "excluded": False}
            self._add(row["paper_id"], row["field_id"], row["track_id"], None, reason)
            if row["node_type"].lower() == "research_question":
                self._store(("question", row["field_id"], row["node_id"]), row["paper_id"], reason)

    def _store(self, key: tuple[str, str, str], paper_id: str, reason: dict) -> None:
        if paper_id in self.visible:
            self.links[key][paper_id].append(reason)

    def _add(self, paper_id: str, field_id: str, track_id: str | None, topic_id: str | None, reason: dict) -> None:
        if field_id not in self.fields:
            return
        track = self.tracks.get(track_id or "")
        if track_id and (track is None or track["field_id"] != field_id):
            return
        reason = {**reason, "field_id": field_id, "track_id": track_id, "topic_id": topic_id}
        self._store(("field", field_id, field_id), paper_id, reason)
        if track_id:
            self._store(("track", field_id, track_id), paper_id, reason)
        topics = self.track_topics.get(track_id or "", set()) | ({topic_id} if topic_id else set())
        for topic in topics:
            if (field_id, topic) in self.field_topics:
                self._store(("topic", field_id, topic), paper_id, reason)

    def read(self, scope: LiteratureScope) -> dict:
        if scope.field_id not in self.fields:
            raise WorkspaceError(404, "Unknown Field")
        if scope.kind == "field":
            valid = scope.object_id == scope.field_id
            record = self.fields.get(scope.object_id)
        elif scope.kind == "topic":
            valid = (scope.field_id, scope.object_id) in self.field_topics
            record = self.topics.get(scope.object_id)
        else:
            record = (self.tracks if scope.kind == "track" else self.questions).get(scope.object_id)
            owner = record if scope.kind == "track" else self.tracks.get(record["track_id"]) if record else None
            valid = owner and owner["field_id"] == scope.field_id
        if not valid or record is None:
            raise WorkspaceError(404, "This object does not belong to the requested Field")
        associations = []
        excluded_count = 0
        for paper_id, reasons in sorted(self.links[scope.kind, scope.field_id, scope.object_id].items()):
            excluded = all(reason["excluded"] for reason in reasons)
            excluded_count += int(excluded)
            if excluded and not scope.include_excluded:
                continue
            included_reasons = [reason for reason in reasons if not reason["excluded"]]
            associations.append({"paper_id": paper_id, "excluded": excluded, "reasons": reasons,
                                 "association_status": "CONFIRMED" if any(reason["association_status"] == "CONFIRMED" for reason in included_reasons) else "CANDIDATE"})
        track_ids = {scope.object_id} if scope.kind == "track" else {record["track_id"]} if scope.kind == "question" else {t["track_id"] for t in self.tracks.values() if t["field_id"] == scope.field_id and (scope.kind == "field" or scope.object_id in self.track_topics[t["track_id"]])}
        return {"scope": scope.model_dump(), "title": record.get("name") or record.get("title") or record.get("statement"),
                "associations": associations, "excluded_count": excluded_count,
                "unavailable_sources": [row for row in self.unavailable if row["track_id"] in track_ids],
                "scientific_approval": False}

    def overview_counts(self) -> list[dict]:
        scopes = [("field", f, f) for f in self.fields]
        scopes += [("topic", f, t) for f, t in sorted(self.field_topics)]
        scopes += [("track", t["field_id"], t["track_id"]) for t in self.tracks.values() if t["field_id"] in self.fields]
        scopes += [("question", self.tracks[q["track_id"]]["field_id"], q["node_id"]) for q in self.questions.values() if q["track_id"] in self.tracks and self.tracks[q["track_id"]]["field_id"] in self.fields]
        result = []
        for kind, field, obj in scopes:
            view = self.read(LiteratureScope(kind=kind, field_id=field, object_id=obj))
            result.append({"kind": kind, "field_id": field, "object_id": obj,
                           "paper_count": len(view["associations"]), "excluded_count": view["excluded_count"],
                           "unavailable_count": len(view["unavailable_sources"])})
        return result
