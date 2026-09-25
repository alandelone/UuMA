from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel, new_id, utc_now


class SourceType(str, Enum):
    WEB = "WEB"
    PAPER = "PAPER"
    DATASHEET = "DATASHEET"
    STANDARD = "STANDARD"
    BOOK = "BOOK"
    MANUAL = "MANUAL"
    DATASET = "DATASET"
    OTHER = "OTHER"


class ClaimStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class EvidenceStance(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"


class GapType(str, Enum):
    UNANSWERED_QUESTION = "UNANSWERED_QUESTION"
    MISSING_EXPLANATION = "MISSING_EXPLANATION"
    MISSING_MECHANISM = "MISSING_MECHANISM"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    CONFLICTING_CLAIMS = "CONFLICTING_CLAIMS"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    TERMINOLOGY = "TERMINOLOGY"
    COVERAGE = "COVERAGE"
    FRESHNESS = "FRESHNESS"
    COMPARISON = "COMPARISON"
    FAILURE_MODE = "FAILURE_MODE"
    HUMAN_REQUEST = "HUMAN_REQUEST"


class WorkStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    FILLED = "FILLED"
    IGNORED = "IGNORED"


class ConflictStatus(str, Enum):
    OPEN = "OPEN"
    CONTEXT_RESOLVED = "CONTEXT_RESOLVED"
    RESOLVED = "RESOLVED"


class PatchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    REVERSED = "REVERSED"


class ResearchRunStatus(str, Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class ReasoningMode(str, Enum):
    AUTO = "AUTO"
    SIMPLE = "SIMPLE"
    DEEP = "DEEP"


class SatisfactionLevel(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    PROVISIONAL = "PROVISIONAL"
    SUFFICIENT = "SUFFICIENT"
    STRONG = "STRONG"


class BudgetTier(str, Enum):
    QUICK = "QUICK"
    STANDARD = "STANDARD"
    DEEP = "DEEP"


class OrbitStatus(str, Enum):
    QUEUED = "QUEUED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class OrbitCycleStatus(str, Enum):
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class OrbitNotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class FrontierPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FreshnessStatus(str, Enum):
    CURRENT = "CURRENT"
    DUE = "DUE"
    STALE = "STALE"


class ProjectionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"


class PatchOperationKind(str, Enum):
    ACCEPT_CLAIM = "ACCEPT_CLAIM"
    UPDATE_CLAIM = "UPDATE_CLAIM"
    SUPERSEDE_CLAIM = "SUPERSEDE_CLAIM"
    ACCEPT_ENTITY = "ACCEPT_ENTITY"
    UPDATE_ENTITY = "UPDATE_ENTITY"
    ACCEPT_RELATION = "ACCEPT_RELATION"
    UPDATE_RELATION = "UPDATE_RELATION"
    ACCEPT_SCHEMA_MODULE = "ACCEPT_SCHEMA_MODULE"
    UPDATE_SCHEMA_MODULE = "UPDATE_SCHEMA_MODULE"
    UPDATE_FRESHNESS = "UPDATE_FRESHNESS"
    UPDATE_GAP = "UPDATE_GAP"
    UPDATE_CONFLICT = "UPDATE_CONFLICT"


class SourceRecord(StrictModel):
    source_id: str = Field(default_factory=lambda: new_id("src"))
    locator: str = Field(min_length=1, max_length=4000)
    title: str = Field(min_length=1, max_length=1000)
    source_type: SourceType = SourceType.WEB
    publisher: str | None = Field(default=None, max_length=500)
    authored_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    content_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(StrictModel):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    source_id: str
    excerpt: str = Field(min_length=1, max_length=16000)
    location: str | None = Field(default=None, max_length=1000)
    surrounding_context: str | None = Field(default=None, max_length=16000)
    extraction_method: str = Field(default="manual", max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class DocumentVersionRecord(StrictModel):
    document_id: str = Field(default_factory=lambda: new_id("doc"))
    source_id: str
    version: int = Field(default=1, ge=1)
    media_type: str = Field(min_length=1, max_length=200)
    language: str = Field(default="und", min_length=2, max_length=35)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_ref: str = Field(min_length=1, max_length=4000)
    previous_document_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=utc_now)


class ChunkRecord(StrictModel):
    chunk_id: str = Field(default_factory=lambda: new_id("chunk"))
    document_id: str
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=100000)
    location: str | None = Field(default=None, max_length=1000)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def character_range_is_ordered(self) -> ChunkRecord:
        if (
            self.start_char is not None
            and self.end_char is not None
            and self.start_char > self.end_char
        ):
            raise ValueError("start_char cannot be after end_char")
        return self


class ClaimRecord(StrictModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    statement: str = Field(min_length=1, max_length=16000)
    subject: str | None = Field(default=None, max_length=1000)
    predicate: str | None = Field(default=None, max_length=1000)
    object: str | None = Field(default=None, max_length=4000)
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    status: ClaimStatus = ClaimStatus.CANDIDATE
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    revision: int = Field(default=1, ge=1)
    superseded_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validity_window_is_ordered(self) -> ClaimRecord:
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("valid_from cannot be after valid_until")
        return self


class ClaimEvidenceLink(StrictModel):
    link_id: str = Field(default_factory=lambda: new_id("link"))
    claim_id: str
    evidence_id: str
    stance: EvidenceStance
    rationale: str = Field(min_length=1, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)


class EntityRecord(StrictModel):
    entity_id: str = Field(default_factory=lambda: new_id("entity"))
    canonical_name: str = Field(min_length=1, max_length=1000)
    entity_type: str = Field(default="Thing", min_length=1, max_length=500)
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)
    schema_module_id: str | None = None
    status: ClaimStatus = ClaimStatus.CANDIDATE
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RelationRecord(StrictModel):
    relation_id: str = Field(default_factory=lambda: new_id("relation"))
    subject_entity_id: str
    predicate: str = Field(min_length=1, max_length=1000)
    object_entity_id: str | None = None
    literal_value: Any | None = None
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    claim_ids: list[str] = Field(default_factory=list)
    schema_module_id: str | None = None
    status: ClaimStatus = ClaimStatus.CANDIDATE
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def one_object_form(self) -> RelationRecord:
        if (self.object_entity_id is None) == (self.literal_value is None):
            raise ValueError("relation requires exactly one object_entity_id or literal_value")
        return self


class ChunkKnowledgeLink(StrictModel):
    chunk_knowledge_link_id: str = Field(default_factory=lambda: new_id("cklink"))
    chunk_id: str
    target_kind: Literal["entity", "relation", "claim", "evidence"]
    target_id: str
    link_type: Literal["MENTIONS", "SUPPORTS", "CONTRADICTS", "QUALIFIES", "EXTRACTED_FROM"]
    extraction_method: str = Field(default="manual", max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class SchemaModuleRecord(StrictModel):
    schema_module_id: str = Field(default_factory=lambda: new_id("schema"))
    name: str = Field(min_length=1, max_length=500)
    version: int = Field(default=1, ge=1)
    description: str = Field(min_length=1, max_length=8000)
    entity_types: dict[str, Any] = Field(default_factory=dict)
    predicates: dict[str, Any] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    logical_rules: list[dict[str, Any]] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.CANDIDATE
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class QuestionRecord(StrictModel):
    question_id: str = Field(default_factory=lambda: new_id("question"))
    text: str = Field(min_length=1, max_length=8000)
    why_worth_knowing: str = Field(min_length=1, max_length=8000)
    parent_question_id: str | None = None
    orbit_id: str | None = None
    status: WorkStatus = WorkStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)


class KnowledgeTopicRecord(StrictModel):
    topic_id: str = Field(default_factory=lambda: new_id("topic"))
    title: str = Field(min_length=1, max_length=1000)
    normalized_key: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list)
    focus: list[str] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=16000)
    status: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TopicQuestionLinkRecord(StrictModel):
    topic_question_link_id: str = Field(default_factory=lambda: new_id("tqlink"))
    topic_id: str
    question_id: str
    relationship: Literal["ROOT", "RELATED", "SUBQUESTION", "FOCUS"]
    rationale: str = Field(min_length=1, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)


class TopicKnowledgeLinkRecord(StrictModel):
    topic_knowledge_link_id: str = Field(default_factory=lambda: new_id("tklink"))
    topic_id: str
    target_kind: Literal["source", "evidence", "claim", "entity", "relation"]
    target_id: str
    relationship: Literal["USES", "SUPPORTS", "CONTRADICTS", "MENTIONS"] = "USES"
    rationale: str = Field(min_length=1, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)


class TopicDocumentRecord(StrictModel):
    topic_document_id: str = Field(default_factory=lambda: new_id("topicdoc"))
    topic_id: str
    title: str = Field(min_length=1, max_length=1000)
    current_version: int = Field(default=0, ge=0)
    latest_version_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TopicDocumentVersionRecord(StrictModel):
    topic_document_version_id: str = Field(default_factory=lambda: new_id("topicver"))
    topic_document_id: str
    topic_id: str
    version: int = Field(ge=1)
    body_markdown: str = Field(min_length=1, max_length=500000)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    change_summary: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    orbit_id: str | None = None
    orbit_cycle_id: str | None = None
    research_status: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class TopicRouteRecord(StrictModel):
    topic_route_id: str = Field(default_factory=lambda: new_id("topicroute"))
    route_key: str = Field(min_length=1, max_length=1000)
    topic_id: str
    question_id: str
    updated_at: datetime = Field(default_factory=utc_now)


class GapRecord(StrictModel):
    gap_id: str = Field(default_factory=lambda: new_id("gap"))
    gap_type: GapType
    reason: str = Field(min_length=1, max_length=8000)
    why_worthwhile: str = Field(min_length=1, max_length=8000)
    question_id: str | None = None
    orbit_id: str | None = None
    related_claim_ids: list[str] = Field(default_factory=list)
    current_knowledge: str | None = Field(default=None, max_length=16000)
    status: WorkStatus = WorkStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConflictRecord(StrictModel):
    conflict_id: str = Field(default_factory=lambda: new_id("conflict"))
    claim_ids: list[str] = Field(min_length=2)
    description: str = Field(min_length=1, max_length=8000)
    context_analysis: str | None = Field(default=None, max_length=16000)
    status: ConflictStatus = ConflictStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PatchOperation(StrictModel):
    kind: PatchOperationKind
    target_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class KnowledgePatch(StrictModel):
    patch_id: str = Field(default_factory=lambda: new_id("patch"))
    operations: list[PatchOperation] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=16000)
    proposed_by: str
    status: PatchStatus = PatchStatus.PROPOSED
    review_note: str | None = Field(default=None, max_length=8000)
    diff: list[dict[str, Any]] = Field(default_factory=list)
    undo: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ResearchRun(StrictModel):
    research_run_id: str = Field(default_factory=lambda: new_id("research"))
    objective: str = Field(min_length=1, max_length=16000)
    root_question_id: str | None = None
    active_gap_ids: list[str] = Field(default_factory=list)
    status: ResearchRunStatus = ResearchRunStatus.PLANNED
    knowledge_satisfaction: float = Field(default=0.0, ge=0.0, le=1.0)
    satisfaction_level: SatisfactionLevel = SatisfactionLevel.INSUFFICIENT
    satisfaction_rationale: str = Field(min_length=1, max_length=8000)
    budget_tier: BudgetTier = BudgetTier.STANDARD
    active_seconds: float = Field(default=0, ge=0)
    sources_used: int = Field(default=0, ge=0)
    model_tokens_used: int = Field(default=0, ge=0)
    stop_reason: str | None = Field(default=None, max_length=8000)
    orbit_id: str | None = None
    current_question_id: str | None = None
    cycle_count: int = Field(default=0, ge=0)
    search_queries_used: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class QuestionOrbitRecord(StrictModel):
    orbit_id: str = Field(default_factory=lambda: new_id("orbit"))
    normalized_root_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    root_question_id: str
    research_run_id: str
    topic_id: str | None = None
    objective: str = Field(min_length=1, max_length=16000)
    uuma_task_id: str | None = None
    uuma_run_id: str | None = None
    budget_tier: BudgetTier = BudgetTier.QUICK
    status: OrbitStatus = OrbitStatus.QUEUED
    satisfaction_level: SatisfactionLevel = SatisfactionLevel.INSUFFICIENT
    satisfaction_rationale: str = Field(min_length=1, max_length=8000)
    stop_reason: str | None = Field(default=None, max_length=8000)
    notification_route: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FrontierItemRecord(StrictModel):
    frontier_item_id: str = Field(default_factory=lambda: new_id("frontier"))
    orbit_id: str
    question_id: str
    gap_id: str | None = None
    priority: FrontierPriority = FrontierPriority.MEDIUM
    relevance: FrontierPriority = FrontierPriority.MEDIUM
    impact: FrontierPriority = FrontierPriority.MEDIUM
    uncertainty: FrontierPriority = FrontierPriority.MEDIUM
    novelty: FrontierPriority = FrontierPriority.MEDIUM
    estimated_cost: FrontierPriority = FrontierPriority.MEDIUM
    rationale: str = Field(min_length=1, max_length=8000)
    status: WorkStatus = WorkStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OrbitCycleRecord(StrictModel):
    orbit_cycle_id: str = Field(default_factory=lambda: new_id("cycle"))
    orbit_id: str
    cycle_key: str = Field(min_length=1, max_length=500)
    frontier_item_id: str
    question_id: str
    status: OrbitCycleStatus = OrbitCycleStatus.RUNNING
    attempt: int = Field(default=1, ge=1, le=3)
    lease_owner: str = Field(min_length=1, max_length=500)
    lease_expires_at: datetime
    heartbeat_at: datetime = Field(default_factory=utc_now)
    kag_watermark: int = Field(default=0, ge=0)
    discovery_queries: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    generated_question_ids: list[str] = Field(default_factory=list)
    decision: str | None = Field(default=None, max_length=200)
    error: str | None = Field(default=None, max_length=8000)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DiscoveryUsageRecord(StrictModel):
    discovery_usage_id: str = Field(default_factory=lambda: new_id("usage"))
    orbit_id: str
    provider: str = Field(min_length=1, max_length=200)
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    request_count: int = Field(default=1, ge=0)
    query_count: int = Field(default=1, ge=0)
    result_count: int = Field(default=0, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)


class OrbitNotificationRecord(StrictModel):
    orbit_notification_id: str = Field(default_factory=lambda: new_id("notice"))
    orbit_id: str
    event_type: str = Field(min_length=1, max_length=200)
    dedupe_key: str = Field(min_length=1, max_length=500)
    route: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: OrbitNotificationStatus = OrbitNotificationStatus.PENDING
    attempts: int = Field(default=0, ge=0, le=3)
    available_at: datetime = Field(default_factory=utc_now)
    sent_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FreshnessPolicyRecord(StrictModel):
    freshness_policy_id: str = Field(default_factory=lambda: new_id("freshness"))
    target_kind: Literal["source", "document", "evidence", "claim", "entity", "relation"]
    target_id: str
    review_interval_days: int = Field(ge=1, le=3650)
    volatility: Literal["HIGH", "MEDIUM", "LOW", "STATIC"] = "LOW"
    status: FreshnessStatus = FreshnessStatus.CURRENT
    last_verified_at: datetime = Field(default_factory=utc_now)
    next_review_at: datetime
    stale_reason: str | None = Field(default=None, max_length=4000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectionJobRecord(StrictModel):
    projection_job_id: str = Field(default_factory=lambda: new_id("projection"))
    event_sequence: int = Field(ge=1)
    aggregate_type: str
    aggregate_id: str
    operation: Literal["UPSERT", "DELETE"] = "UPSERT"
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ProjectionStatus = ProjectionStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = Field(default=None, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReasoningStep(StrictModel):
    step: int = Field(ge=1)
    operator: Literal["EXACT", "TEXT", "VECTOR", "GRAPH", "NUMERIC", "TEMPORAL", "SEMANTIC"]
    query: str = Field(min_length=1, max_length=8000)
    result_refs: list[str] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=8000)


class ReasoningTraceRecord(StrictModel):
    reasoning_trace_id: str = Field(default_factory=lambda: new_id("trace"))
    question: str = Field(min_length=1, max_length=16000)
    requested_mode: ReasoningMode = ReasoningMode.AUTO
    selected_mode: ReasoningMode
    steps: list[ReasoningStep] = Field(default_factory=list)
    projection_watermark: int = Field(default=0, ge=0)
    degraded: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class AnswerCitation(StrictModel):
    source_id: str
    evidence_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    claim_id: str | None = None
    locator: str
    location: str | None = None
    stance: EvidenceStance | None = None
    rationale: str | None = Field(default=None, max_length=8000)


class KnowledgeAnswer(StrictModel):
    answer: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    satisfaction_level: SatisfactionLevel
    satisfaction_rationale: str
    remaining_gap_ids: list[str] = Field(default_factory=list)
    reasoning_trace_id: str
    selected_mode: ReasoningMode
    runtime_status: Literal["KAG", "DEGRADED_KAG"]
    projection_watermark: int = Field(ge=0)


class KnowledgeEvent(StrictModel):
    sequence: int
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_id: str
    occurred_at: datetime
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str
