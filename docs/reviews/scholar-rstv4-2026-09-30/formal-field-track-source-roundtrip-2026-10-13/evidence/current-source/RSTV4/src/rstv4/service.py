from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .approval import consume_grant
from .database import initialize_catalog, initialize_project, transaction
from .experiment import ExperimentResult, ExperimentRunner
from .models import (
    DecisionProposalInput,
    DecisionStatus,
    EvidenceAssessmentInput,
    EvidenceInput,
    ExperimentPlanInput,
    FieldInput,
    FoundationVersionInput,
    ManuscriptBindingInput,
    ManuscriptInput,
    ManuscriptStatusInput,
    ResearchProjectInput,
    SourceCandidate,
    SubmissionEventInput,
    TopicInput,
    TrackInput,
    TrackProgressInput,
    new_id,
)
from .research_types import validate_type_payload
from .review import RebuttalPlanner, ReviewSimulator
from .sources import search_all
from .writing import CitationVerifier, ManuscriptCompiler


class RSTV4Error(RuntimeError):
    pass


class NotFoundError(RSTV4Error):
    pass


class RevisionConflictError(RSTV4Error):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_title(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold())


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _paper_key(candidate: SourceCandidate) -> str:
    if candidate.doi:
        return f"doi:{candidate.doi.casefold().strip()}"
    if candidate.external_id:
        return f"{candidate.source_provider}:{candidate.external_id.casefold().strip()}"
    digest = hashlib.sha256(_normalized_title(candidate.title).encode("utf-8")).hexdigest()
    return f"title:{digest}"


class RSTV4Service:
    """Owns RSTV4's scientific state; UuMA remains the execution-control system."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path(__file__).resolve().parents[3]).resolve()
        self.catalog_path = self.root / "data" / "catalog.db"
        self.projects_root = self.root / "projects"
        initialize_catalog(self.catalog_path)
        for project_database in self.projects_root.glob("*/research.db"):
            initialize_project(project_database)

    def create_project(self, payload: ResearchProjectInput) -> dict[str, Any]:
        validate_type_payload(payload.research_type, payload.type_payload)
        path = self._project_path(payload.slug)
        if path.exists():
            raise RSTV4Error(f"Project already exists: {payload.slug}")
        initialize_project(path)
        project_id = new_id("project")
        timestamp = _now()
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO project(project_id,slug,title,field,research_type,type_payload_json,scope,status,revision,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project_id,
                    payload.slug,
                    payload.title,
                    payload.field,
                    payload.research_type.value,
                    _json(payload.type_payload),
                    payload.scope,
                    "ACTIVE",
                    1,
                    timestamp,
                    timestamp,
                ),
            )
        initialize_project(path)
        field = self.create_field(FieldInput(name=payload.field))
        self.associate_project_field(payload.slug, field["field_id"], scope=payload.scope)
        return self.get_project(payload.slug)

    def get_project(self, slug: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute("SELECT * FROM project LIMIT 1").fetchone()
        if row is None:
            raise NotFoundError(f"Project metadata missing: {slug}")
        result = self._decode_project(row)
        with transaction(path) as conn:
            result["fields"] = [dict(item) for item in conn.execute("SELECT * FROM project_fields")]
            result["topics"] = [dict(item) for item in conn.execute("SELECT * FROM project_topics")]
            result["tracks"] = [dict(item) for item in conn.execute(
                "SELECT * FROM research_tracks ORDER BY created_at"
            )]
        return result

    def create_field(self, payload: FieldInput) -> dict[str, Any]:
        normalized = _normalized_name(payload.name)
        timestamp = _now()
        with transaction(self.catalog_path) as conn:
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

    def create_topic(self, payload: TopicInput) -> dict[str, Any]:
        normalized = _normalized_name(payload.name)
        timestamp = _now()
        with transaction(self.catalog_path) as conn:
            row = conn.execute("SELECT * FROM topics WHERE normalized_name=?", (normalized,)).fetchone()
            if row is None:
                topic_id = new_id("topic")
                conn.execute(
                    "INSERT INTO topics VALUES(?,?,?,?,?,?)",
                    (topic_id, normalized, payload.name, payload.description, timestamp, timestamp),
                )
                row = conn.execute("SELECT * FROM topics WHERE topic_id=?", (topic_id,)).fetchone()
        return dict(row)

    def get_field(self, field_id: str) -> dict[str, Any]:
        return self._catalog_object("research_fields", "field_id", field_id)

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        return self._catalog_object("topics", "topic_id", topic_id)

    def associate_field_topic(self, field_id: str, topic_id: str) -> dict[str, str]:
        self.get_field(field_id)
        self.get_topic(topic_id)
        timestamp = _now()
        with transaction(self.catalog_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO field_topics(field_id,topic_id,created_at) VALUES(?,?,?)",
                (field_id, topic_id, timestamp),
            )
        return {"field_id": field_id, "topic_id": topic_id}

    def associate_project_field(self, slug: str, field_id: str, *, scope: str | None = None) -> None:
        self.get_field(field_id)
        with transaction(self._require_project_path(slug)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO project_fields(field_id,scope,created_at) VALUES(?,?,?)",
                (field_id, scope, _now()),
            )

    def associate_project_topic(
        self, slug: str, topic_id: str, *, scope: str | None = None, role: str = "PRIMARY"
    ) -> dict[str, Any]:
        self.get_topic(topic_id)
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO project_topics(topic_id,scope,role,created_at) VALUES(?,?,?,?)
                   ON CONFLICT(topic_id) DO UPDATE SET scope=excluded.scope,role=excluded.role""",
                (topic_id, scope, role, _now()),
            )
            row = conn.execute("SELECT * FROM project_topics WHERE topic_id=?", (topic_id,)).fetchone()
        return dict(row)

    def create_track(self, slug: str, payload: TrackInput) -> dict[str, Any]:
        project = self.get_project(slug)
        path = self._require_project_path(slug)
        for topic_id in payload.topic_ids:
            self.get_topic(topic_id)
            with transaction(path) as conn:
                if conn.execute(
                    "SELECT 1 FROM project_topics WHERE topic_id=?", (topic_id,)
                ).fetchone() is None:
                    raise ValueError("A track topic must first be associated with its project")
        track_id = new_id("track")
        timestamp = _now()
        research_type = payload.research_type.value if payload.research_type else project["research_type"]
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO research_tracks(
                   track_id,title,scope,research_type,status,revision,is_default,created_at,updated_at)
                   VALUES(?,?,?,?,?,1,0,?,?)""",
                (track_id, payload.title, payload.scope, research_type, "ACTIVE", timestamp, timestamp),
            )
            for topic_id in payload.topic_ids:
                conn.execute(
                    "INSERT INTO track_topics(track_id,topic_id,created_at) VALUES(?,?,?)",
                    (track_id, topic_id, timestamp),
                )
        return self.get_track(slug, track_id)

    def get_track(self, slug: str, track_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute("SELECT * FROM research_tracks WHERE track_id=?", (track_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown research track: {track_id}")
            result = dict(row)
            result["topics"] = [item["topic_id"] for item in conn.execute(
                "SELECT topic_id FROM track_topics WHERE track_id=?", (track_id,)
            )]
            result["phases"] = [dict(item) for item in conn.execute(
                "SELECT * FROM track_phase_status WHERE track_id=? ORDER BY phase", (track_id,)
            )]
        result["foundation_updates"] = self.check_foundation_updates(slug, track_id)
        return result

    def associate_track_topic(self, slug: str, track_id: str, topic_id: str) -> dict[str, Any]:
        self.get_track(slug, track_id)
        self.get_topic(topic_id)
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            project_topic = conn.execute(
                "SELECT 1 FROM project_topics WHERE topic_id=?", (topic_id,)
            ).fetchone()
            if project_topic is None:
                raise ValueError("A track topic must first be associated with its project")
            conn.execute(
                "INSERT OR IGNORE INTO track_topics(track_id,topic_id,created_at) VALUES(?,?,?)",
                (track_id, topic_id, _now()),
            )
        return self.get_track(slug, track_id)

    def update_track_progress(
        self, slug: str, track_id: str, payload: TrackProgressInput
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        self.get_track(slug, track_id)
        with transaction(path) as conn:
            current = conn.execute(
                "SELECT revision FROM track_phase_status WHERE track_id=? AND phase=?",
                (track_id, payload.phase),
            ).fetchone()
            revision = int(current["revision"]) if current else 1
            if revision != payload.expected_revision:
                raise RevisionConflictError("Track phase revision changed")
            next_revision = revision + 1 if current else 1
            conn.execute(
                """INSERT INTO track_phase_status(track_id,phase,status,blocker,revision,updated_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(track_id,phase) DO UPDATE SET
                   status=excluded.status,blocker=excluded.blocker,revision=excluded.revision,
                   updated_at=excluded.updated_at""",
                (track_id, payload.phase, payload.status, payload.blocker, next_revision, _now()),
            )
        return self.get_track(slug, track_id)

    def publish_foundation(
        self, payload: FoundationVersionInput, foundation_id: str | None = None
    ) -> dict[str, Any]:
        for paper_id in payload.paper_ids:
            self.get_paper(paper_id)
        for topic_id in payload.topic_ids:
            self.get_topic(topic_id)
        body = payload.model_dump(mode="json")
        digest = hashlib.sha256(_json(body).encode("utf-8")).hexdigest()
        timestamp = _now()
        with transaction(self.catalog_path) as conn:
            if foundation_id is None:
                foundation_id = new_id("foundation")
                conn.execute(
                    "INSERT INTO foundations(foundation_id,title,created_at) VALUES(?,?,?)",
                    (foundation_id, payload.title, timestamp),
                )
            elif conn.execute(
                "SELECT 1 FROM foundations WHERE foundation_id=?", (foundation_id,)
            ).fetchone() is None:
                raise NotFoundError(f"Unknown foundation: {foundation_id}")
            duplicate = conn.execute(
                """SELECT version FROM foundation_versions
                   WHERE foundation_id=? AND content_digest=?""",
                (foundation_id, digest),
            ).fetchone()
            if duplicate:
                raise RevisionConflictError("This immutable foundation content is already published")
            version = conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM foundation_versions WHERE foundation_id=?",
                (foundation_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO foundation_versions VALUES(?,?,?,?,?)",
                (foundation_id, version, _json(body), digest, timestamp),
            )
            for topic_id in payload.topic_ids:
                conn.execute(
                    "INSERT INTO foundation_topics VALUES(?,?,?)",
                    (foundation_id, version, topic_id),
                )
        return self.get_foundation_version(foundation_id, version)

    def get_foundation_version(self, foundation_id: str, version: int) -> dict[str, Any]:
        with transaction(self.catalog_path) as conn:
            row = conn.execute(
                "SELECT * FROM foundation_versions WHERE foundation_id=? AND version=?",
                (foundation_id, version),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown foundation version: {foundation_id} v{version}")
            result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def adopt_foundation(
        self, slug: str, track_id: str, foundation_id: str, version: int
    ) -> dict[str, Any]:
        self.get_track(slug, track_id)
        foundation = self.get_foundation_version(foundation_id, version)
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            existing = conn.execute(
                """SELECT * FROM adopted_foundations
                   WHERE track_id=? AND foundation_id=? AND foundation_version=?""",
                (track_id, foundation_id, version),
            ).fetchone()
            if existing is None:
                adoption_id = new_id("adoption")
                conn.execute(
                    "INSERT INTO adopted_foundations VALUES(?,?,?,?,?,?,?)",
                    (
                        adoption_id,
                        track_id,
                        foundation_id,
                        version,
                        foundation["content_digest"],
                        _json(foundation),
                        _now(),
                    ),
                )
                existing = conn.execute(
                    "SELECT * FROM adopted_foundations WHERE adoption_id=?", (adoption_id,)
                ).fetchone()
        result = dict(existing)
        result["snapshot"] = json.loads(result.pop("snapshot_json"))
        return result

    def check_foundation_updates(self, slug: str, track_id: str) -> list[dict[str, Any]]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            adoptions = conn.execute(
                "SELECT foundation_id,MAX(foundation_version) AS version FROM adopted_foundations "
                "WHERE track_id=? GROUP BY foundation_id",
                (track_id,),
            ).fetchall()
        updates: list[dict[str, Any]] = []
        with transaction(self.catalog_path) as conn:
            for adopted in adoptions:
                latest = conn.execute(
                    "SELECT MAX(version) FROM foundation_versions WHERE foundation_id=?",
                    (adopted["foundation_id"],),
                ).fetchone()[0]
                if latest and latest > adopted["version"]:
                    updates.append(
                        {
                            "foundation_id": adopted["foundation_id"],
                            "adopted_version": adopted["version"],
                            "latest_version": latest,
                        }
                    )
        return updates

    def adopt_foundation_update(
        self, slug: str, track_id: str, foundation_id: str, version: int
    ) -> dict[str, Any]:
        adoption = self.adopt_foundation(slug, track_id, foundation_id, version)
        path = self._require_project_path(slug)
        timestamp = _now()
        with transaction(path) as conn:
            conn.execute(
                """UPDATE research_nodes SET status='STALE',revision=revision+1,updated_at=?
                   WHERE track_id=? AND status='APPROVED'""",
                (timestamp, track_id),
            )
            conn.execute(
                """UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=?
                   WHERE track_id=?""",
                (timestamp, track_id),
            )
        return adoption

    def search_literature(
        self,
        query: str,
        *,
        providers: list[str] | None = None,
        limit_per_provider: int = 10,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("query is required")
        results = search_all(query, providers=providers, limit_per_provider=limit_per_provider)
        timestamp = _now()
        with transaction(self.catalog_path) as conn:
            for result in results:
                retrieval_id = new_id("retrieval")
                conn.execute(
                    "INSERT INTO retrieval_runs(retrieval_id,query,provider,status,detail,started_at,completed_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        retrieval_id,
                        query,
                        result.provider,
                        "FAILED" if result.error else "COMPLETED",
                        result.error,
                        timestamp,
                        timestamp,
                    ),
                )
        return [
            {
                "provider": item.provider,
                "error": item.error,
                "candidates": [candidate.model_dump(mode="json") for candidate in item.candidates],
            }
            for item in results
        ]

    def ingest_candidates(self, candidates: Iterable[SourceCandidate]) -> list[dict[str, Any]]:
        ingested: list[dict[str, Any]] = []
        with transaction(self.catalog_path) as conn:
            for candidate in candidates:
                ingested.append(self._upsert_candidate(conn, candidate))
        return ingested

    def register_local_pdf(self, paper_id: str, local_path: str) -> dict[str, Any]:
        path = Path(local_path).resolve()
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            raise ValueError("local_path must be an existing PDF")
        with transaction(self.catalog_path) as conn:
            row = conn.execute(
                "SELECT paper_id FROM papers WHERE paper_id=?", (paper_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown paper: {paper_id}")
            conn.execute(
                "UPDATE papers SET pdf_url=?, updated_at=? WHERE paper_id=?",
                (str(path), _now(), paper_id),
            )
        return self.get_paper(paper_id)

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        with transaction(self.catalog_path) as conn:
            return self._get_paper_with_conn(conn, paper_id)

    def list_papers(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with transaction(self.catalog_path) as conn:
            rows = conn.execute(
                "SELECT * FROM papers ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(row), "authors": json.loads(row["authors_json"])} for row in rows]

    def add_evidence(self, slug: str, payload: EvidenceInput) -> dict[str, Any]:
        self.get_paper(payload.paper_id)
        path = self._require_project_path(slug)
        evidence_id = new_id("evidence")
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO evidence(evidence_id,paper_id,statement,excerpt,location,relation,confidence,extractor_model,prompt_version,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidence_id,
                    payload.paper_id,
                    payload.statement,
                    payload.excerpt,
                    payload.location,
                    payload.relation.value,
                    payload.confidence,
                    payload.extractor_model,
                    payload.prompt_version,
                    _now(),
                ),
            )
        return self.get_evidence(slug, evidence_id)

    def get_evidence(self, slug: str, evidence_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute(
                "SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown evidence: {evidence_id}")
        result = dict(row)
        result["paper"] = self.get_paper(result["paper_id"])
        return result

    def propose_decision(self, slug: str, payload: DecisionProposalInput) -> dict[str, Any]:
        path = self._require_project_path(slug)
        track_id = self._resolve_track(path, payload.track_id)
        for evidence_id in payload.evidence_ids:
            self.get_evidence(slug, evidence_id)
        upstream_rows = [self._require_node(path, upstream) for upstream in payload.upstream_node_ids]
        if payload.kind.value == "idea" and any(
            row["node_type"] != "gap" or row["status"] != DecisionStatus.APPROVED.value
            for row in upstream_rows
        ):
            raise ValueError("Every upstream node for an idea must be an approved gap")
        if payload.supersedes_node_id:
            self._require_node(path, payload.supersedes_node_id)
        node_id = new_id(payload.kind.value)
        proposal_id = new_id("proposal")
        timestamp = _now()
        approval_phrase = f"APPROVE {proposal_id}"
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO research_nodes(node_id,node_type,status,statement,rationale,payload_json,revision,created_at,updated_at,track_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    node_id,
                    payload.kind.value,
                    DecisionStatus.PROPOSED.value,
                    payload.statement,
                    payload.rationale,
                    _json(
                        {
                            "evidence_ids": payload.evidence_ids,
                            "upstream_node_ids": payload.upstream_node_ids,
                        }
                    ),
                    1,
                    timestamp,
                    timestamp,
                    track_id,
                ),
            )
            conn.execute(
                """INSERT INTO decisions(proposal_id,node_id,kind,status,approval_phrase,expected_revision,supersedes_node_id,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    proposal_id,
                    node_id,
                    payload.kind.value,
                    DecisionStatus.PROPOSED.value,
                    approval_phrase,
                    1,
                    payload.supersedes_node_id,
                    timestamp,
                ),
            )
            for evidence_id in payload.evidence_ids:
                conn.execute(
                    "INSERT INTO node_evidence(node_id,evidence_id) VALUES(?,?)",
                    (node_id, evidence_id),
                )
            for upstream in payload.upstream_node_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO research_edges(edge_id,source_node_id,target_node_id,relation,created_at) VALUES(?,?,?,?,?)",
                    (new_id("edge"), upstream, node_id, "MOTIVATES", timestamp),
                )
        return self.get_decision(slug, proposal_id)

    def get_decision(self, slug: str, proposal_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
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

    def list_pending_decisions(self, slug: str) -> list[dict[str, Any]]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            ids = [
                row["proposal_id"]
                for row in conn.execute(
                    "SELECT proposal_id FROM decisions WHERE status='PROPOSED' ORDER BY created_at"
                ).fetchall()
            ]
        return [self.get_decision(slug, proposal_id) for proposal_id in ids]

    def approve_scientific_decision(
        self,
        slug: str,
        proposal_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        timestamp = _now()
        with transaction(path) as conn:
            decision = conn.execute(
                "SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            if decision is None:
                raise NotFoundError(f"Unknown proposal: {proposal_id}")
            if decision["status"] != DecisionStatus.PROPOSED.value:
                raise RevisionConflictError("Only a pending proposal can be approved")
            if decision["expected_revision"] != expected_revision:
                raise RevisionConflictError(
                    "Proposal revision changed; re-read the proposal before approving"
                )
            node = self._require_node(conn, decision["node_id"])
            if node["revision"] != expected_revision:
                raise RevisionConflictError(
                    "Node revision changed; re-read the proposal before approving"
                )
            grant = consume_grant(
                conn,
                proposal_id=proposal_id,
                proposal_type="decision",
                revision=expected_revision,
            )
            confirmation = _json(
                {
                    "grant_id": grant["grant_id"],
                    "profile": grant["profile"],
                    "session_id": grant["session_id"],
                    "message_id": grant["message_id"],
                }
            )
            conn.execute(
                "UPDATE decisions SET status=?,confirmation_text=?,resolved_at=? WHERE proposal_id=?",
                (DecisionStatus.APPROVED.value, confirmation, timestamp, proposal_id),
            )
            conn.execute(
                "UPDATE research_nodes SET status=?,updated_at=? WHERE node_id=?",
                (DecisionStatus.APPROVED.value, timestamp, decision["node_id"]),
            )
            if decision["supersedes_node_id"]:
                self._supersede_and_mark_stale(conn, decision["supersedes_node_id"], timestamp)
        return self.get_decision(slug, proposal_id)

    def propose_experiment_plan(self, slug: str, payload: ExperimentPlanInput) -> dict[str, Any]:
        path = self._require_project_path(slug)
        method = self._require_node(path, payload.method_node_id)
        if method["node_type"] != "method" or method["status"] != DecisionStatus.APPROVED.value:
            raise ValueError("Experiment plans require a currently approved method node")
        project_dir = path.parent.resolve()
        working_directory = (project_dir / payload.working_directory).resolve()
        if working_directory != project_dir and project_dir not in working_directory.parents:
            raise ValueError("working_directory must remain inside the RSTV4 project directory")
        script_path: str | None = None
        if payload.script_path:
            script = (working_directory / payload.script_path).resolve()
            if script != working_directory and working_directory not in script.parents:
                raise ValueError("script_path must remain inside working_directory")
            if not script.is_file():
                raise ValueError("script_path must identify an existing file")
            digest = hashlib.sha256(script.read_bytes()).hexdigest()
            if digest != payload.script_sha256:
                raise ValueError("script_sha256 does not match the current script")
            script_path = str(script)
        plan_id = new_id("experiment_plan")
        proposal_id = new_id("proposal")
        timestamp = _now()
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO experiment_plans(
                   plan_id,proposal_id,method_node_id,status,revision,argv_json,
                   working_directory,script_path,script_sha256,timeout_seconds,
                   metrics_json_path,created_at,track_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    plan_id,
                    proposal_id,
                    payload.method_node_id,
                    DecisionStatus.PROPOSED.value,
                    1,
                    _json(payload.argv),
                    str(working_directory),
                    script_path,
                    payload.script_sha256,
                    payload.timeout_seconds,
                    payload.metrics_json_path,
                    timestamp,
                    method["track_id"],
                ),
            )
        return self.get_experiment_plan(slug, plan_id)

    def get_experiment_plan(self, slug: str, plan_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute(
                "SELECT * FROM experiment_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown experiment plan: {plan_id}")
        result = dict(row)
        result["argv"] = json.loads(result.pop("argv_json"))
        result["approval_phrase"] = f"APPROVE {result['proposal_id']}"
        return result

    def approve_experiment_plan(
        self, slug: str, plan_id: str, expected_revision: int
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            plan = conn.execute(
                "SELECT * FROM experiment_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
            if plan is None:
                raise NotFoundError(f"Unknown experiment plan: {plan_id}")
            if plan["status"] != DecisionStatus.PROPOSED.value:
                raise RevisionConflictError("Only a pending experiment plan can be approved")
            if plan["revision"] != expected_revision:
                raise RevisionConflictError("Experiment plan revision changed")
            method = self._require_node(conn, plan["method_node_id"])
            if method["status"] != DecisionStatus.APPROVED.value:
                raise RevisionConflictError("The experiment method is no longer approved")
            consume_grant(
                conn,
                proposal_id=plan["proposal_id"],
                proposal_type="experiment_plan",
                revision=expected_revision,
            )
            conn.execute(
                "UPDATE experiment_plans SET status=?,approved_at=? WHERE plan_id=?",
                (DecisionStatus.APPROVED.value, _now(), plan_id),
            )
        return self.get_experiment_plan(slug, plan_id)

    def reject_scientific_decision(
        self, slug: str, proposal_id: str, reason: str
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            decision = conn.execute(
                "SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            if decision is None:
                raise NotFoundError(f"Unknown proposal: {proposal_id}")
            if decision["status"] != DecisionStatus.PROPOSED.value:
                raise RevisionConflictError("Only a pending proposal can be rejected")
            timestamp = _now()
            conn.execute(
                "UPDATE decisions SET status=?,rejection_reason=?,resolved_at=? WHERE proposal_id=?",
                (DecisionStatus.REJECTED.value, reason, timestamp, proposal_id),
            )
            conn.execute(
                "UPDATE research_nodes SET status=?,updated_at=? WHERE node_id=?",
                (DecisionStatus.REJECTED.value, timestamp, decision["node_id"]),
            )
        return self.get_decision(slug, proposal_id)

    def trace_provenance(self, slug: str, node_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        self._require_node(path, node_id)
        with transaction(path) as conn:
            evidence_rows = conn.execute(
                "SELECT evidence_id FROM node_evidence WHERE node_id=?", (node_id,)
            ).fetchall()
            upstream = conn.execute(
                "SELECT source_node_id,relation FROM research_edges WHERE target_node_id=?",
                (node_id,),
            ).fetchall()
        return {
            "node_id": node_id,
            "evidence": [self.get_evidence(slug, row["evidence_id"]) for row in evidence_rows],
            "upstream": [dict(row) for row in upstream],
        }

    def impact_analysis(self, slug: str, node_id: str) -> list[dict[str, Any]]:
        path = self._require_project_path(slug)
        self._require_node(path, node_id)
        with transaction(path) as conn:
            pending = deque([node_id])
            seen = {node_id}
            impacted: list[dict[str, Any]] = []
            while pending:
                current = pending.popleft()
                rows = conn.execute(
                    """SELECT n.node_id,n.node_type,n.status,n.statement,n.revision FROM research_edges e
                       JOIN research_nodes n ON n.node_id=e.target_node_id WHERE e.source_node_id=?""",
                    (current,),
                ).fetchall()
                for row in rows:
                    if row["node_id"] not in seen:
                        seen.add(row["node_id"])
                        pending.append(row["node_id"])
                        impacted.append(dict(row))
        return impacted

    def build_blueprint(self, slug: str, track_id: str | None = None) -> dict[str, Any]:
        path = self._require_project_path(slug)
        project = self.get_project(slug)
        track_id = self._resolve_track(path, track_id)
        track = self.get_track(slug, track_id)
        with transaction(path) as conn:
            rows = conn.execute(
                """SELECT node_id,node_type,statement,rationale,payload_json,revision
                   FROM research_nodes WHERE status='APPROVED' AND track_id=? ORDER BY created_at""",
                (track_id,),
            ).fetchall()
            stale = conn.execute(
                """SELECT node_id,node_type,statement FROM research_nodes
                   WHERE status='STALE' AND track_id=? ORDER BY updated_at""",
                (track_id,),
            ).fetchall()
            payload = {
                "project": project,
                "track": track,
                "approved": [
                    {
                        **dict(row),
                        "payload": json.loads(row["payload_json"]),
                        "provenance": self._provenance_with_conn(conn, slug, row["node_id"]),
                    }
                    for row in rows
                ],
                "stale_objects": [dict(row) for row in stale],
            }
        return payload

    def snapshot_blueprint(self, slug: str, track_id: str | None = None) -> dict[str, Any]:
        path = self._require_project_path(slug)
        track_id = self._resolve_track(path, track_id)
        payload = self.build_blueprint(slug, track_id)
        with transaction(path) as conn:
            revision = conn.execute(
                """SELECT COALESCE(MAX(revision),0)+1 FROM blueprint_snapshots
                   WHERE track_id=?""",
                (track_id,),
            ).fetchone()[0]
            blueprint_id = new_id("blueprint")
            conn.execute(
                """INSERT INTO blueprint_snapshots(
                   blueprint_id,track_id,revision,payload_json,created_at) VALUES(?,?,?,?,?)""",
                (blueprint_id, track_id, revision, _json(payload), _now()),
            )
        return {"blueprint_id": blueprint_id, "revision": revision, **payload}

    def render_blueprint(self, slug: str, track_id: str | None = None) -> str:
        blueprint = self.build_blueprint(slug, track_id)
        project = blueprint["project"]
        lines = [f"# {project['title']}", "", "## Research Blueprint", ""]
        lines += [
            f"- Project: `{project['project_id']}`",
            f"- Research type: `{project['research_type']}`",
            f"- Field: {project['field']}",
            f"- Track: `{blueprint['track']['track_id']}` — {blueprint['track']['title']}",
        ]
        if project.get("scope"):
            lines.append(f"- Scope: {project['scope']}")
        for node in blueprint["approved"]:
            lines += [
                "",
                f"## {node['node_type'].replace('_', ' ').title()}",
                "",
                node["statement"],
                "",
                f"Rationale: {node['rationale']}",
            ]
            if node["provenance"]["evidence"]:
                lines += ["", "Evidence:"]
                lines += [
                    f"- `{item['evidence_id']}` — {item['statement']} ({item['paper']['title']}, {item['location']})"
                    for item in node["provenance"]["evidence"]
                ]
        if blueprint["stale_objects"]:
            lines += ["", "## Requires review", ""]
            lines += [
                f"- `{item['node_id']}` {item['node_type']}: {item['statement']}"
                for item in blueprint["stale_objects"]
            ]
        return "\n".join(lines) + "\n"

    def _upsert_candidate(self, conn: Any, candidate: SourceCandidate) -> dict[str, Any]:
        key = _paper_key(candidate)
        timestamp = _now()
        row = conn.execute(
            "SELECT paper_id FROM papers WHERE canonical_key=? OR (doi IS NOT NULL AND doi=?)",
            (key, candidate.doi),
        ).fetchone()
        if row:
            paper_id = row["paper_id"]
            conn.execute(
                """UPDATE papers SET title=?,authors_json=?,published_year=?,abstract=COALESCE(?,abstract),landing_url=COALESCE(?,landing_url),pdf_url=COALESCE(?,pdf_url),updated_at=? WHERE paper_id=?""",
                (
                    candidate.title,
                    _json(candidate.authors),
                    candidate.published_year,
                    candidate.abstract,
                    candidate.landing_url,
                    candidate.pdf_url,
                    timestamp,
                    paper_id,
                ),
            )
        else:
            paper_id = new_id("paper")
            conn.execute(
                """INSERT INTO papers(paper_id,canonical_key,doi,normalized_title,title,authors_json,published_year,abstract,landing_url,pdf_url,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    paper_id,
                    key,
                    candidate.doi,
                    _normalized_title(candidate.title),
                    candidate.title,
                    _json(candidate.authors),
                    candidate.published_year,
                    candidate.abstract,
                    candidate.landing_url,
                    candidate.pdf_url,
                    timestamp,
                    timestamp,
                ),
            )
        if candidate.external_id:
            existing = conn.execute(
                "SELECT paper_source_id FROM paper_sources WHERE provider=? AND external_id=?",
                (candidate.source_provider, candidate.external_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO paper_sources(paper_source_id,paper_id,provider,external_id,retrieved_at,raw_json) VALUES(?,?,?,?,?,?)",
                    (
                        new_id("paper_source"),
                        paper_id,
                        candidate.source_provider,
                        candidate.external_id,
                        timestamp,
                        _json(candidate.raw),
                    ),
                )
        return self._get_paper_with_conn(conn, paper_id)

    def _project_path(self, slug: str) -> Path:
        return self.projects_root / slug / "research.db"

    def _require_project_path(self, slug: str) -> Path:
        path = self._project_path(slug)
        if not path.exists():
            raise NotFoundError(f"Unknown project: {slug}")
        return path

    def _catalog_object(self, table: str, key: str, value: str) -> dict[str, Any]:
        if (table, key) not in {("research_fields", "field_id"), ("topics", "topic_id")}:
            raise ValueError("Unsupported catalog object")
        with transaction(self.catalog_path) as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown catalog object: {value}")
        return dict(row)

    @staticmethod
    def _resolve_track(path: Path, track_id: str | None) -> str:
        with transaction(path) as conn:
            if track_id:
                row = conn.execute(
                    "SELECT track_id FROM research_tracks WHERE track_id=?", (track_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError(f"Unknown research track: {track_id}")
                return track_id
            rows = conn.execute("SELECT track_id FROM research_tracks ORDER BY created_at").fetchall()
        if len(rows) != 1:
            raise ValueError("track_id is required when a project has multiple research tracks")
        return rows[0]["track_id"]

    @staticmethod
    def _get_paper_with_conn(conn: Any, paper_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown paper: {paper_id}")
        sources = conn.execute(
            "SELECT provider,external_id,retrieved_at FROM paper_sources WHERE paper_id=? ORDER BY retrieved_at",
            (paper_id,),
        ).fetchall()
        result = dict(row)
        result["authors"] = json.loads(result.pop("authors_json"))
        result["sources"] = [dict(item) for item in sources]
        return result

    @staticmethod
    def _require_node(connection_or_path: Any, node_id: str) -> Any:
        if isinstance(connection_or_path, Path):
            with transaction(connection_or_path) as conn:
                row = conn.execute(
                    "SELECT * FROM research_nodes WHERE node_id=?", (node_id,)
                ).fetchone()
        else:
            row = connection_or_path.execute(
                "SELECT * FROM research_nodes WHERE node_id=?", (node_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown research node: {node_id}")
        return row

    def _supersede_and_mark_stale(self, conn: Any, node_id: str, timestamp: str) -> None:
        conn.execute(
            "UPDATE research_nodes SET status=?,revision=revision+1,updated_at=? WHERE node_id=?",
            (DecisionStatus.SUPERSEDED.value, timestamp, node_id),
        )
        self._mark_manuscripts_for_review(conn, node_id, timestamp)
        pending = deque([node_id])
        seen = {node_id}
        while pending:
            current = pending.popleft()
            for row in conn.execute(
                "SELECT target_node_id FROM research_edges WHERE source_node_id=?", (current,)
            ).fetchall():
                target = row["target_node_id"]
                if target in seen:
                    continue
                seen.add(target)
                pending.append(target)
                conn.execute(
                    "UPDATE research_nodes SET status=?,revision=revision+1,updated_at=? WHERE node_id=? AND status='APPROVED'",
                    (DecisionStatus.STALE.value, timestamp, target),
                )
                self._mark_manuscripts_for_review(conn, target, timestamp)

    @staticmethod
    def _mark_manuscripts_for_review(conn: Any, node_id: str, timestamp: str) -> None:
        conn.execute(
            """UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=?
               WHERE manuscript_id IN (
                 SELECT manuscript_id FROM manuscript_nodes WHERE node_id=?
               )""",
            (timestamp, node_id),
        )

    def _provenance_with_conn(self, conn: Any, slug: str, node_id: str) -> dict[str, Any]:
        evidence_rows = conn.execute(
            "SELECT evidence_id FROM node_evidence WHERE node_id=?", (node_id,)
        ).fetchall()
        upstream = conn.execute(
            "SELECT source_node_id,relation FROM research_edges WHERE target_node_id=?", (node_id,)
        ).fetchall()
        assessments = conn.execute(
            "SELECT * FROM evidence_assessments WHERE claim_node_id=? ORDER BY created_at",
            (node_id,),
        ).fetchall()
        return {
            "evidence": [self.get_evidence(slug, row["evidence_id"]) for row in evidence_rows],
            "upstream": [dict(row) for row in upstream],
            "assessments": [dict(row) for row in assessments],
        }

    @staticmethod
    def _decode_project(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["type_payload"] = json.loads(result.pop("type_payload_json"))
        return result

    def run_experiment(
        self,
        slug: str,
        plan_id: str,
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        plan = self.get_experiment_plan(slug, plan_id)
        if plan["status"] != DecisionStatus.APPROVED.value:
            raise PermissionError("Only an approved experiment plan may run")
        method = self._require_node(path, plan["method_node_id"])
        if method["status"] != DecisionStatus.APPROVED.value:
            raise PermissionError("The experiment plan's method is no longer approved")
        if plan.get("script_path"):
            script = Path(plan["script_path"])
            if (
                not script.is_file()
                or hashlib.sha256(script.read_bytes()).hexdigest() != plan["script_sha256"]
            ):
                raise RevisionConflictError("The approved experiment script changed")
        runner = ExperimentRunner(path)
        res = runner.run_script(
            plan["argv"],
            cwd=plan["working_directory"],
            timeout=plan["timeout_seconds"],
            metrics_json_path=plan["metrics_json_path"],
        )
        with transaction(path) as conn:
            conn.execute(
                "UPDATE pipeline_runs SET track_id=? WHERE run_id=?",
                (plan["track_id"], res.run_id),
            )
        return {
            "run_id": res.run_id,
            "plan_id": plan_id,
            "argv": res.command,
            "exit_code": res.exit_code,
            "duration_seconds": round(res.duration_seconds, 2),
            "stdout_preview": res.stdout[:1000],
            "stderr_preview": res.stderr[:1000],
            "metrics": res.metrics,
        }

    def record_experiment_evidence(
        self,
        slug: str,
        run_id: str,
        statement: str,
        *,
        metric_key: str | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute("SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown pipeline run: {run_id}")
        detail = json.loads(row["detail_json"])
        metrics = detail.get("metrics", {})
        exit_code = detail.get("exit_code", 0)
        command_argv = detail.get("argv", [run_id])

        paper_id = f"run:{run_id}"
        timestamp = _now()
        with transaction(self.catalog_path) as cat_conn:
            existing = cat_conn.execute(
                "SELECT paper_id FROM papers WHERE paper_id=?", (paper_id,)
            ).fetchone()
            if not existing:
                cat_conn.execute(
                    """INSERT INTO papers(paper_id, canonical_key, doi, normalized_title, title, authors_json, published_year, abstract, landing_url, pdf_url, created_at, updated_at)
                       VALUES(?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                    (
                        paper_id,
                        paper_id,
                        f"experimentrun{run_id}",
                        f"Empirical Run: {_json(command_argv)}",
                        json.dumps(["Local Empirical Benchmark"]),
                        datetime.now(UTC).year,
                        f"Execution output metrics: {json.dumps(metrics)}",
                        timestamp,
                        timestamp,
                    ),
                )

        res = ExperimentResult(
            run_id=run_id,
            command=command_argv,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_seconds=detail.get("duration", 0.0),
            output_files=[],
            metrics=metrics,
        )
        runner = ExperimentRunner(path)
        evidence_input = runner.convert_result_to_evidence(
            res, statement=statement, metric_key=metric_key, confidence=confidence
        )
        return self.add_evidence(slug, evidence_input)

    def assess_claim_evidence(self, slug: str, payload: EvidenceAssessmentInput) -> dict[str, Any]:
        path = self._require_project_path(slug)
        claim = self._require_node(path, payload.claim_node_id)
        if claim["node_type"] != "claim":
            raise ValueError("claim_node_id must identify a claim")
        evidence = self.get_evidence(slug, payload.evidence_id)
        with transaction(path) as conn:
            linked = conn.execute(
                "SELECT 1 FROM node_evidence WHERE node_id=? AND evidence_id=?",
                (payload.claim_node_id, payload.evidence_id),
            ).fetchone()
        if linked is None:
            raise ValueError("The evidence must already be linked to the claim")
        for counterevidence_id in payload.counterevidence_ids:
            self.get_evidence(slug, counterevidence_id)
        digest = hashlib.sha256(
            _json(
                {
                    "statement": evidence["statement"],
                    "excerpt": evidence["excerpt"],
                    "location": evidence["location"],
                }
            ).encode("utf-8")
        ).hexdigest()
        assessment_id = new_id("assessment")
        with transaction(path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO evidence_assessments(
                   assessment_id,claim_node_id,evidence_id,verdict,rationale,conditions_json,
                   counterevidence_json,assessor_model,prompt_version,evidence_digest,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    assessment_id,
                    payload.claim_node_id,
                    payload.evidence_id,
                    payload.verdict.value,
                    payload.rationale,
                    _json(payload.conditions),
                    _json(payload.counterevidence_ids),
                    payload.assessor_model,
                    payload.prompt_version,
                    digest,
                    _now(),
                ),
            )
            row = conn.execute(
                """SELECT * FROM evidence_assessments
                   WHERE claim_node_id=? AND evidence_id=? AND assessor_model=?
                   AND prompt_version=? AND evidence_digest=?""",
                (
                    payload.claim_node_id,
                    payload.evidence_id,
                    payload.assessor_model,
                    payload.prompt_version,
                    digest,
                ),
            ).fetchone()
        result = dict(row)
        result["conditions"] = json.loads(result.pop("conditions_json"))
        result["counterevidence_ids"] = json.loads(result.pop("counterevidence_json"))
        return result

    def create_manuscript(self, slug: str, payload: ManuscriptInput) -> dict[str, Any]:
        path = self._require_project_path(slug)
        track = self.get_track(slug, payload.track_id)
        nodes = [self._require_node(path, node_id) for node_id in payload.node_ids]
        evidence_items = [self.get_evidence(slug, item) for item in payload.evidence_ids]
        manuscript_id = new_id("manuscript")
        timestamp = _now()
        research_type = payload.research_type.value if payload.research_type else track["research_type"]
        sections = {
            node_id: section
            for section, node_ids in payload.section_map.items()
            for node_id in node_ids
        }
        with transaction(path) as conn:
            conn.execute(
                """INSERT INTO manuscripts(
                   manuscript_id,track_id,title,scope,research_type,writing_status,
                   needs_scientific_review,revision,created_at,updated_at)
                   VALUES(?,?,?,?,?,'PLANNING',0,1,?,?)""",
                (manuscript_id, payload.track_id, payload.title, payload.scope, research_type,
                 timestamp, timestamp),
            )
            for node in nodes:
                conn.execute(
                    "INSERT INTO manuscript_nodes VALUES(?,?,?,?)",
                    (manuscript_id, node["node_id"], sections.get(node["node_id"]), node["revision"]),
                )
            for evidence in evidence_items:
                digest = hashlib.sha256(
                    _json({key: evidence[key] for key in ("statement", "excerpt", "location")})
                    .encode("utf-8")
                ).hexdigest()
                conn.execute(
                    "INSERT INTO manuscript_evidence VALUES(?,?,?)",
                    (manuscript_id, evidence["evidence_id"], digest),
                )
            conn.execute(
                "INSERT INTO manuscript_status_history VALUES(?,?,?,?,?,?,?,?)",
                (new_id("history"), manuscript_id, "PLANNING", None, None,
                 "Manuscript created", 1, timestamp),
            )
        return self.get_manuscript(slug, manuscript_id)

    def bind_manuscript_content(
        self, slug: str, manuscript_id: str, payload: ManuscriptBindingInput
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        manuscript = self.get_manuscript(slug, manuscript_id)
        if manuscript["revision"] != payload.expected_revision:
            raise RevisionConflictError("Manuscript revision changed")
        nodes = [self._require_node(path, node_id) for node_id in payload.node_ids]
        evidence_items = [self.get_evidence(slug, item) for item in payload.evidence_ids]
        sections = {
            node_id: section
            for section, node_ids in payload.section_map.items()
            for node_id in node_ids
        }
        timestamp = _now()
        with transaction(path) as conn:
            for node in nodes:
                conn.execute(
                    """INSERT INTO manuscript_nodes VALUES(?,?,?,?)
                       ON CONFLICT(manuscript_id,node_id) DO UPDATE SET
                       section=excluded.section,node_revision=excluded.node_revision""",
                    (manuscript_id, node["node_id"], sections.get(node["node_id"]), node["revision"]),
                )
            for evidence in evidence_items:
                digest = hashlib.sha256(
                    _json({key: evidence[key] for key in ("statement", "excerpt", "location")})
                    .encode("utf-8")
                ).hexdigest()
                conn.execute(
                    "INSERT OR IGNORE INTO manuscript_evidence VALUES(?,?,?)",
                    (manuscript_id, evidence["evidence_id"], digest),
                )
            conn.execute(
                """UPDATE manuscripts SET needs_scientific_review=1,revision=revision+1,updated_at=?
                   WHERE manuscript_id=?""",
                (timestamp, manuscript_id),
            )
        return self.get_manuscript(slug, manuscript_id)

    def get_manuscript(self, slug: str, manuscript_id: str) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            row = conn.execute(
                "SELECT * FROM manuscripts WHERE manuscript_id=?", (manuscript_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown manuscript: {manuscript_id}")
            result = dict(row)
            result["nodes"] = [dict(item) for item in conn.execute(
                "SELECT * FROM manuscript_nodes WHERE manuscript_id=?", (manuscript_id,)
            )]
            result["evidence"] = [dict(item) for item in conn.execute(
                "SELECT * FROM manuscript_evidence WHERE manuscript_id=?", (manuscript_id,)
            )]
            result["versions"] = [dict(item) for item in conn.execute(
                """SELECT manuscript_version_id,version,inputs_json,created_at
                   FROM manuscript_versions WHERE manuscript_id=? ORDER BY version""",
                (manuscript_id,),
            )]
            result["status_history"] = [dict(item) for item in conn.execute(
                "SELECT * FROM manuscript_status_history WHERE manuscript_id=? ORDER BY created_at",
                (manuscript_id,),
            )]
            result["submissions"] = [dict(item) for item in conn.execute(
                "SELECT * FROM submission_events WHERE manuscript_id=? ORDER BY created_at",
                (manuscript_id,),
            )]
        return result

    def update_manuscript_status(
        self, slug: str, manuscript_id: str, payload: ManuscriptStatusInput
    ) -> dict[str, Any]:
        current = self.get_manuscript(slug, manuscript_id)
        if current["revision"] != payload.expected_revision:
            raise RevisionConflictError("Manuscript revision changed")
        revision = current["revision"] + 1
        timestamp = _now()
        with transaction(self._require_project_path(slug)) as conn:
            conn.execute(
                """UPDATE manuscripts SET writing_status=?,blocker=?,next_step=?,revision=?,updated_at=?
                   WHERE manuscript_id=?""",
                (payload.status.value, payload.blocker, payload.next_step, revision, timestamp,
                 manuscript_id),
            )
            conn.execute(
                "INSERT INTO manuscript_status_history VALUES(?,?,?,?,?,?,?,?)",
                (new_id("history"), manuscript_id, payload.status.value, payload.blocker,
                 payload.next_step, payload.reason, revision, timestamp),
            )
        return self.get_manuscript(slug, manuscript_id)

    def record_submission_event(
        self, slug: str, manuscript_id: str, payload: SubmissionEventInput
    ) -> dict[str, Any]:
        self.get_manuscript(slug, manuscript_id)
        event_id = new_id("submission")
        with transaction(self._require_project_path(slug)) as conn:
            conn.execute(
                "INSERT INTO submission_events VALUES(?,?,?,?,?,?,?)",
                (event_id, manuscript_id, payload.venue, payload.round, payload.status.value,
                 payload.detail, _now()),
            )
            row = conn.execute("SELECT * FROM submission_events WHERE event_id=?", (event_id,)).fetchone()
        return dict(row)

    def project_progress(self, slug: str) -> dict[str, Any]:
        project = self.get_project(slug)
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            tracks = [dict(row) for row in conn.execute(
                "SELECT * FROM research_tracks ORDER BY created_at"
            )]
            manuscripts = [dict(row) for row in conn.execute(
                """SELECT manuscript_id,track_id,title,writing_status,needs_scientific_review,
                   blocker,next_step,revision FROM manuscripts ORDER BY created_at"""
            )]
        return {"project": project, "tracks": tracks, "manuscripts": manuscripts}

    def compile_manuscript(
        self,
        slug: str,
        abstract: str,
        sections: list[dict[str, str]] | None = None,
        manuscript_id: str | None = None,
        track_id: str | None = None,
    ) -> str:
        project = self.get_project(slug)
        manuscript = self.get_manuscript(slug, manuscript_id) if manuscript_id else None
        selected_track = manuscript["track_id"] if manuscript else track_id
        blueprint = self.build_blueprint(slug, selected_track)
        if manuscript:
            selected_nodes = {item["node_id"] for item in manuscript["nodes"]}
            selected_evidence = {item["evidence_id"] for item in manuscript["evidence"]}
            blueprint["approved"] = [
                node for node in blueprint["approved"] if node["node_id"] in selected_nodes
            ]
        else:
            selected_evidence = None

        # Collect references from evidence in blueprint
        references: list[dict[str, Any]] = []
        seen_papers: set[str] = set()
        for node in blueprint.get("approved", []):
            for ev in node.get("provenance", {}).get("evidence", []):
                if selected_evidence is not None and ev["evidence_id"] not in selected_evidence:
                    continue
                paper = ev.get("paper")
                if paper and paper["paper_id"] not in seen_papers:
                    seen_papers.add(paper["paper_id"])
                    references.append(paper)
        if manuscript:
            for binding in manuscript["evidence"]:
                paper = self.get_evidence(slug, binding["evidence_id"])["paper"]
                if paper["paper_id"] not in seen_papers:
                    seen_papers.add(paper["paper_id"])
                    references.append(paper)

        # Build default sections from blueprint if not provided
        actual_sections = sections or []
        if not actual_sections:
            actual_sections.append(
                {
                    "title": "Introduction & Background",
                    "content": self.render_blueprint(slug, selected_track),
                }
            )

        content = ManuscriptCompiler.compile_markdown(
            title=manuscript["title"] if manuscript else project["title"],
            abstract=abstract,
            sections=actual_sections,
            references=references,
        )
        if manuscript:
            path = self._require_project_path(slug)
            inputs = {
                "track_id": selected_track,
                "node_revisions": {item["node_id"]: item["revision"] for item in blueprint["approved"]},
                "evidence_digests": {
                    item["evidence_id"]: item["evidence_digest"] for item in manuscript["evidence"]
                },
            }
            with transaction(path) as conn:
                version = conn.execute(
                    "SELECT COALESCE(MAX(version),0)+1 FROM manuscript_versions WHERE manuscript_id=?",
                    (manuscript_id,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO manuscript_versions VALUES(?,?,?,?,?,?)",
                    (new_id("manuscript_version"), manuscript_id, version, content, _json(inputs), _now()),
                )
        return content

    def verify_citations(
        self, slug: str, text: str, manuscript_id: str | None = None
    ) -> dict[str, Any]:
        path = self._require_project_path(slug)
        with transaction(path) as conn:
            if manuscript_id:
                self.get_manuscript(slug, manuscript_id)
                evidence_rows = conn.execute(
                    """SELECT e.evidence_id,e.paper_id FROM evidence e
                       JOIN manuscript_evidence me ON me.evidence_id=e.evidence_id
                       WHERE me.manuscript_id=?""",
                    (manuscript_id,),
                ).fetchall()
            else:
                evidence_rows = conn.execute("SELECT evidence_id, paper_id FROM evidence").fetchall()

        with transaction(self.catalog_path) as conn:
            if manuscript_id:
                paper_ids = [row["paper_id"] for row in evidence_rows]
                if paper_ids:
                    placeholders = ",".join("?" for _ in paper_ids)
                    paper_rows = conn.execute(
                        f"SELECT paper_id,canonical_key,doi FROM papers WHERE paper_id IN ({placeholders})",
                        paper_ids,
                    ).fetchall()
                else:
                    paper_rows = []
            else:
                paper_rows = conn.execute(
                    "SELECT paper_id, canonical_key, doi FROM papers"
                ).fetchall()

        valid_keys: set[str] = set()
        for r in evidence_rows:
            valid_keys.add(r["evidence_id"])
            valid_keys.add(r["paper_id"])
        for r in paper_rows:
            valid_keys.add(r["paper_id"])
            valid_keys.add(r["canonical_key"])
            if r["doi"]:
                valid_keys.add(r["doi"])

        resolution = CitationVerifier.verify(text, valid_keys)
        cited_evidence = [
            key for key in resolution["valid_citations"] if key.startswith("evidence_")
        ]
        assessments: list[dict[str, Any]] = []
        if cited_evidence:
            placeholders = ",".join("?" for _ in cited_evidence)
            with transaction(path) as conn:
                rows = conn.execute(
                    f"SELECT * FROM evidence_assessments WHERE evidence_id IN ({placeholders})",
                    cited_evidence,
                ).fetchall()
            assessments = [dict(row) for row in rows]
        resolution["content_assessments"] = assessments
        resolution["content_status"] = (
            "NOT_ASSESSED" if cited_evidence and not assessments else "ASSESSED"
        )
        return resolution

    def simulate_review(self, slug: str, manuscript_id: str | None = None) -> dict[str, Any]:
        manuscript = self.get_manuscript(slug, manuscript_id) if manuscript_id else None
        blueprint = self.build_blueprint(slug, manuscript["track_id"] if manuscript else None)
        if manuscript:
            selected = {item["node_id"] for item in manuscript["nodes"]}
            blueprint["approved"] = [
                node for node in blueprint["approved"] if node["node_id"] in selected
            ]
        review_report = ReviewSimulator.evaluate_blueprint(blueprint)
        rebuttal_actions = RebuttalPlanner.plan_rebuttal(review_report)
        review_report["rebuttal_proposals"] = rebuttal_actions
        return review_report
