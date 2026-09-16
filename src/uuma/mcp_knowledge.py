from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from .kag_adapter import (
    KagProjectionWorker,
    KagUnavailableError,
    KnowledgeReasoner,
    OpenSpgKagBackend,
)
from .knowledge_construction import KnowledgeConstructor
from .knowledge_ingest import KnowledgeIngestor
from .knowledge_models import (
    ChunkKnowledgeLink,
    ClaimEvidenceLink,
    ClaimRecord,
    ConflictRecord,
    EntityRecord,
    EvidenceRecord,
    FreshnessPolicyRecord,
    GapRecord,
    KnowledgePatch,
    QuestionRecord,
    ReasoningMode,
    RelationRecord,
    ResearchRun,
    SchemaModuleRecord,
    SourceRecord,
    SourceType,
)
from .knowledge_service import KnowledgeService
from .settings import Settings

mcp = FastMCP("wisdom-knowledge")
ModelT = TypeVar("ModelT", bound=BaseModel)


def _actor() -> str:
    actor_id = os.environ.get("UUMA_AGENT_ID", "")
    if actor_id not in KnowledgeService.WRITERS:
        raise PermissionError("This Knowledge MCP is not available to the current Hermes profile.")
    return actor_id


@lru_cache(maxsize=1)
def _service() -> KnowledgeService:
    settings = Settings.from_env()
    settings.ensure_directories()
    return KnowledgeService(settings.knowledge_database_path())


@lru_cache(maxsize=1)
def _backend() -> OpenSpgKagBackend:
    return OpenSpgKagBackend.from_env()


@lru_cache(maxsize=1)
def _reasoner() -> KnowledgeReasoner:
    return KnowledgeReasoner(_service(), _backend())


@lru_cache(maxsize=1)
def _projection_worker() -> KagProjectionWorker:
    return KagProjectionWorker(_service(), _backend())


@lru_cache(maxsize=1)
def _ingestor() -> KnowledgeIngestor:
    settings = Settings.from_env()
    return KnowledgeIngestor(_service(), settings.knowledge_content_path())


@lru_cache(maxsize=1)
def _constructor() -> KnowledgeConstructor:
    return KnowledgeConstructor(_service(), _backend())


def _model(model_type: type[ModelT], payload_json: str) -> ModelT:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        # Preserve validation-error behavior for malformed serialized MCP arguments.
        raise ValueError("The JSON argument must contain an object.")  # noqa: TRY004
    return model_type.model_validate(payload)


@mcp.tool()
def knowledge_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search the canonical text fallback; use knowledge_answer for KAG reasoning."""
    _actor()
    return _service().search(query, limit)


@mcp.tool()
def knowledge_get(object_id: str) -> dict[str, Any]:
    """Get one knowledge object; claims include their evidence links and evidence records."""
    _actor()
    return _service().get(object_id)


@mcp.tool()
def knowledge_list(kind: str, status: str = "", limit: int = 100) -> dict[str, Any]:
    """List canonical records by semantic kind; no storage-backend query is exposed."""
    _actor()
    return _service().list_records(kind, status=status or None, limit=limit)


@mcp.tool()
def knowledge_get_history(aggregate_id: str = "", limit: int = 200) -> dict[str, Any]:
    """Return immutable knowledge events and the current hash-chain verification result."""
    _actor()
    return _service().history(aggregate_id or None, limit)


@mcp.tool()
def knowledge_add_source(source_json: str) -> dict[str, Any]:
    """Register source provenance before extracting evidence from it."""
    actor_id = _actor()
    return _service().add_source(_model(SourceRecord, source_json), actor_id=actor_id)


@mcp.tool()
def knowledge_add_evidence(evidence_json: str) -> dict[str, Any]:
    """Store an exact, located evidence excerpt tied to a registered source."""
    actor_id = _actor()
    return _service().add_evidence(_model(EvidenceRecord, evidence_json), actor_id=actor_id)


@mcp.tool()
def knowledge_ingest_file(path: str) -> dict[str, Any]:
    """Snapshot, version, extract, and chunk a local text, HTML, Markdown, PDF, or DOCX file."""
    return _ingestor().ingest_file(path, actor_id=_actor())


@mcp.tool()
def knowledge_ingest_web(url: str) -> dict[str, Any]:
    """Fetch one public URL, preserve its raw digest/version, and create located chunks."""
    return _ingestor().ingest_web(url, actor_id=_actor())


@mcp.tool()
def knowledge_ingest_text(
    locator: str,
    title: str,
    text: str,
    media_type: str = "text/plain",
    source_type: str = "OTHER",
) -> dict[str, Any]:
    """Ingest supplied source text when acquisition is handled by another authorized connector."""
    return _ingestor().ingest_text(
        locator=locator,
        title=title,
        text=text,
        media_type=media_type,
        source_type=SourceType(source_type.upper()),
        actor_id=_actor(),
    )


@mcp.tool()
def knowledge_extract_candidates(
    document_id: str,
    max_chunks: int = 20,
    offset: int = 0,
    recover_runtime: bool = True,
) -> dict[str, Any]:
    """Extract one canonical chunk page; continue with the returned next_offset until complete."""
    return _constructor().extract_document(
        document_id,
        actor_id=_actor(),
        max_chunks=max_chunks,
        offset=offset,
        recover=recover_runtime,
    )


@mcp.tool()
def knowledge_propose_claim(claim_json: str) -> dict[str, Any]:
    """Add an atomic CANDIDATE claim with explicit conditions in qualifiers."""
    actor_id = _actor()
    return _service().propose_claim(_model(ClaimRecord, claim_json), actor_id=actor_id)


@mcp.tool()
def knowledge_link_evidence(link_json: str) -> dict[str, Any]:
    """Link evidence to a claim as SUPPORTS, CONTRADICTS, or QUALIFIES with rationale."""
    actor_id = _actor()
    return _service().link_evidence(_model(ClaimEvidenceLink, link_json), actor_id=actor_id)


@mcp.tool()
def knowledge_propose_entity(entity_json: str) -> dict[str, Any]:
    """Propose a CANDIDATE entity for review before it enters the KAG projection."""
    return _service().propose_entity(_model(EntityRecord, entity_json), actor_id=_actor())


@mcp.tool()
def knowledge_propose_relation(relation_json: str) -> dict[str, Any]:
    """Propose a qualified CANDIDATE graph relation linked to canonical claims."""
    return _service().propose_relation(_model(RelationRecord, relation_json), actor_id=_actor())


@mcp.tool()
def knowledge_link_chunk(link_json: str) -> dict[str, Any]:
    """Create a provenance-preserving chunk-to-entity/relation/claim/evidence mutual link."""
    return _service().link_chunk(_model(ChunkKnowledgeLink, link_json), actor_id=_actor())


@mcp.tool()
def knowledge_propose_schema_module(schema_module_json: str) -> dict[str, Any]:
    """Propose a versioned domain ontology/rule module; review is required before projection."""
    return _service().propose_schema_module(
        _model(SchemaModuleRecord, schema_module_json), actor_id=_actor()
    )


@mcp.tool()
def knowledge_add_freshness_policy(freshness_policy_json: str) -> dict[str, Any]:
    """Attach an adaptive verification interval and current/due/stale state to knowledge."""
    return _service().add_freshness_policy(
        _model(FreshnessPolicyRecord, freshness_policy_json), actor_id=_actor()
    )


@mcp.tool()
def knowledge_get_graph_neighborhood(
    entity_id: str, depth: int = 1, limit: int = 100
) -> dict[str, Any]:
    """Retrieve a bounded semantic neighborhood from accepted canonical relations."""
    _actor()
    return _service().graph_neighborhood(entity_id, depth=depth, limit=limit)


@mcp.tool()
def knowledge_answer(
    question: str, mode: str = "AUTO", recover_runtime: bool = True
) -> dict[str, Any]:
    """Answer through OpenSPG KAG hybrid reasoning, with explicit canonical fallback and trace."""
    actor_id = _actor()
    return _reasoner().answer(
        question,
        requested_mode=ReasoningMode(mode.upper()),
        actor_id=actor_id,
        recover=recover_runtime,
    )


@mcp.tool()
def knowledge_projection_health() -> dict[str, Any]:
    """Report canonical outbox watermark/lag and disposable OpenSPG KAG runtime readiness."""
    _actor()
    result = _service().projection_health()
    try:
        result["runtime"] = _backend().health()
    except KagUnavailableError as exc:
        result["runtime"] = {"ready": False, "error": str(exc)}
    return result


@mcp.tool()
def knowledge_projection_sync(limit: int = 100, recover_runtime: bool = True) -> dict[str, Any]:
    """Apply pending canonical outbox events to KAG, recovering its isolated runtime when configured."""
    _actor()
    return _projection_worker().sync(limit=limit, recover=recover_runtime)


@mcp.tool()
def knowledge_add_question(question_json: str) -> dict[str, Any]:
    """Add a root or child question and why answering it is worthwhile."""
    actor_id = _actor()
    return _service().add_question(_model(QuestionRecord, question_json), actor_id=actor_id)


@mcp.tool()
def knowledge_add_gap(gap_json: str) -> dict[str, Any]:
    """Record a qualified knowledge gap, its current knowledge, and why it matters."""
    actor_id = _actor()
    return _service().add_gap(_model(GapRecord, gap_json), actor_id=actor_id)


@mcp.tool()
def knowledge_record_conflict(conflict_json: str) -> dict[str, Any]:
    """Record a genuine unresolved conflict after checking units, scope, date, and conditions."""
    actor_id = _actor()
    return _service().record_conflict(_model(ConflictRecord, conflict_json), actor_id=actor_id)


@mcp.tool()
def knowledge_start_research_run(research_run_json: str) -> dict[str, Any]:
    """Persist a bounded research objective, active gaps, and initial knowledge satisfaction."""
    actor_id = _actor()
    return _service().start_research_run(
        _model(ResearchRun, research_run_json), actor_id=actor_id
    )


@mcp.tool()
def knowledge_update_research_run(
    research_run_id: str, changes_json: str
) -> dict[str, Any]:
    """Update research progress, active gaps, satisfaction rationale, or explicit stop state."""
    actor_id = _actor()
    changes = json.loads(changes_json)
    if not isinstance(changes, dict):
        # Preserve validation-error behavior for malformed serialized MCP arguments.
        raise ValueError("changes_json must contain an object.")  # noqa: TRY004
    return _service().update_research_run(research_run_id, changes, actor_id=actor_id)


@mcp.tool()
def knowledge_propose_patch(patch_json: str) -> dict[str, Any]:
    """Propose a reviewable canonical change; Wisdom-Oldman cannot apply its own patch."""
    actor_id = _actor()
    return _service().propose_patch(_model(KnowledgePatch, patch_json), actor_id=actor_id)


@mcp.tool()
def knowledge_get_diff(patch_id: str) -> dict[str, Any]:
    """Inspect the before/proposed or before/after diff for a knowledge patch."""
    _actor()
    return _service().patch_diff(patch_id)


@mcp.tool()
def knowledge_apply_patch(patch_id: str, review_note: str) -> dict[str, Any]:
    """Apply a proposed patch; authorization is restricted to the Orchestrator profile."""
    actor_id = _actor()
    return _service().apply_patch(patch_id, actor_id=actor_id, review_note=review_note)


@mcp.tool()
def knowledge_reject_patch(patch_id: str, review_note: str) -> dict[str, Any]:
    """Reject a proposed patch while preserving the proposal and review rationale."""
    actor_id = _actor()
    return _service().reject_patch(patch_id, actor_id=actor_id, review_note=review_note)


@mcp.tool()
def knowledge_reverse_patch(patch_id: str, review_note: str) -> dict[str, Any]:
    """Reverse an applied patch through an audited compensating change."""
    actor_id = _actor()
    return _service().reverse_patch(patch_id, actor_id=actor_id, review_note=review_note)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
