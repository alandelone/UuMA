from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchType(str, Enum):
    EXPERIMENTAL = "experimental"
    ENGINEERING_SYSTEM = "engineering_system"
    METHOD_ALGORITHM = "method_algorithm"
    SYSTEMATIC_REVIEW = "systematic_review"
    SOTA_REVIEW = "sota_review"
    CRITICAL_REVIEW = "critical_review"
    BIBLIOMETRIC_REVIEW = "bibliometric_review"
    CONCEPTUAL_FRAMEWORK = "conceptual_framework"
    CASE_STUDY = "case_study"


class DecisionKind(str, Enum):
    GAP = "gap"
    IDEA = "idea"
    RESEARCH_QUESTION = "research_question"
    HYPOTHESIS = "hypothesis"
    METHOD = "method"
    CLAIM = "claim"


class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"


class CollectionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED_CURRENT_FRONTIER = "COMPLETED_CURRENT_FRONTIER"


class AcquisitionJobStatus(str, Enum):
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    READY = "READY"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    RESOURCE_WAIT = "RESOURCE_WAIT"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class EvidenceRelation(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXTUALIZES = "CONTEXTUALIZES"


class EvidenceVerdict(str, Enum):
    SUPPORTS = "SUPPORTS"
    PARTIAL = "PARTIAL"
    CONTRADICTS = "CONTRADICTS"
    INSUFFICIENT = "INSUFFICIENT"


class WritingStatus(str, Enum):
    PLANNING = "PLANNING"
    DRAFTING = "DRAFTING"
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    REVISING = "REVISING"


class SubmissionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    ACCEPTED = "ACCEPTED"
    PUBLISHED = "PUBLISHED"


class SourceCandidate(StrictModel):
    source_provider: str
    external_id: str | None = None
    doi: str | None = None
    title: str = Field(min_length=1, max_length=2000)
    authors: list[str] = Field(default_factory=list)
    published_year: int | None = Field(default=None, ge=1000, le=3000)
    abstract: str | None = None
    landing_url: str | None = None
    pdf_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class EvidenceInput(StrictModel):
    paper_id: str
    statement: str = Field(min_length=1, max_length=12000)
    excerpt: str = Field(min_length=1, max_length=24000)
    location: str = Field(min_length=1, max_length=1000)
    relation: EvidenceRelation
    confidence: float = Field(ge=0, le=1)
    extractor_model: str | None = None
    prompt_version: str | None = None


class ResearchProjectInput(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=500)
    field: str = Field(min_length=1, max_length=300)
    research_type: ResearchType
    type_payload: dict[str, Any] = Field(default_factory=dict)
    scope: str | None = Field(default=None, max_length=4000)


class FieldInput(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)


class TopicInput(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)


class TrackInput(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    scope: str | None = Field(default=None, max_length=4000)
    research_type: ResearchType | None = None
    topic_ids: list[str] = Field(default_factory=list)


class TrackProgressInput(StrictModel):
    phase: str = Field(pattern=r"^(1|2|2\.5|3|4)$")
    status: str = Field(min_length=1, max_length=100)
    blocker: str | None = Field(default=None, max_length=4000)
    expected_revision: int = Field(ge=1)


class FoundationVersionInput(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    retrieval_scope: dict[str, Any] = Field(default_factory=dict)
    paper_ids: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    candidate_gaps: list[dict[str, Any]] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)


class ManuscriptInput(StrictModel):
    track_id: str
    title: str = Field(min_length=1, max_length=1000)
    scope: str | None = Field(default=None, max_length=8000)
    research_type: ResearchType | None = None
    node_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    section_map: dict[str, list[str]] = Field(default_factory=dict)


class ManuscriptStatusInput(StrictModel):
    status: WritingStatus
    blocker: str | None = Field(default=None, max_length=4000)
    next_step: str | None = Field(default=None, max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(ge=1)


class ManuscriptBindingInput(StrictModel):
    node_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    section_map: dict[str, list[str]] = Field(default_factory=dict)
    expected_revision: int = Field(ge=1)


class SubmissionEventInput(StrictModel):
    venue: str = Field(min_length=1, max_length=500)
    round: int = Field(default=1, ge=1)
    status: SubmissionStatus
    detail: str | None = Field(default=None, max_length=8000)


class DecisionProposalInput(StrictModel):
    kind: DecisionKind
    statement: str = Field(min_length=1, max_length=16000)
    rationale: str = Field(min_length=1, max_length=16000)
    evidence_ids: list[str] = Field(default_factory=list)
    upstream_node_ids: list[str] = Field(default_factory=list)
    supersedes_node_id: str | None = None
    track_id: str | None = None

    @model_validator(mode="after")
    def gap_needs_evidence(self) -> DecisionProposalInput:
        if self.kind is DecisionKind.GAP and not self.evidence_ids:
            raise ValueError("A gap proposal must reference at least one evidence item.")
        if self.kind is DecisionKind.IDEA and not self.upstream_node_ids:
            raise ValueError("An idea proposal must reference at least one approved gap.")
        return self


class ExperimentPlanInput(StrictModel):
    method_node_id: str
    argv: list[str] = Field(min_length=1)
    working_directory: str = "."
    script_path: str | None = None
    script_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    metrics_json_path: str | None = None

    @model_validator(mode="after")
    def script_digest_is_paired(self) -> ExperimentPlanInput:
        if bool(self.script_path) != bool(self.script_sha256):
            raise ValueError("script_path and script_sha256 must be supplied together")
        return self


class EvidenceAssessmentInput(StrictModel):
    claim_node_id: str
    evidence_id: str
    verdict: EvidenceVerdict
    rationale: str = Field(min_length=1, max_length=12000)
    conditions: list[str] = Field(default_factory=list)
    counterevidence_ids: list[str] = Field(default_factory=list)
    assessor_model: str = Field(min_length=1, max_length=300)
    prompt_version: str = Field(min_length=1, max_length=300)


class TrackFirstTopicInput(TopicInput):
    field_id: str


class TrackFirstTrackInput(StrictModel):
    field_id: str
    primary_topic_id: str
    title: str = Field(min_length=1, max_length=500)
    scope: str | None = Field(default=None, max_length=4000)
    research_type: ResearchType
    secondary_topic_ids: list[str] = Field(default_factory=list)


class TrackFirstProjectInput(StrictModel):
    track_id: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=500)
    research_type: ResearchType | None = None
    type_payload: dict[str, Any] = Field(default_factory=dict)
    scope: str | None = Field(default=None, max_length=4000)


class TrackMilestoneInput(StrictModel):
    milestone: str = Field(
        pattern=r"^(SCOPE|SNAPSHOT_ADOPTION|GAP|IDEA|RESEARCH_QUESTION|HYPOTHESIS|METHOD|EXPERIMENT|CLAIM)$"
    )
    status: str = Field(
        pattern=r"^(NOT_STARTED|ACTIVE|BLOCKED|READY_FOR_REVIEW|APPROVED|STALE|REOPENED)$"
    )
    blocker: str | None = Field(default=None, max_length=4000)
    expected_revision: int = Field(ge=0)


class TrackFirstEvidenceInput(EvidenceInput):
    track_id: str
    location_data: dict[str, Any] = Field(default_factory=dict)


class TrackFirstManuscriptInput(ManuscriptInput):
    project_ids: list[str] = Field(default_factory=list)


class FieldKGBuildInput(StrictModel):
    field_id: str
    paper_ids: list[str] = Field(default_factory=list)
    retrieval_scope: dict[str, Any] = Field(default_factory=dict)


class CollectionTargetInput(StrictModel):
    field_id: str
    track_id: str | None = None
    topic_id: str | None = None


class CollectionBudgetInput(StrictModel):
    max_papers: int | None = Field(default=500, ge=1, le=1_000_000)
    max_registered_pdf_bytes: int | None = Field(default=10 * 1024**3, ge=1)
    max_active_seconds: int | None = Field(default=24 * 3600, ge=1)
    max_task_attempts: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def bounded(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one Collection resource limit is required")
        return self


class CollectionBudgetUpdateInput(StrictModel):
    request_id: str = Field(min_length=8, max_length=300)
    expected_revision: int = Field(ge=1)
    limits: CollectionBudgetInput
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def explicit_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Explain the Collection budget change")
        return self


class CollectionCreateInput(CollectionTargetInput):
    name: str = Field(min_length=1, max_length=500)
    scope: dict[str, Any] = Field(default_factory=dict)
    paper_ids: list[str] = Field(default_factory=list, max_length=500)
    budget: CollectionBudgetInput | None = None
    dois: list[str] = Field(default_factory=list, max_length=5000)
    bibtex: str | None = Field(default=None, max_length=5_000_000)
    queries: list[str] = Field(default_factory=list, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def needs_seed(self) -> CollectionCreateInput:
        if not self.dois and not self.bibtex and not self.queries and not self.paper_ids:
            raise ValueError("Select a Catalog paper or provide a DOI, BibTeX record, or search query")
        if len(set(self.paper_ids)) != len(self.paper_ids) or any(not value.strip() for value in self.paper_ids):
            raise ValueError("Catalog paper IDs must be nonempty and selected once")
        return self


class CollectionScopeInput(StrictModel):
    scope: dict[str, Any]
    expected_revision: int = Field(ge=1)


class CollectionSearchInput(StrictModel):
    query: str = Field(min_length=3, max_length=1000)
    providers: list[str] = Field(default_factory=list, max_length=12)
    limit_per_provider: int = Field(default=10, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=300)


class DeepReadRequestInput(StrictModel):
    paper_id: str
    parse_run_id: str | None = None
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=300)


class PdfRegistrationInput(StrictModel):
    paper_id: str
    path: str = Field(min_length=1, max_length=4000)
    acquisition_method: str = Field(min_length=1, max_length=100)
    source_url: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=300)


class BrowserAcquisitionInput(StrictModel):
    paper_id: str
    idempotency_key: str = Field(min_length=8, max_length=300)
    start_url: str | None = Field(default=None, max_length=4000)


class BrowserAcquisitionReceiptInput(StrictModel):
    request_id: str
    execution_id: str = Field(min_length=1, max_length=500)
    action_id: str | None = Field(default=None, max_length=500)
    action_version: str | None = Field(default=None, max_length=100)
    status: str = Field(
        pattern=r"^(RUNNING|WAITING_HUMAN|COMPLETED|PARTIAL|FAILED|ABORTED)$"
    )
    output_paths: list[str] = Field(default_factory=list, max_length=20)
    source_url: str | None = Field(default=None, max_length=4000)
    error: dict[str, Any] | None = None


class LegacyPaperMigrationInput(StrictModel):
    database_path: str = Field(min_length=1, max_length=4000)
    paper_ids: list[int] = Field(default_factory=list)
    copy_files: bool = True


class LocalPdfImportInput(StrictModel):
    directories: list[str] = Field(min_length=1, max_length=20)
    max_files: int = Field(default=100, ge=1, le=500)


class JournalMetricsImportInput(StrictModel):
    path: str = Field(min_length=1, max_length=4000)
    metric_year: int = Field(ge=1900, le=2200)
    source: str = Field(default="SCOPUS_CITESCORE", pattern=r"^SCOPUS_CITESCORE$")


class PaperPoolImportInput(StrictModel):
    database_path: str
    paper_ids: list[int] = Field(default_factory=list)


class FieldKGReviewInput(StrictModel):
    decision: str = Field(pattern=r"^(ACCEPTED|REJECTED)$")
    rationale: str = Field(min_length=1, max_length=8000)
    expected_revision: int = Field(ge=1)


class FieldKGGapInput(StrictModel):
    statement: str = Field(min_length=1, max_length=16000)
    rationale: str = Field(min_length=1, max_length=16000)
    evidence_ids: list[str] = Field(default_factory=list)
    counterevidence_ids: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    generator_model: str | None = None
    prompt_version: str | None = None
