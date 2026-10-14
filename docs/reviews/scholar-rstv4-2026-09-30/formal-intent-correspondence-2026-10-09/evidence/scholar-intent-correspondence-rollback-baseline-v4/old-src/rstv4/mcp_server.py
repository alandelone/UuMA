from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from .fieldkg_kag import FieldKGKagClient, FieldKGProjectionWorker
from .models import (
    BrowserAcquisitionInput,
    BrowserAcquisitionReceiptInput,
    CollectionCreateInput,
    CollectionScopeInput,
    CollectionSearchInput,
    DecisionProposalInput,
    DeepReadRequestInput,
    ExperimentPlanInput,
    FieldInput,
    FieldKGBuildInput,
    FieldKGGapInput,
    FieldKGReviewInput,
    JournalMetricsImportInput,
    LegacyPaperMigrationInput,
    LocalPdfImportInput,
    ManuscriptBindingInput,
    ManuscriptStatusInput,
    PdfRegistrationInput,
    SubmissionEventInput,
    TrackFirstEvidenceInput,
    TrackFirstManuscriptInput,
    TrackFirstProjectInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
    TrackMilestoneInput,
)
from .track_first import TrackFirstService

mcp = FastMCP("rstv4-worker")


@lru_cache(maxsize=1)
def service() -> TrackFirstService:
    return TrackFirstService(os.environ.get("RSTV4_ROOT"))


def _json(value: str) -> Any:
    return json.loads(value)


@mcp.tool()
def list_research_fields() -> list[dict[str, Any]]:
    """List all long-lived research Fields."""
    return service().list_fields()


@mcp.tool()
def list_research_tracks(field_id: str = "") -> list[dict[str, Any]]:
    """List research Tracks, optionally filtered by field_id."""
    return service().list_tracks(field_id or None)


@mcp.tool()
def list_research_topics(field_id: str = "") -> list[dict[str, Any]]:
    """List research Topics, optionally filtered by field_id."""
    return service().list_topics(field_id or None)


@mcp.tool()
def create_research_field(field_json: str) -> dict[str, Any]:
    """Create or resolve a long-lived research Field."""
    return service().create_field(FieldInput.model_validate(_json(field_json)))


@mcp.tool()
def create_research_topic(field_id: str, topic_json: str) -> dict[str, Any]:
    """Create or associate a Topic inside one Field."""
    return service().create_topic(
        TrackFirstTopicInput.model_validate({**_json(topic_json), "field_id": field_id})
    )


@mcp.tool()
def create_research_track(track_json: str) -> dict[str, Any]:
    """Create a Track directly below a Field and its primary Topic."""
    return service().create_track(TrackFirstTrackInput.model_validate(_json(track_json)))


@mcp.tool()
def get_research_track(track_id: str) -> dict[str, Any]:
    """Return Track-owned science, Projects, Manuscripts, milestones, and updates."""
    return service().get_track(track_id)


@mcp.tool()
def get_field_view(field_id: str) -> dict[str, Any]:
    """Return Topics, FieldKG builds, snapshots, Candidate Gaps, and Tracks."""
    return service().get_field_view(field_id)


@mcp.tool()
def create_collection(collection_json: str) -> dict[str, Any]:
    """Start or resolve one durable BibTeX/DOI collection for a Field or Track."""
    return service().paperpool.create_collection(
        CollectionCreateInput.model_validate(_json(collection_json))
    )


@mcp.tool()
def request_collection_search(collection_id: str, search_json: str) -> dict[str, Any]:
    """Queue a bounded multi-provider search and screen unique papers in the Collection."""
    return service().paperpool.request_collection_search(
        collection_id, CollectionSearchInput.model_validate(_json(search_json))
    )


@mcp.tool()
def request_reference_lookups(
    collection_id: str, paper_id: str, limit: int = 20
) -> dict[str, Any]:
    """Queue a bounded Crossref lookup for references whose PDF text has no DOI."""
    return service().paperpool.request_reference_lookups(
        collection_id, paper_id, limit=limit
    )


@mcp.tool()
def get_collection(collection_id: str) -> dict[str, Any]:
    """Return collection scope, seeds and durable processing counts."""
    return service().paperpool.get_collection(collection_id)


@mcp.tool()
def pause_collection(collection_id: str, expected_revision: int) -> dict[str, Any]:
    """Stop claiming new work after current steps checkpoint."""
    return service().paperpool.pause_collection(collection_id, expected_revision)


@mcp.tool()
def resume_collection(collection_id: str, expected_revision: int) -> dict[str, Any]:
    """Resume durable work without repeating valid completed steps."""
    return service().paperpool.resume_collection(collection_id, expected_revision)


@mcp.tool()
def update_collection_scope(collection_id: str, scope_json: str) -> dict[str, Any]:
    """Version a collection scope and enqueue new scoped screening results."""
    return service().paperpool.update_scope(
        collection_id, CollectionScopeInput.model_validate(_json(scope_json))
    )


@mcp.tool()
def list_catalog_papers(
    collection_id: str = "", limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Page canonical reference papers, optionally inside one collection."""
    return service().paperpool.list_papers(collection_id or None, limit=limit, offset=offset)


@mcp.tool()
def get_catalog_paper(paper_id: str) -> dict[str, Any]:
    """Return one paper's metadata, files, assessments and PDF references."""
    return service().paperpool.get_paper(paper_id)


@mcp.tool()
def get_processing_history(
    paper_id: str, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Page the durable step attempts for one paper."""
    return service().paperpool.get_processing_history(paper_id, limit=limit, offset=offset)


@mcp.tool()
def get_collection_frontier(
    collection_id: str, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Return outstanding work, including waits and retry times."""
    return service().paperpool.get_frontier(collection_id, limit=limit, offset=offset)


@mcp.tool()
def get_collection_failures(
    collection_id: str, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Return retry, resource, human and terminal failures."""
    return service().paperpool.get_failures(collection_id, limit=limit, offset=offset)


@mcp.tool()
def get_collection_usage(collection_id: str) -> dict[str, Any]:
    """Return recorded job and attempt counts without estimating hidden charges."""
    return service().paperpool.get_usage(collection_id)


@mcp.tool()
def request_deep_read(collection_id: str, request_json: str) -> dict[str, Any]:
    """Prioritize an explicit paper for standard-model PaperSkeleton processing."""
    return service().paperpool.request_deep_read(
        collection_id, DeepReadRequestInput.model_validate(_json(request_json))
    )


@mcp.tool()
def retry_collection_step(job_id: str, expected_fencing_token: int = -1) -> dict[str, Any]:
    """Retry only one stopped step without invalidating its successful predecessors."""
    token = expected_fencing_token if expected_fencing_token >= 0 else None
    return service().paperpool.retry_step(job_id, token)


@mcp.tool()
def register_paper_pdf(collection_id: str, pdf_json: str) -> dict[str, Any]:
    """Register and validate a PDF from a configured import directory."""
    return service().paperpool.register_pdf(
        collection_id, PdfRegistrationInput.model_validate(_json(pdf_json))
    )


@mcp.tool()
def request_browser_acquisition(collection_id: str, request_json: str) -> dict[str, Any]:
    """Create a persistent Orchestrator/Copycat handoff request for one paper."""
    return service().paperpool.request_browser_acquisition(
        collection_id, BrowserAcquisitionInput.model_validate(_json(request_json))
    )


@mcp.tool()
def list_browser_acquisition_requests(
    status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """List persistent browser handoffs for the Orchestrator."""
    return service().paperpool.list_browser_acquisition_requests(status=status, limit=limit)


@mcp.tool()
def submit_browser_acquisition_receipt(receipt_json: str) -> dict[str, Any]:
    """Record an Orchestrator/Copycat receipt and validate returned files."""
    return service().paperpool.submit_browser_acquisition_receipt(
        BrowserAcquisitionReceiptInput.model_validate(_json(receipt_json))
    )


@mcp.tool()
def get_core_candidates(
    collection_id: str, scope_kind: str = "FIELD", limit: int = 100
) -> list[dict[str, Any]]:
    """Return explainable Field- or Track-scoped citation core candidates."""
    return service().paperpool.get_core_candidates(
        collection_id, scope_kind=scope_kind, limit=limit
    )


@mcp.tool()
def get_citation_neighborhood(paper_id: str, collection_id: str = "") -> dict[str, Any]:
    """Return observed PDF citation edges around one paper."""
    return service().paperpool.get_citation_neighborhood(
        paper_id, collection_id=collection_id or None
    )


@mcp.tool()
def migrate_legacy_paperpool(migration_json: str) -> dict[str, Any]:
    """Audit and import only basic metadata and verified files from legacy PaperPool."""
    return service().paperpool.migrate_legacy_paperpool(
        LegacyPaperMigrationInput.model_validate(_json(migration_json))
    )


@mcp.tool()
def import_local_pdf_directories(import_json: str) -> dict[str, Any]:
    """Stage local PDF folders and import readable files as reviewable catalog records."""
    return service().paperpool.import_local_pdf_directories(
        LocalPdfImportInput.model_validate(_json(import_json))
    )


@mcp.tool()
def get_local_pdf_import_status() -> dict[str, Any]:
    """Summarize imported, review-needed, and iCloud-pending local PDFs."""
    return service().paperpool.local_pdf_import_status()


@mcp.tool()
def quarantine_local_pdf_parser_outputs(root_path: str) -> dict[str, int]:
    """Exclude derived parser PDFs from the visible paper catalog while preserving provenance."""
    return service().paperpool.quarantine_local_pdf_parser_outputs(root_path)


@mcp.tool()
def import_scopus_journal_metrics(import_json: str) -> dict[str, Any]:
    """Import an official Scopus CiteScore CSV with ISSN, category, quartile and CiteScore."""
    return service().paperpool.import_journal_metrics_csv(
        JournalMetricsImportInput.model_validate(_json(import_json))
    )


@mcp.tool()
def add_processed_papers_to_fieldkg_build(
    build_id: str, paper_ids_json: str
) -> dict[str, Any]:
    """Add completed canonical Skeletons to an existing FieldKG build."""
    return service().paperpool.add_processed_papers_to_fieldkg_build(
        build_id, list(_json(paper_ids_json))
    )


@mcp.tool()
def create_project(project_json: str) -> dict[str, Any]:
    """Create a bounded execution Project under exactly one Track."""
    return service().create_project(TrackFirstProjectInput.model_validate(_json(project_json)))


@mcp.tool()
def get_project(project_id: str) -> dict[str, Any]:
    """Read a Track-owned Project by stable id."""
    return service().get_project(project_id)


@mcp.tool()
def update_track_milestone(track_id: str, milestone_json: str) -> dict[str, Any]:
    """Update one independent Track research milestone with optimistic concurrency."""
    return service().update_milestone(
        track_id, TrackMilestoneInput.model_validate(_json(milestone_json))
    )


@mcp.tool()
def create_fieldkg_build(build_json: str) -> dict[str, Any]:
    """Start a versioned FieldKG build for an explicit Field and paper scope."""
    return service().create_fieldkg_build(FieldKGBuildInput.model_validate(_json(build_json)))


@mcp.tool()
def import_paperpool_batch(
    build_id: str, database_path: str, paper_ids_json: str = "[]"
) -> dict[str, Any]:
    """Read legacy PaperPool/PaperSkeleton records without modifying PaperPool."""
    return service().import_paperpool(build_id, database_path, list(_json(paper_ids_json)))


@mcp.tool()
def finish_fieldkg_build(build_id: str, expected_revision: int) -> dict[str, Any]:
    """Move a FieldKG build to human review."""
    return service().finish_fieldkg_build(build_id, expected_revision)


@mcp.tool()
def review_fieldkg_evidence(candidate_id: str, review_json: str) -> dict[str, Any]:
    """Accept or reject one candidate; acceptance creates immutable Evidence."""
    return service().review_evidence_candidate(
        candidate_id, FieldKGReviewInput.model_validate(_json(review_json))
    )


@mcp.tool()
def propose_candidate_gap(build_id: str, gap_json: str) -> dict[str, Any]:
    """Record a derived Candidate Gap in one FieldKG build."""
    return service().create_candidate_gap(
        build_id, FieldKGGapInput.model_validate(_json(gap_json))
    )


@mcp.tool()
def review_candidate_gap(candidate_gap_id: str, review_json: str) -> dict[str, Any]:
    """Review a Candidate Gap without approving it as Track science."""
    return service().review_candidate_gap(
        candidate_gap_id, FieldKGReviewInput.model_validate(_json(review_json))
    )


@mcp.tool()
def seal_fieldkg_snapshot(build_id: str, expected_revision: int) -> dict[str, Any]:
    """Seal a reviewed build as an immutable FieldKG Snapshot."""
    return service().seal_snapshot(build_id, expected_revision)


@mcp.tool()
def adopt_fieldkg_snapshot(track_id: str, snapshot_id: str) -> dict[str, Any]:
    """Adopt one immutable Snapshot without replacing older adoptions."""
    return service().adopt_snapshot(track_id, snapshot_id)


@mcp.tool()
def add_track_evidence(track_id: str, evidence_json: str) -> dict[str, Any]:
    """Record literature or experimental Evidence scoped to one Track."""
    return service().add_evidence(
        TrackFirstEvidenceInput.model_validate({**_json(evidence_json), "track_id": track_id})
    )


@mcp.tool()
def propose_scientific_decision(track_id: str, proposal_json: str) -> dict[str, Any]:
    """Create an unapproved scientific decision inside one Track."""
    return service().propose_decision(
        track_id,
        DecisionProposalInput.model_validate({**_json(proposal_json), "track_id": track_id}),
    )


@mcp.tool()
def approve_scientific_decision(proposal_id: str, expected_revision: int) -> dict[str, Any]:
    """Consume an exact user-message grant for one proposal revision."""
    return service().approve_decision(proposal_id, expected_revision)


@mcp.tool()
def get_blueprint(track_id: str) -> dict[str, Any]:
    """Read current approved Track state without creating a snapshot."""
    return service().build_blueprint(track_id)


@mcp.tool()
def snapshot_blueprint(track_id: str) -> dict[str, Any]:
    """Explicitly save an immutable numbered Blueprint snapshot for one Track."""
    return service().snapshot_blueprint(track_id)


@mcp.tool()
def trace_research_provenance(node_id: str) -> dict[str, Any]:
    """Trace Evidence and upstream dependencies for one research node."""
    return service().trace_provenance(node_id)


@mcp.tool()
def analyze_research_impact(node_id: str) -> list[dict[str, Any]]:
    """List actual downstream dependants; shared Topics alone do not propagate staleness."""
    return service().impact_analysis(node_id)


@mcp.tool()
def propose_experiment_plan(track_id: str, plan_json: str, project_id: str = "") -> dict[str, Any]:
    """Propose a reproducible experiment inherited from an approved Method's Track."""
    return service().propose_experiment_plan(
        track_id, ExperimentPlanInput.model_validate(_json(plan_json)), project_id or None
    )


@mcp.tool()
def approve_experiment_plan(plan_id: str, expected_revision: int) -> dict[str, Any]:
    """Approve an experiment plan using its exact captured user-message grant."""
    return service().approve_experiment_plan(plan_id, expected_revision)


@mcp.tool()
def run_experiment(plan_id: str) -> dict[str, Any]:
    """Execute an approved immutable experiment plan."""
    return service().run_experiment(plan_id)


@mcp.tool()
def record_experiment_evidence(
    run_id: str, statement: str, metric_key: str = "", confidence: float = 0.95
) -> dict[str, Any]:
    """Convert one recorded run into Track-scoped Evidence."""
    return service().record_experiment_evidence(run_id, statement, metric_key or None, confidence)


@mcp.tool()
def create_manuscript(manuscript_json: str) -> dict[str, Any]:
    """Create an independently tracked Paper directly under one Track."""
    return service().create_manuscript(
        TrackFirstManuscriptInput.model_validate(_json(manuscript_json))
    )


@mcp.tool()
def get_manuscript(manuscript_id: str) -> dict[str, Any]:
    """Return a Paper's bindings, versions, status history, and submissions."""
    return service().get_manuscript(manuscript_id)


@mcp.tool()
def bind_manuscript_content(manuscript_id: str, binding_json: str) -> dict[str, Any]:
    """Bind selected Track nodes and Evidence to a Paper revision."""
    return service().bind_manuscript(
        manuscript_id, ManuscriptBindingInput.model_validate(_json(binding_json))
    )


@mcp.tool()
def update_manuscript_status(manuscript_id: str, status_json: str) -> dict[str, Any]:
    """Update one Paper's writing state without changing submissions."""
    return service().update_manuscript_status(
        manuscript_id, ManuscriptStatusInput.model_validate(_json(status_json))
    )


@mcp.tool()
def record_submission_event(manuscript_id: str, event_json: str) -> dict[str, Any]:
    """Append one submission event without overwriting prior venues or rounds."""
    return service().record_submission(
        manuscript_id, SubmissionEventInput.model_validate(_json(event_json))
    )


@mcp.tool()
def compile_manuscript(manuscript_id: str, abstract: str, sections_json: str = "[]") -> str:
    """Create an immutable version from only this Paper's selected content."""
    sections = list(_json(sections_json))
    return service().compile_manuscript(manuscript_id, abstract, sections or None)


@mcp.tool()
def verify_citations(manuscript_id: str, text: str) -> dict[str, Any]:
    """Check citations only against Evidence selected by this Paper."""
    return service().verify_citations(manuscript_id, text)


@mcp.tool()
def simulate_manuscript_review(manuscript_id: str) -> dict[str, Any]:
    """Produce review findings without changing Paper writing or submission status."""
    return service().simulate_review(manuscript_id)


@mcp.tool()
def query_fieldkg(
    field_id: str, query: str, mode: str = "AUTO", cross_field: bool = False
) -> dict[str, Any]:
    """Run KAG retrieval; normal queries are scoped to exactly one Field."""
    return FieldKGKagClient().query(field_id, query, mode, cross_field)


@mcp.tool()
def fieldkg_projection_health() -> dict[str, Any]:
    """Report ScholarFieldKG bridge health and the canonical backlog."""
    return FieldKGProjectionWorker(service().db_path).health()


@mcp.tool()
def sync_fieldkg_projection(limit: int = 100) -> dict[str, Any]:
    """Idempotently apply pending FieldKG projection jobs."""
    return FieldKGProjectionWorker(service().db_path).sync(limit)


@mcp.tool()
def rebuild_fieldkg_projection() -> dict[str, int]:
    """Recreate projection jobs from canonical SQLite state."""
    return FieldKGProjectionWorker(service().db_path).rebuild_outbox()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
