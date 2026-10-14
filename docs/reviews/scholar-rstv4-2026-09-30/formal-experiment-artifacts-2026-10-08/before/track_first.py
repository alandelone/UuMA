from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .acquisition import AcquisitionService
from .approval import consume_grant
from .database import initialize_catalog, migrate_legacy_projects, transaction
from .experiment import ExperimentResult, ExperimentRunner
from .fieldkg import LegacyPaperPoolAdapter, digest, stable_id
from .models import (
    DecisionProposalInput,
    ExperimentPlanInput,
    FieldInput,
    FieldKGBuildInput,
    FieldKGGapInput,
    FieldKGReviewInput,
    ManuscriptBindingInput,
    ManuscriptStatusInput,
    SubmissionEventInput,
    TrackFirstEvidenceInput,
    TrackFirstManuscriptInput,
    TrackFirstProjectInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
    TrackMilestoneInput,
    new_id,
)
from .research_types import validate_type_payload
from .review import RebuttalPlanner, ReviewSimulator
from .service import NotFoundError, RevisionConflictError
from .source_review import evidence_is_available
from .writing import CitationVerifier, ManuscriptCompiler


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class TrackFirstService:
    """Global Scholar state with Field -> Topic -> Track -> Project ownership."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path(__file__).resolve().parents[3]).resolve()
        self.db_path = self.root / "data" / "catalog.db"
        self.artifacts_root = self.root / "data" / "artifacts"
        initialize_catalog(self.db_path)
        migrate_legacy_projects(self.db_path, self.root / "projects")

    @property
    def paperpool(self) -> AcquisitionService:
        return AcquisitionService(self.root)

    def list_fields(self) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM research_fields ORDER BY name").fetchall()]

    def list_tracks(self, field_id: str | None = None) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            if field_id:
                return [dict(row) for row in conn.execute("SELECT * FROM research_tracks WHERE field_id = ? ORDER BY title", (field_id,)).fetchall()]
            return [dict(row) for row in conn.execute("SELECT * FROM research_tracks ORDER BY title").fetchall()]

    def list_topics(self, field_id: str | None = None) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            if field_id:
                query = "SELECT t.* FROM topics t JOIN field_topics ft ON t.topic_id = ft.topic_id WHERE ft.field_id = ? ORDER BY t.name"
                return [dict(row) for row in conn.execute(query, (field_id,)).fetchall()]
            return [dict(row) for row in conn.execute("SELECT * FROM topics ORDER BY name").fetchall()]

    def create_field(self, payload: FieldInput) -> dict[str, Any]:
        normalized = " ".join(payload.name.casefold().split())
        timestamp = _now()
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM research_fields WHERE normalized_name=?", (normalized,)
            ).fetchone()
            if row is None:
                field_id = new_id("field")
                conn.execute(
                    "INSERT INTO research_fields VALUES(?,?,?,?,?,?)",
                    (field_id, normalized, payload.name, payload.description, timestamp, timestamp),
                )
                row = conn.execute(
                    "SELECT * FROM research_fields WHERE field_id=?", (field_id,)
                ).fetchone()
        return dict(row)

    def create_topic(self, payload: TrackFirstTopicInput) -> dict[str, Any]:
        self._require("research_fields", "field_id", payload.field_id)
        normalized = " ".join(payload.name.casefold().split())
        timestamp = _now()
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM topics WHERE normalized_name=?", (normalized,)).fetchone()
            if row is None:
                topic_id = new_id("topic")
                conn.execute(
                    "INSERT INTO topics VALUES(?,?,?,?,?,?)",
                    (topic_id, normalized, payload.name, payload.description, timestamp, timestamp),
                )
            else:
                topic_id = row["topic_id"]
            conn.execute(
                "INSERT OR IGNORE INTO field_topics VALUES(?,?,?)",
                (payload.field_id, topic_id, timestamp),
            )
            row = conn.execute("SELECT * FROM topics WHERE topic_id=?", (topic_id,)).fetchone()
        result = dict(row)
        result["field_id"] = payload.field_id
        return result

    def create_track(self, payload: TrackFirstTrackInput) -> dict[str, Any]:
        self._require_topic_in_field(payload.field_id, payload.primary_topic_id)
        for topic_id in payload.secondary_topic_ids:
            self._require("topics", "topic_id", topic_id)
        track_id = new_id("track")
        timestamp = _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT INTO research_tracks VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    track_id, payload.field_id, payload.primary_topic_id, payload.title, payload.scope,
                    payload.research_type.value, "ACTIVE", "MAPPED", 1, timestamp, timestamp,
                ),
            )
            conn.execute(
                "INSERT INTO track_topics VALUES(?,?, 'PRIMARY',?)",
                (track_id, payload.primary_topic_id, timestamp),
            )
            for topic_id in payload.secondary_topic_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO track_topics VALUES(?,?, 'SECONDARY',?)",
                    (track_id, topic_id, timestamp),
                )
        return self.get_track(track_id)

    def create_project(self, payload: TrackFirstProjectInput) -> dict[str, Any]:
        track = self.get_track(payload.track_id)
        research_type = payload.research_type or track["research_type"]
        validate_type_payload(research_type, payload.type_payload)
        project_id = new_id("project")
        timestamp = _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project_id, payload.track_id, payload.slug, payload.title,
                    research_type.value if hasattr(research_type, "value") else research_type,
                    _json(payload.type_payload), payload.scope, "ACTIVE", 1, timestamp, timestamp,
                ),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        row = self._require("projects", "project_id", project_id)
        result = dict(row)
        result["type_payload"] = json.loads(result.pop("type_payload_json"))
        return result

    def get_track(self, track_id: str) -> dict[str, Any]:
        row = self._require("research_tracks", "track_id", track_id)
        with transaction(self.db_path) as conn:
            result = dict(row)
            result["topics"] = [dict(item) for item in conn.execute(
                "SELECT topic_id,role FROM track_topics WHERE track_id=? ORDER BY role,created_at",
                (track_id,),
            )]
            result["projects"] = [dict(item) for item in conn.execute(
                "SELECT project_id,slug,title,status,revision FROM projects WHERE track_id=? ORDER BY created_at",
                (track_id,),
            )]
            result["milestones"] = [dict(item) for item in conn.execute(
                "SELECT * FROM track_milestones WHERE track_id=? ORDER BY milestone", (track_id,)
            )]
            result["manuscripts"] = [dict(item) for item in conn.execute(
                """SELECT manuscript_id,title,writing_status,needs_scientific_review,blocker,
                   next_step,revision FROM manuscripts WHERE track_id=? ORDER BY created_at""",
                (track_id,),
            )]
            result["snapshot_updates"] = self._snapshot_updates(conn, track_id)
        return result

    def get_field_view(self, field_id: str) -> dict[str, Any]:
        field = dict(self._require("research_fields", "field_id", field_id))
        with transaction(self.db_path) as conn:
            field["topics"] = [dict(row) for row in conn.execute(
                """SELECT t.* FROM topics t JOIN field_topics ft ON ft.topic_id=t.topic_id
                   WHERE ft.field_id=? ORDER BY t.name""", (field_id,)
            )]
            field["tracks"] = [dict(row) for row in conn.execute(
                "SELECT * FROM research_tracks WHERE field_id=? ORDER BY created_at", (field_id,)
            )]
            field["builds"] = [dict(row) for row in conn.execute(
                "SELECT * FROM fieldkg_builds WHERE field_id=? ORDER BY created_at", (field_id,)
            )]
            field["snapshots"] = [dict(row) for row in conn.execute(
                "SELECT * FROM fieldkg_snapshots WHERE field_id=? ORDER BY version", (field_id,)
            )]
            field["candidate_gaps"] = [dict(row) for row in conn.execute(
                "SELECT * FROM fieldkg_candidate_gaps WHERE field_id=? ORDER BY created_at", (field_id,)
            )]
        return field

    def update_milestone(self, track_id: str, payload: TrackMilestoneInput) -> dict[str, Any]:
        self.get_track(track_id)
        with transaction(self.db_path) as conn:
            current = conn.execute(
                "SELECT revision FROM track_milestones WHERE track_id=? AND milestone=?",
                (track_id, payload.milestone),
            ).fetchone()
            revision = int(current["revision"]) if current else 0
            if revision != payload.expected_revision:
                raise RevisionConflictError("Track milestone revision changed")
            conn.execute(
                """INSERT INTO track_milestones VALUES(?,?,?,?,?,?)
                   ON CONFLICT(track_id,milestone) DO UPDATE SET status=excluded.status,
                   blocker=excluded.blocker,revision=excluded.revision,updated_at=excluded.updated_at""",
                (track_id, payload.milestone, payload.status, payload.blocker, revision + 1, _now()),
            )
            row = conn.execute(
                "SELECT * FROM track_milestones WHERE track_id=? AND milestone=?",
                (track_id, payload.milestone),
            ).fetchone()
        return dict(row)

    def create_fieldkg_build(self, payload: FieldKGBuildInput) -> dict[str, Any]:
        self._require("research_fields", "field_id", payload.field_id)
        for paper_id in payload.paper_ids:
            self._require("papers", "paper_id", paper_id)
        build_id = new_id("fieldkg_build")
        timestamp = _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT INTO fieldkg_builds VALUES(?,?, 'COLLECTING',?,1,?,?)",
                (build_id, payload.field_id, _json(payload.retrieval_scope), timestamp, timestamp),
            )
        return self.get_fieldkg_build(build_id)

    def import_paperpool(self, build_id: str, database_path: str, paper_ids: list[int]) -> dict[str, Any]:
        self.get_fieldkg_build(build_id)
        result = LegacyPaperPoolAdapter(self.db_path).import_batch(build_id, database_path, paper_ids)
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE fieldkg_builds SET status='EXTRACTING_EVIDENCE',revision=revision+1,updated_at=? WHERE build_id=?",
                (_now(), build_id),
            )
        return result

    def get_fieldkg_build(self, build_id: str) -> dict[str, Any]:
        row = self._require("fieldkg_builds", "build_id", build_id)
        with transaction(self.db_path) as conn:
            result = dict(row)
            result["retrieval_scope"] = json.loads(result.pop("retrieval_scope_json"))
            result["papers"] = [dict(item) for item in conn.execute(
                "SELECT * FROM fieldkg_build_papers WHERE build_id=?", (build_id,)
            )]
            result["evidence_candidates"] = [dict(item) for item in conn.execute(
                "SELECT * FROM fieldkg_evidence_candidates WHERE build_id=?", (build_id,)
            )]
            result["candidate_gaps"] = [dict(item) for item in conn.execute(
                "SELECT * FROM fieldkg_candidate_gaps WHERE build_id=?", (build_id,)
            )]
        return result

    def finish_fieldkg_build(self, build_id: str, expected_revision: int) -> dict[str, Any]:
        build = self.get_fieldkg_build(build_id)
        if build["revision"] != expected_revision:
            raise RevisionConflictError("FieldKG build revision changed")
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE fieldkg_builds SET status='READY_FOR_REVIEW',revision=revision+1,updated_at=? WHERE build_id=?",
                (_now(), build_id),
            )
        return self.get_fieldkg_build(build_id)

    def review_evidence_candidate(self, candidate_id: str, payload: FieldKGReviewInput) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM fieldkg_evidence_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown evidence candidate: {candidate_id}")
            if row["revision"] != payload.expected_revision or row["status"] != "PROPOSED":
                raise RevisionConflictError("Evidence candidate is no longer at the expected revision")
            timestamp = _now()
            conn.execute(
                """UPDATE fieldkg_evidence_candidates SET status=?,rationale=?,revision=revision+1,
                   reviewed_at=? WHERE candidate_id=?""",
                (payload.decision, payload.rationale, timestamp, candidate_id),
            )
            if payload.decision == "ACCEPTED":
                unit = conn.execute(
                    """SELECT su.*,ps.paper_version_id,pv.paper_id FROM skeleton_units su
                       JOIN paper_skeletons ps ON ps.skeleton_id=su.skeleton_id
                       JOIN paper_versions pv ON pv.paper_version_id=ps.paper_version_id
                       WHERE su.unit_id=?""", (row["unit_id"],)
                ).fetchone()
                evidence_id = stable_id("evidence", candidate_id, row["statement"])
                location = {
                    "unit_id": row["unit_id"], "page": unit["page_idx"], "section": unit["section"],
                    "sequence": unit["seq_idx"],
                }
                evidence_digest = digest([row["statement"], row["excerpt"], location])
                conn.execute(
                    """INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        evidence_id, "FIELDKG", row["field_id"], None, unit["paper_id"],
                        unit["paper_version_id"], None, row["statement"], row["excerpt"], _json(location),
                        row["relation"], row["confidence"], "paper-skeleton-bridge", "v1",
                        evidence_digest, timestamp,
                    ),
                )
                self._enqueue(conn, "Evidence", evidence_id, row["field_id"], "UPSERT", {
                    "statement": row["statement"], "excerpt": row["excerpt"], "location": location,
                    "content_digest": evidence_digest,
                })
            updated = conn.execute(
                "SELECT * FROM fieldkg_evidence_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        return dict(updated)

    def create_candidate_gap(self, build_id: str, payload: FieldKGGapInput) -> dict[str, Any]:
        build = self.get_fieldkg_build(build_id)
        gap_id = new_id("candidate_gap")
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT INTO fieldkg_candidate_gaps VALUES(?,?,?,?,?,?,?,?,?,?, 'PROPOSED',1,?,NULL)""",
                (
                    gap_id, build_id, build["field_id"], payload.statement, payload.rationale,
                    _json(payload.evidence_ids), _json(payload.counterevidence_ids), _json(payload.conditions),
                    payload.generator_model, payload.prompt_version, _now(),
                ),
            )
        return self._row("fieldkg_candidate_gaps", "candidate_gap_id", gap_id)

    def review_candidate_gap(self, candidate_gap_id: str, payload: FieldKGReviewInput) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM fieldkg_candidate_gaps WHERE candidate_gap_id=?", (candidate_gap_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown candidate gap: {candidate_gap_id}")
            if row["revision"] != payload.expected_revision or row["status"] != "PROPOSED":
                raise RevisionConflictError("Candidate gap is no longer at the expected revision")
            conn.execute(
                """UPDATE fieldkg_candidate_gaps SET status=?,revision=revision+1,reviewed_at=?
                   WHERE candidate_gap_id=?""",
                (payload.decision, _now(), candidate_gap_id),
            )
            updated = conn.execute(
                "SELECT * FROM fieldkg_candidate_gaps WHERE candidate_gap_id=?", (candidate_gap_id,)
            ).fetchone()
            if payload.decision == "ACCEPTED":
                self._enqueue(conn, "CandidateGap", candidate_gap_id, row["field_id"], "UPSERT", dict(updated))
        return dict(updated)

    def seal_snapshot(self, build_id: str, expected_revision: int) -> dict[str, Any]:
        build = self.get_fieldkg_build(build_id)
        if build["revision"] != expected_revision or build["status"] != "READY_FOR_REVIEW":
            raise RevisionConflictError("FieldKG build is not ready at the expected revision")
        with transaction(self.db_path) as conn:
            pending = conn.execute(
                """SELECT
                   (SELECT COUNT(1) FROM fieldkg_evidence_candidates WHERE build_id=? AND status='PROPOSED')+
                   (SELECT COUNT(1) FROM fieldkg_candidate_gaps WHERE build_id=? AND status='PROPOSED')""",
                (build_id, build_id),
            ).fetchone()[0]
            if pending:
                raise ValueError("All evidence and gap candidates must be reviewed before sealing")
            accepted_candidates = conn.execute(
                "SELECT * FROM fieldkg_evidence_candidates WHERE build_id=? AND status='ACCEPTED'",
                (build_id,),
            ).fetchall()
            evidence = []
            for candidate in accepted_candidates:
                evidence_id = stable_id("evidence", candidate["candidate_id"], candidate["statement"])
                evidence_row = conn.execute(
                    "SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)
                ).fetchone()
                if evidence_row is not None:
                    evidence.append(dict(evidence_row))
            gaps = [dict(row) for row in conn.execute(
                "SELECT * FROM fieldkg_candidate_gaps WHERE build_id=? AND status='ACCEPTED'", (build_id,)
            )]
            manifest = {
                "field_id": build["field_id"], "build_id": build_id,
                "papers": build["papers"],
                "evidence": [{"evidence_id": item["evidence_id"], "digest": item["content_digest"]} for item in evidence],
                "candidate_gaps": [{"candidate_gap_id": item["candidate_gap_id"], "digest": digest(item)} for item in gaps],
            }
            content_digest = digest(manifest)
            existing = conn.execute(
                "SELECT * FROM fieldkg_snapshots WHERE field_id=? AND content_digest=?",
                (build["field_id"], content_digest),
            ).fetchone()
            if existing:
                return dict(existing)
            version = conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM fieldkg_snapshots WHERE field_id=?",
                (build["field_id"],),
            ).fetchone()[0]
            snapshot_id = new_id("fieldkg_snapshot")
            timestamp = _now()
            conn.execute(
                "INSERT INTO fieldkg_snapshots VALUES(?,?,?,?,'SEALED',?,?, 'MAPPED',?)",
                (snapshot_id, build["field_id"], version, build_id, _json(manifest), content_digest, timestamp),
            )
            for item in manifest["evidence"]:
                conn.execute(
                    "INSERT INTO fieldkg_snapshot_members VALUES(?, 'EVIDENCE',?,?)",
                    (snapshot_id, item["evidence_id"], item["digest"]),
                )
            for item in manifest["candidate_gaps"]:
                conn.execute(
                    "INSERT INTO fieldkg_snapshot_members VALUES(?, 'CANDIDATE_GAP',?,?)",
                    (snapshot_id, item["candidate_gap_id"], item["digest"]),
                )
            conn.execute(
                "UPDATE fieldkg_builds SET status='SEALED',revision=revision+1,updated_at=? WHERE build_id=?",
                (timestamp, build_id),
            )
            self._enqueue(conn, "FieldKGSnapshot", snapshot_id, build["field_id"], "UPSERT", manifest)
            row = conn.execute("SELECT * FROM fieldkg_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        return dict(row)

    def adopt_snapshot(self, track_id: str, snapshot_id: str) -> dict[str, Any]:
        track = self.get_track(track_id)
        snapshot = self._row("fieldkg_snapshots", "snapshot_id", snapshot_id)
        if snapshot["status"] != "SEALED" or snapshot["field_id"] != track["field_id"]:
            raise ValueError("A track may adopt only a sealed snapshot from its own field")
        adoption_id = stable_id("adoption", track_id, snapshot_id)
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO track_snapshot_adoptions VALUES(?,?,?,?,?)",
                (adoption_id, track_id, snapshot_id, snapshot["content_digest"], _now()),
            )
        return self._row("track_snapshot_adoptions", "adoption_id", adoption_id)

    def add_evidence(self, payload: TrackFirstEvidenceInput) -> dict[str, Any]:
        track = self.get_track(payload.track_id)
        paper_id = payload.paper_id if not payload.paper_id.startswith("run:") else None
        if paper_id:
            self._require("papers", "paper_id", paper_id)
        evidence_id = new_id("evidence")
        location = payload.location_data or {"legacy": payload.location}
        content_digest = digest([payload.statement, payload.excerpt, location])
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id, "TRACK", track["field_id"], payload.track_id, paper_id, None,
                    payload.paper_id.removeprefix("run:") if payload.paper_id.startswith("run:") else None,
                    payload.statement, payload.excerpt, _json(location), payload.relation.value,
                    payload.confidence, payload.extractor_model, payload.prompt_version, content_digest, _now(),
                ),
            )
        return self._row("evidence", "evidence_id", evidence_id)

    def propose_decision(self, track_id: str, payload: DecisionProposalInput) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            proposal_id = self._propose_decision(conn, track_id, payload)
        return self.get_decision(proposal_id)

    def _propose_decision(self, conn: Any, track_id: str, payload: DecisionProposalInput) -> str:
        track = conn.execute("SELECT * FROM research_tracks WHERE track_id=?", (track_id,)).fetchone()
        if track is None:
            raise NotFoundError(f"Unknown track: {track_id}")
        if track["mapping_status"] != "MAPPED":
            raise ValueError("Legacy track requires topic mapping before new scientific decisions")
        if payload.track_id and payload.track_id != track_id:
            raise ValueError("Payload track_id does not match the selected track")
        for evidence_id in payload.evidence_ids:
            evidence = conn.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
            if evidence is None:
                raise NotFoundError(f"Unknown evidence: {evidence_id}")
            if not evidence_is_available(conn, dict(evidence)):
                raise RevisionConflictError("Evidence source requires a new review before a scientific decision")
            if evidence["scope_kind"] == "TRACK" and evidence["track_id"] != track_id:
                raise ValueError("Track evidence cannot be referenced across tracks")
        upstream = [self._node(conn, node_id) for node_id in payload.upstream_node_ids]
        if any(row["track_id"] != track_id for row in upstream):
            raise ValueError("Research dependencies cannot cross tracks directly")
        if payload.supersedes_node_id:
            self._validate_supersession(
                conn, payload.supersedes_node_id, track_id, payload.kind.value,
                payload.upstream_node_ids,
            )
        if payload.kind.value == "idea" and any(
            row["node_type"] != "gap" or row["status"] != "APPROVED" for row in upstream
        ):
            raise ValueError("Every upstream node for an idea must be an approved gap")
        node_id = new_id(payload.kind.value)
        proposal_id = new_id("proposal")
        timestamp = _now()
        conn.execute(
            "INSERT INTO research_nodes VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                node_id, track_id, payload.kind.value, "PROPOSED", payload.statement,
                payload.rationale, _json({"evidence_ids": payload.evidence_ids, "upstream_node_ids": payload.upstream_node_ids}),
                1, timestamp, timestamp,
            ),
        )
        conn.execute(
            "INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal_id, track_id, node_id, payload.kind.value, "PROPOSED",
                f"APPROVE {proposal_id}", 1, None, None, payload.supersedes_node_id,
                timestamp, None,
            ),
        )
        for evidence_id in payload.evidence_ids:
            conn.execute("INSERT INTO node_evidence VALUES(?,?)", (node_id, evidence_id))
        for upstream_id in payload.upstream_node_ids:
            conn.execute(
                "INSERT INTO research_edges VALUES(?,?,?,?,?,?)",
                (new_id("edge"), track_id, upstream_id, node_id, "MOTIVATES", timestamp),
            )
        return proposal_id

    def get_decision(self, proposal_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                """SELECT d.*,n.statement,n.rationale,n.revision,n.payload_json FROM decisions d
                   JOIN research_nodes n ON n.node_id=d.node_id WHERE d.proposal_id=?""",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown proposal: {proposal_id}")
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def approve_decision(self, proposal_id: str, expected_revision: int) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            self._approve_decision(conn, proposal_id, expected_revision)
        return self.get_decision(proposal_id)

    def _approve_decision(self, conn: Any, proposal_id: str, expected_revision: int) -> None:
        decision = conn.execute("SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,)).fetchone()
        if decision is None:
            raise NotFoundError(f"Unknown proposal: {proposal_id}")
        node = self._node(conn, decision["node_id"])
        if decision["status"] != "PROPOSED" or decision["expected_revision"] != expected_revision or node["revision"] != expected_revision:
            raise RevisionConflictError("Proposal is no longer pending at the expected revision")
        upstream = json.loads(node["payload_json"]).get("upstream_node_ids", [])
        for evidence in conn.execute("SELECT e.* FROM evidence e JOIN node_evidence ne ON ne.evidence_id=e.evidence_id WHERE ne.node_id=?", (node["node_id"],)):
            if not evidence_is_available(conn, dict(evidence)):
                raise RevisionConflictError("Evidence source changed after this proposal; review a new source before approval")
        for upstream_id in upstream:
            dependency = self._node(conn, upstream_id)
            if dependency["track_id"] != node["track_id"] or dependency["status"] != "APPROVED":
                raise RevisionConflictError(
                    "A scientific upstream dependency is no longer approved"
                )
        if decision["supersedes_node_id"]:
            self._validate_supersession(
                conn, decision["supersedes_node_id"], node["track_id"],
                node["node_type"], upstream,
            )
        grant = consume_grant(conn, proposal_id=proposal_id, proposal_type="decision", revision=expected_revision)
        timestamp = _now()
        conn.execute(
            "UPDATE decisions SET status='APPROVED',confirmation_text=?,resolved_at=? WHERE proposal_id=?",
            (_json({"grant_id": grant["grant_id"], "message_id": grant["message_id"]}), timestamp, proposal_id),
        )
        conn.execute(
            "UPDATE research_nodes SET status='APPROVED',updated_at=? WHERE node_id=?",
            (timestamp, decision["node_id"]),
        )
        if decision["supersedes_node_id"]:
            self._supersede_and_mark_stale(conn, decision["supersedes_node_id"], timestamp)

    def _validate_supersession(
        self, conn: Any, node_id: str, track_id: str, kind: str, upstream_ids: list[str],
    ) -> None:
        original = self._node(conn, node_id)
        if original["track_id"] != track_id or original["node_type"] != kind:
            raise ValueError("A replacement must have the same track and scientific node type")
        if original["status"] not in {"APPROVED", "STALE"}:
            raise RevisionConflictError(
                "The scientific node is no longer available for replacement"
            )
        affected = self._dependent_node_ids(conn, node_id, track_id)
        if affected.intersection(upstream_ids):
            raise ValueError("A replacement cannot depend on the scientific basis it invalidates")

    @staticmethod
    def _dependent_node_ids(conn: Any, node_id: str, track_id: str) -> set[str]:
        # UNION deduplicates converging paths and terminates even for legacy cycles.
        return {row["node_id"] for row in conn.execute(
            """WITH RECURSIVE affected(node_id) AS (
                 SELECT node_id FROM research_nodes WHERE node_id=? AND track_id=?
                 UNION
                 SELECT e.target_node_id FROM research_edges e
                 JOIN affected a ON a.node_id=e.source_node_id
                 JOIN research_nodes n ON n.node_id=e.target_node_id
                 WHERE e.track_id=? AND n.track_id=?
               ) SELECT node_id FROM affected""",
            (node_id, track_id, track_id, track_id),
        )}

    def _supersede_and_mark_stale(self, conn: Any, node_id: str, timestamp: str) -> None:
        original = self._node(conn, node_id)
        affected = sorted(self._dependent_node_ids(conn, node_id, original["track_id"]))
        conn.execute(
            "UPDATE research_nodes SET status='SUPERSEDED',revision=revision+1,updated_at=? "
            "WHERE node_id=?",
            (timestamp, node_id),
        )
        placeholders = ",".join("?" for _ in affected)
        conn.execute(
            f"UPDATE research_nodes SET status='STALE',revision=revision+1,updated_at=? "
            f"WHERE node_id IN ({placeholders}) AND status='APPROVED'",
            (timestamp, *affected),
        )
        # One manuscript revision per approval, including indirect or multiple bindings.
        # Retain its writing status, original bindings, versions and submission history.
        conn.execute(
            "UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=? "
            "WHERE manuscript_id IN (SELECT manuscript_id FROM manuscript_nodes "
            f"WHERE node_id IN ({placeholders}))",
            (timestamp, *affected),
        )

    def build_blueprint(self, track_id: str) -> dict[str, Any]:
        track = self.get_track(track_id)
        with transaction(self.db_path) as conn:
            approved = []
            for row in conn.execute(
                "SELECT * FROM research_nodes WHERE track_id=? AND status='APPROVED' ORDER BY created_at",
                (track_id,),
            ):
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                item["kind"] = item["node_type"]
                item["evidence"] = [dict(ev) for ev in conn.execute(
                    """SELECT e.* FROM evidence e JOIN node_evidence ne ON ne.evidence_id=e.evidence_id
                       WHERE ne.node_id=?""", (row["node_id"],)
                )]
                item["provenance"] = self._provenance_with_conn(conn, row["node_id"])
                approved.append(item)
            stale = [dict(row) for row in conn.execute(
                "SELECT * FROM research_nodes WHERE track_id=? AND status IN ('STALE','SUPERSEDED')",
                (track_id,),
            )]
        return {"track": track, "approved": approved, "stale_objects": stale}

    def snapshot_blueprint(self, track_id: str) -> dict[str, Any]:
        payload = self.build_blueprint(track_id)
        with transaction(self.db_path) as conn:
            revision = conn.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM blueprint_snapshots WHERE track_id=?",
                (track_id,),
            ).fetchone()[0]
            blueprint_id = new_id("blueprint")
            conn.execute(
                "INSERT INTO blueprint_snapshots VALUES(?,?,?,?,?)",
                (blueprint_id, track_id, revision, _json(payload), _now()),
            )
        return {"blueprint_id": blueprint_id, "revision": revision, **payload}

    def trace_provenance(self, node_id: str) -> dict[str, Any]:
        self._require("research_nodes", "node_id", node_id)
        with transaction(self.db_path) as conn:
            return {"node_id": node_id, **self._provenance_with_conn(conn, node_id)}

    def impact_analysis(self, node_id: str) -> list[dict[str, Any]]:
        origin = self._require("research_nodes", "node_id", node_id)
        with transaction(self.db_path) as conn:
            pending = deque([node_id])
            seen = {node_id}
            impacted: list[dict[str, Any]] = []
            while pending:
                rows = conn.execute(
                    """SELECT n.node_id,n.node_type,n.status,n.statement,n.revision
                       FROM research_edges e JOIN research_nodes n ON n.node_id=e.target_node_id
                       WHERE e.source_node_id=? AND e.track_id=?""",
                    (pending.popleft(), origin["track_id"]),
                ).fetchall()
                for row in rows:
                    if row["node_id"] not in seen:
                        seen.add(row["node_id"])
                        pending.append(row["node_id"])
                        impacted.append(dict(row))
        return impacted

    def propose_experiment_plan(
        self, track_id: str, payload: ExperimentPlanInput, project_id: str | None = None
    ) -> dict[str, Any]:
        method = self._require("research_nodes", "node_id", payload.method_node_id)
        if method["track_id"] != track_id or method["node_type"] != "method" or method["status"] != "APPROVED":
            raise ValueError("Experiment plans require an approved method in the selected track")
        if project_id:
            project = self.get_project(project_id)
            if project["track_id"] != track_id:
                raise ValueError("Experiment project must belong to the selected track")
            base = (self.root / "projects" / project["slug"]).resolve()
        else:
            base = (self.artifacts_root / track_id / "experiments").resolve()
        working_directory = (base / payload.working_directory).resolve()
        if working_directory != base and base not in working_directory.parents:
            raise ValueError("working_directory must remain inside its Track/Project workspace")
        script_path = None
        if payload.script_path:
            script = (working_directory / payload.script_path).resolve()
            if script != working_directory and working_directory not in script.parents:
                raise ValueError("script_path must remain inside working_directory")
            if not script.is_file() or hashlib.sha256(script.read_bytes()).hexdigest() != payload.script_sha256:
                raise ValueError("script_path is missing or script_sha256 does not match")
            script_path = str(script)
        plan_id, proposal_id, timestamp = new_id("experiment_plan"), new_id("proposal"), _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT INTO experiment_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (plan_id, proposal_id, track_id, project_id, payload.method_node_id, "PROPOSED", 1,
                 _json(payload.argv), str(working_directory), script_path, payload.script_sha256,
                 payload.timeout_seconds, payload.metrics_json_path, timestamp, None),
            )
        return self.get_experiment_plan(plan_id)

    def get_experiment_plan(self, plan_id: str) -> dict[str, Any]:
        result = self._row("experiment_plans", "plan_id", plan_id)
        result["argv"] = json.loads(result.pop("argv_json"))
        result["approval_phrase"] = f"APPROVE {result['proposal_id']}"
        return result

    def approve_experiment_plan(self, plan_id: str, expected_revision: int) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            plan = conn.execute("SELECT * FROM experiment_plans WHERE plan_id=?", (plan_id,)).fetchone()
            if plan is None:
                raise NotFoundError(f"Unknown experiment plan: {plan_id}")
            if plan["status"] != "PROPOSED" or plan["revision"] != expected_revision:
                raise RevisionConflictError("Experiment plan is no longer pending at this revision")
            method = self._node(conn, plan["method_node_id"])
            if method["status"] != "APPROVED" or method["track_id"] != plan["track_id"]:
                raise RevisionConflictError("The experiment method is no longer approved in this track")
            consume_grant(conn, proposal_id=plan["proposal_id"], proposal_type="experiment_plan", revision=expected_revision)
            conn.execute("UPDATE experiment_plans SET status='APPROVED',approved_at=? WHERE plan_id=?", (_now(), plan_id))
        return self.get_experiment_plan(plan_id)

    def run_experiment(self, plan_id: str) -> dict[str, Any]:
        plan = self.get_experiment_plan(plan_id)
        if plan["status"] != "APPROVED":
            raise PermissionError("Only an approved experiment plan may run")
        method = self._require("research_nodes", "node_id", plan["method_node_id"])
        if (
            method["track_id"] != plan["track_id"]
            or method["node_type"] != "method"
            or method["status"] != "APPROVED"
        ):
            raise RevisionConflictError("The experiment method is no longer approved in this track")
        if plan.get("script_path"):
            script = Path(plan["script_path"])
            if not script.is_file() or hashlib.sha256(script.read_bytes()).hexdigest() != plan["script_sha256"]:
                raise RevisionConflictError("The approved experiment script changed")
        result = ExperimentRunner(self.db_path).run_script(
            plan["argv"], track_id=plan["track_id"], project_id=plan["project_id"],
            cwd=plan["working_directory"], timeout=plan["timeout_seconds"],
            metrics_json_path=plan["metrics_json_path"],
        )
        return {"run_id": result.run_id, "plan_id": plan_id, "exit_code": result.exit_code,
                "duration_seconds": round(result.duration_seconds, 2), "metrics": result.metrics,
                "stdout_preview": result.stdout[:1000], "stderr_preview": result.stderr[:1000]}

    def record_experiment_evidence(
        self, run_id: str, statement: str, metric_key: str | None = None, confidence: float = 0.95
    ) -> dict[str, Any]:
        run = self._require("pipeline_runs", "run_id", run_id)
        detail = json.loads(run["detail_json"])
        result = ExperimentResult(run_id, detail.get("argv", [run_id]), detail.get("exit_code", 0), "", "",
                                  detail.get("duration", 0.0), [], detail.get("metrics", {}))
        payload = ExperimentRunner(self.db_path).convert_result_to_evidence(
            result, statement=statement, metric_key=metric_key, confidence=confidence
        )
        return self.add_evidence(TrackFirstEvidenceInput(
            track_id=run["track_id"], **payload.model_dump(),
            location_data={"pipeline_run_id": run_id},
        ))

    def simulate_review(self, manuscript_id: str) -> dict[str, Any]:
        manuscript = self.get_manuscript(manuscript_id)
        blueprint = self.build_blueprint(manuscript["track_id"])
        selected = {item["node_id"] for item in manuscript["nodes"]}
        blueprint["approved"] = [node for node in blueprint["approved"] if node["node_id"] in selected]
        report = ReviewSimulator.evaluate_blueprint(blueprint)
        report["rebuttal_proposals"] = RebuttalPlanner.plan_rebuttal(report)
        return report

    def _provenance_with_conn(self, conn: Any, node_id: str) -> dict[str, Any]:
        return {
            "evidence": [dict(row) for row in conn.execute(
                """SELECT e.* FROM evidence e JOIN node_evidence ne ON ne.evidence_id=e.evidence_id
                   WHERE ne.node_id=?""", (node_id,))],
            "upstream": [dict(row) for row in conn.execute(
                "SELECT source_node_id,relation FROM research_edges WHERE target_node_id=?", (node_id,))],
            "assessments": [],
        }

    def create_manuscript(self, payload: TrackFirstManuscriptInput) -> dict[str, Any]:
        track = self.get_track(payload.track_id)
        for project_id in payload.project_ids:
            project = self.get_project(project_id)
            if project["track_id"] != payload.track_id:
                raise ValueError("A manuscript may bind only projects owned by its track")
        manuscript_id = new_id("manuscript")
        timestamp = _now()
        research_type = payload.research_type.value if payload.research_type else track["research_type"]
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT INTO manuscripts(
                   manuscript_id,track_id,title,scope,research_type,writing_status,
                   needs_scientific_review,blocker,next_step,revision,created_at,updated_at,
                   workflow_stage) VALUES(?,?,?,?,?,'PLANNING',0,NULL,NULL,1,?,?,'PLANNING')""",
                (
                    manuscript_id,
                    payload.track_id,
                    payload.title,
                    payload.scope,
                    research_type,
                    timestamp,
                    timestamp,
                ),
            )
            for project_id in payload.project_ids:
                conn.execute("INSERT INTO manuscript_projects VALUES(?,?)", (manuscript_id, project_id))
            self._bind_manuscript(conn, manuscript_id, payload.track_id, payload.node_ids, payload.evidence_ids, payload.section_map)
            conn.execute(
                "INSERT INTO manuscript_status_history VALUES(?,?, 'PLANNING',NULL,NULL,'Created',1,?)",
                (new_id("history"), manuscript_id, timestamp),
            )
        return self.get_manuscript(manuscript_id)

    def get_manuscript(self, manuscript_id: str) -> dict[str, Any]:
        row = self._require("manuscripts", "manuscript_id", manuscript_id)
        with transaction(self.db_path) as conn:
            result = dict(row)
            for key, table in (
                ("projects", "manuscript_projects"), ("nodes", "manuscript_nodes"),
                ("evidence", "manuscript_evidence"), ("versions", "manuscript_versions"),
                ("history", "manuscript_status_history"), ("submissions", "submission_events"),
            ):
                result[key] = [dict(item) for item in conn.execute(
                    f"SELECT * FROM {table} WHERE manuscript_id=? ORDER BY rowid", (manuscript_id,)
                )]
        return result

    def bind_manuscript(self, manuscript_id: str, payload: ManuscriptBindingInput) -> dict[str, Any]:
        manuscript = self.get_manuscript(manuscript_id)
        if manuscript["revision"] != payload.expected_revision:
            raise RevisionConflictError("Manuscript revision changed")
        with transaction(self.db_path) as conn:
            self._bind_manuscript(conn, manuscript_id, manuscript["track_id"], payload.node_ids, payload.evidence_ids, payload.section_map)
            conn.execute(
                "UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=? WHERE manuscript_id=?",
                (_now(), manuscript_id),
            )
        return self.get_manuscript(manuscript_id)

    def update_manuscript_status(self, manuscript_id: str, payload: ManuscriptStatusInput) -> dict[str, Any]:
        manuscript = self.get_manuscript(manuscript_id)
        if manuscript["revision"] != payload.expected_revision:
            raise RevisionConflictError("Manuscript revision changed")
        revision = payload.expected_revision + 1
        with transaction(self.db_path) as conn:
            conn.execute(
                """UPDATE manuscripts SET writing_status=?,blocker=?,next_step=?,revision=?,updated_at=?
                   WHERE manuscript_id=?""",
                (payload.status.value, payload.blocker, payload.next_step, revision, _now(), manuscript_id),
            )
            conn.execute(
                "INSERT INTO manuscript_status_history VALUES(?,?,?,?,?,?,?,?)",
                (new_id("history"), manuscript_id, payload.status.value, payload.blocker, payload.next_step, payload.reason, revision, _now()),
            )
        return self.get_manuscript(manuscript_id)

    def record_submission(self, manuscript_id: str, payload: SubmissionEventInput) -> dict[str, Any]:
        self.get_manuscript(manuscript_id)
        event_id = new_id("submission")
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT INTO submission_events VALUES(?,?,?,?,?,?,?)",
                (event_id, manuscript_id, payload.venue, payload.round, payload.status.value, payload.detail, _now()),
            )
        return self._row("submission_events", "event_id", event_id)

    def compile_manuscript(self, manuscript_id: str, abstract: str, sections: list[dict[str, str]] | None = None) -> str:
        manuscript = self.get_manuscript(manuscript_id)
        if manuscript["needs_scientific_review"]:
            raise RevisionConflictError("Manuscript scientific bindings require review before compilation")
        blueprint = self.build_blueprint(manuscript["track_id"])
        selected_nodes = {item["node_id"] for item in manuscript["nodes"]}
        blueprint["approved"] = [item for item in blueprint["approved"] if item["node_id"] in selected_nodes]
        references: dict[str, dict[str, Any]] = {}
        with transaction(self.db_path) as conn:
            for binding in manuscript["evidence"]:
                evidence = conn.execute("SELECT * FROM evidence WHERE evidence_id=?", (binding["evidence_id"],)).fetchone()
                if evidence and evidence["paper_id"]:
                    paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (evidence["paper_id"],)).fetchone()
                    if paper:
                        decoded = dict(paper)
                        decoded["authors"] = json.loads(decoded.pop("authors_json"))
                        references[evidence["evidence_id"]] = decoded
        if sections is None:
            sections = [{"title": "Research Blueprint", "content": _json(blueprint)}]
        content = ManuscriptCompiler.compile_markdown(
            title=manuscript["title"], abstract=abstract, sections=sections,
            references=list(references.values()),
        )
        inputs = {"track_id": manuscript["track_id"], "node_ids": sorted(selected_nodes), "evidence": manuscript["evidence"]}
        with transaction(self.db_path) as conn:
            version = conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM manuscript_versions WHERE manuscript_id=?",
                (manuscript_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO manuscript_versions VALUES(?,?,?,?,?,?)",
                (new_id("manuscript_version"), manuscript_id, version, content, _json(inputs), _now()),
            )
        return content

    def verify_citations(self, manuscript_id: str, text: str) -> dict[str, Any]:
        manuscript = self.get_manuscript(manuscript_id)
        allowed = {item["evidence_id"] for item in manuscript["evidence"]}
        with transaction(self.db_path) as conn:
            known = {row["evidence_id"] for row in conn.execute(
                f"SELECT evidence_id FROM evidence WHERE evidence_id IN ({','.join('?' for _ in allowed)})",
                tuple(allowed),
            )} if allowed else set()
        result = CitationVerifier.verify(text, known)
        return result

    def _bind_manuscript(
        self, conn: Any, manuscript_id: str, track_id: str, node_ids: list[str],
        evidence_ids: list[str], section_map: dict[str, list[str]],
    ) -> None:
        sections = {node_id: section for section, ids in section_map.items() for node_id in ids}
        for node_id in node_ids:
            node = self._node(conn, node_id)
            if node["track_id"] != track_id:
                raise ValueError("A manuscript cannot bind another track's research node")
            conn.execute(
                "INSERT OR REPLACE INTO manuscript_nodes VALUES(?,?,?,?)",
                (manuscript_id, node_id, sections.get(node_id), node["revision"]),
            )
        for evidence_id in evidence_ids:
            evidence = conn.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
            if evidence is None:
                raise NotFoundError(f"Unknown evidence: {evidence_id}")
            if not evidence_is_available(conn, dict(evidence)):
                raise RevisionConflictError("This Evidence needs a new source review before manuscript binding")
            if evidence["scope_kind"] == "TRACK" and evidence["track_id"] != track_id:
                raise ValueError("A manuscript cannot bind another track's evidence")
            conn.execute(
                "INSERT OR REPLACE INTO manuscript_evidence VALUES(?,?,?)",
                (manuscript_id, evidence_id, evidence["content_digest"]),
            )

    def _snapshot_updates(self, conn: Any, track_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute(
            """SELECT a.snapshot_id AS adopted_snapshot_id,s.version AS adopted_version,
               latest.snapshot_id AS latest_snapshot_id,latest.version AS latest_version
               FROM track_snapshot_adoptions a JOIN fieldkg_snapshots s ON s.snapshot_id=a.snapshot_id
               JOIN fieldkg_snapshots latest ON latest.field_id=s.field_id
               WHERE a.track_id=? AND latest.version=(SELECT MAX(version) FROM fieldkg_snapshots x WHERE x.field_id=s.field_id)
               AND latest.version>s.version""", (track_id,)
        )]

    def _enqueue(
        self, conn: Any, aggregate_type: str, aggregate_id: str, field_id: str,
        operation: str, payload: dict[str, Any],
    ) -> None:
        timestamp = _now()
        job_id = stable_id("projection", aggregate_type, aggregate_id, operation, digest(payload))
        conn.execute(
            "INSERT OR IGNORE INTO projection_outbox VALUES(?,?,?,?,?,?,'PENDING',0,NULL,?,?)",
            (job_id, aggregate_type, aggregate_id, field_id, operation, _json(payload), timestamp, timestamp),
        )

    def _require_topic_in_field(self, field_id: str, topic_id: str) -> None:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM field_topics WHERE field_id=? AND topic_id=?", (field_id, topic_id)
            ).fetchone()
        if row is None:
            raise ValueError("Primary topic must belong to the selected field")

    def _require(self, table: str, key: str, value: str) -> Any:
        with transaction(self.db_path) as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown {table}: {value}")
        return row

    def _row(self, table: str, key: str, value: str) -> dict[str, Any]:
        return dict(self._require(table, key, value))

    @staticmethod
    def _node(conn: Any, node_id: str) -> Any:
        row = conn.execute("SELECT * FROM research_nodes WHERE node_id=?", (node_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown research node: {node_id}")
        return row
