from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from .kag_adapter import (
    KagProjectionWorker,
    KagUnavailableError,
    OpenSpgKagBackend,
)
from .knowledge_construction import KnowledgeConstructor
from .knowledge_ingest import KnowledgeIngestor
from .knowledge_models import (
    BudgetTier,
    ChunkKnowledgeLink,
    ClaimEvidenceLink,
    ClaimRecord,
    ConflictRecord,
    EntityRecord,
    EvidenceRecord,
    FreshnessPolicyRecord,
    GapRecord,
    KnowledgePatch,
    OrbitStatus,
    QuestionRecord,
    ReasoningMode,
    RelationRecord,
    ResearchRun,
    SatisfactionLevel,
    SchemaModuleRecord,
    SourceRecord,
    SourceType,
)
from .knowledge_runtime import ensure_knowledge_graph
from .knowledge_service import KnowledgeService
from .orbit_discovery import citations_fit_question
from .orbit_synthesis import OrbitCompactSynthesizer
from .question_orbit import QuestionOrbitService
from .settings import Settings
from .wisdom_topics import (
    TopicKnowledgeService,
    ensure_view_token,
    grounded_answer,
    is_machine_error_payload,
    is_progress_request,
    research_control_intent,
    research_question_text,
)

mcp = FastMCP("wisdom-knowledge")
ModelT = TypeVar("ModelT", bound=BaseModel)


def _wake_orbit_runner(status: str) -> dict[str, Any]:
    """Wake the installed on-demand runner only after an Orbit is durable and queued."""
    if status != "QUEUED":
        return {"requested": False}
    profile_home = os.environ.get("UUMA_QUESTION_ORBIT_PROFILE_HOME", "").strip()
    if os.name == "nt" and profile_home:
        profile_home = str(Path(profile_home).resolve())
        python = Path(sys.executable).with_name("pythonw.exe")
        runner_environment = os.environ.copy()
        runner_environment["UUMA_DATA_DIR"] = str(Settings.from_env().knowledge_database_path().parent)
        # Ensure the spawned process can find the uuma package even when
        # sys.executable is Hermes's Python (not the UuMA venv Python).
        # Derive UuMA src/ from this file's location: mcp_knowledge.py → src/
        uuma_src = str(Path(__file__).resolve().parent.parent)
        current_pythonpath = runner_environment.get("PYTHONPATH", "")
        runner_environment["PYTHONPATH"] = (
            f"{uuma_src}{os.pathsep}{current_pythonpath}"
            if current_pythonpath else uuma_src
        )
        try:
            process = subprocess.Popen(
                [str(python if python.is_file() else sys.executable),
                 "-m", "uuma.orbit_runner", "--profile-home", profile_home],
                env=runner_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=(
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
            )
        except OSError:
            pass  # The installed scheduled task can still wake the durable queue.
        else:
            return {"requested": True, "method": "detached_process", "pid": process.pid}
    task_name = os.environ.get("UUMA_QUESTION_ORBIT_WAKE_TASK", "").strip()
    if os.name != "nt" or not task_name:
        return {"requested": False, "reason": "No on-demand runner wake task configured."}
    try:
        receipt = subprocess.run(
            ["schtasks.exe", "/run", "/tn", task_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"requested": False, "reason": type(exc).__name__}
    if receipt.returncode:
        return {"requested": False, "reason": "Task Scheduler rejected the wake request."}
    return {"requested": True}


def _global_research_status() -> dict[str, Any]:
    """Report durable research across chat sessions without changing topic routing."""
    orbits = _orbits().list(limit=200)["records"]
    topics = {
        item["topic_id"]: item
        for item in _topics().list_topics(limit=200)["records"]
    }
    active: list[dict[str, Any]] = []
    paused: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []
    for orbit in orbits:
        topic_id = orbit.get("topic_id")
        topic = topics.get(topic_id) if topic_id else None
        if not topic or topic["status"] != "ACTIVE":
            continue
        context = _topics().get_topic(topic_id)
        detail = _orbits().get(orbit["orbit_id"])
        run = detail["research_run"]
        cycle = detail.get("current_cycle") or {}
        latest = context.get("latest_version") or {}
        item = {
            "orbit_id": orbit["orbit_id"],
            "status": orbit["status"],
            "topic_id": topic_id,
            "topic_title": topic["title"] if topic else orbit["objective"][:160],
            "document_url": _topics().topic_url(topic_id) if topic else None,
            "stop_reason": orbit.get("stop_reason"),
            "updated_at": orbit["updated_at"],
            "document_version": (context.get("document") or {}).get("current_version", 0),
            "section_count": len(latest.get("sections") or []),
            "document_updated_at": (context.get("document") or {}).get("updated_at"),
            "completed_cycles": run.get("cycle_count", 0),
            "cycle_status": cycle.get("status"),
            "retry_reason": cycle.get("error") if cycle.get("status") == "RETRY" else None,
            "retry_at": cycle.get("lease_expires_at") if cycle.get("status") == "RETRY" else None,
            "budget_usage": {key: run[key] for key in (
                "active_seconds", "sources_used", "model_tokens_used", "search_queries_used",
            )},
            "budget": detail["budget"],
            "open_questions": [_topics().knowledge.get(item["question_id"])["record"]["text"]
                               for item in detail["frontier"] if item["status"] == "OPEN"],
        }
        group = active if orbit["status"] in {"QUEUED", "ACTIVE"} else (
            paused if orbit["status"] in {"PAUSED", "BLOCKED", "BUDGET_EXHAUSTED"} else finished
        )
        group.append(item)
    return {"active": active, "paused": paused, "finished": finished,
            "topics_url": _topics().topics_url()}


def _control_existing_research(
    intent: str, route: dict[str, str], actor_id: str, topic_id: str,
) -> dict[str, Any]:
    current = _topics().conversation_status(route)
    target = topic_id or current.get("topic_id")
    if not target:
        candidates = [topic for topic in _topics().list_topics()["records"]
                      if topic["status"] == "ACTIVE"]
        if len(candidates) == 1:
            target = candidates[0]["topic_id"]
    changed: list[str] = []
    if target:
        context = _topics().get_topic(target)
        if context["topic"]["status"] != "ACTIVE":
            raise ValueError("Select an existing active topic to control research.")
        if route:
            _topics().bind_existing_topic(target, route=route, actor_id=actor_id)
        transitions = {
            "resume": ({"PAUSED", "BLOCKED", "FAILED"}, OrbitStatus.QUEUED),
            "pause": ({"QUEUED", "ACTIVE"}, OrbitStatus.PAUSED),
            "stop": ({"QUEUED", "ACTIVE", "PAUSED", "BLOCKED"}, OrbitStatus.STOPPED),
        }
        allowed, destination = transitions[intent]
        for orbit in context["orbits"]:
            if orbit["status"] in allowed:
                _orbits().transition(orbit["orbit_id"], destination, actor_id=actor_id,
                                     reason=f"User requested {intent} of existing research.")
                changed.append(orbit["orbit_id"])
    global_status = _global_research_status()
    global_status["control_message"] = (
        "请选择要操作的已有主题；这次没有更改研究任务。" if not target else
        "已按指令更新原研究任务；没有建立新主题或重置预算。" if changed else
        "现有任务无需切换，或已停止／预算已用完；这次没有启动新研究或追加预算。"
    )
    wake = _wake_orbit_runner("QUEUED") if changed and intent == "resume" else None
    return {
        "message_intent": intent, "needs_intent_resolution": False,
        "needs_topic_selection": not bool(target), "knowledge_mutated": bool(changed),
        "orbit_started": False, "changed_orbit_ids": changed, "runner_wake": wake,
        "current_status": _topics().conversation_status(route), "global_status": global_status,
        "research_continues": bool(global_status["active"]),
        "instruction": "Report durable state. No new topic or budget was created. "
                       "Stopped or exhausted tasks cannot resume automatically. "
                       "If target is ambiguous, ask which existing topic the user means.",
    }


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
def _reasoner() -> OrbitCompactSynthesizer:
    return OrbitCompactSynthesizer(_service(), _backend())


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


@lru_cache(maxsize=1)
def _orbits() -> QuestionOrbitService:
    tier = BudgetTier(os.environ.get("UUMA_QUESTION_ORBIT_DEFAULT_BUDGET", "DEEP").upper())
    return QuestionOrbitService(
        _service(), topics=_topics(), automatic_budget_tier=tier
    )


@lru_cache(maxsize=1)
def _topics() -> TopicKnowledgeService:
    settings = Settings.from_env()
    token = ensure_view_token(settings.knowledge_database_path().parent)
    return TopicKnowledgeService(
        _service(),
        view_base_url=os.environ.get("UUMA_WISDOM_VIEW_BASE_URL", "http://127.0.0.1:8767"),
        view_token=token,
    )


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
    if not ensure_knowledge_graph("wisdom-oldman", recover=recover_runtime)["ready"]:
        raise KagUnavailableError("Knowledge graph unavailable; knowledge work is BLOCKED")
    answer = _reasoner().answer(
        question,
        requested_mode=ReasoningMode(mode.upper()),
        actor_id=actor_id,
        recover=recover_runtime,
        sync_projection=False,
    )
    if answer.get("runtime_status") != "KAG":
        raise KagUnavailableError("Graph reasoning failed; text-only fallback is blocked")
    return answer


@mcp.tool()
def knowledge_question_preflight(
    question: str,
    mode: str = "SIMPLE",
    recover_runtime: bool = False,
    uuma_task_id: str = "",
    uuma_run_id: str = "",
    notification_route_json: str = "{}",
    intent: str = "auto",
    topic_creation_approved: bool = False,
    topic_id: str = "",
) -> dict[str, Any]:
    """Read-only intake by default. Use intent=research only after interpreting conversation intent.

    Progress/status and feedback are operational, not research topics. Auto never writes knowledge.
    Research intent proposes new topics for user approval before creating them. Set
    topic_creation_approved only after a later user confirmation of the exact pending proposal.
    Existing topics are reused without a new creation permission.
    """
    actor_id = _actor()
    route = json.loads(notification_route_json)
    if not isinstance(route, dict) or any(not isinstance(value, str) for value in route.values()):
        raise ValueError("notification_route_json must contain a string-to-string object.")
    if intent not in {"auto", "research", "status", "feedback", "conversation",
                      "resume", "pause", "stop"}:
        raise ValueError("Unsupported message intent.")
    if is_progress_request(question):
        intent = "status"
    if is_machine_error_payload(question):
        intent = "feedback"
    control_intent = research_control_intent(question)
    if control_intent:
        intent = control_intent
    if intent in {"resume", "pause", "stop"}:
        return _control_existing_research(intent, route, actor_id, topic_id)
    if intent != "research":
        current_status = _topics().conversation_status(route)
        global_status = _global_research_status() if intent == "status" else None
        return {
            "message_intent": intent,
            "needs_intent_resolution": intent == "auto",
            "knowledge_mutated": False,
            "orbit_started": False,
            "research_continues": any(
                task["status"] in {"QUEUED", "ACTIVE"}
                for task in current_status["tasks"]
            ) or bool(global_status and global_status["active"]),
            "current_status": current_status,
            "global_status": global_status,
            "instruction": (
                "Interpret the user's message in its conversation context. For progress, report "
                "current_status and global_status, including reasons and document links. "
                "Feedback, errors and conversation must not create research. "
                "Resume/pause/stop only control an existing topic; specify topic_id if ambiguous. "
                "Only for a genuine topic/question/focus request, call this tool again with "
                "intent=research and the resolved research question, preserving the supplied "
                "notification route, task and run IDs. Do not treat citations as proof of relevance."
            ),
            "notification_route_json": notification_route_json,
            "uuma_task_id": uuma_task_id,
            "uuma_run_id": uuma_run_id,
        }
    question = research_question_text(question)
    resolved = _topics().resolve_question(
        question,
        actor_id=actor_id,
        route=route,
        allow_new_topic=topic_creation_approved,
    )
    if resolved.get("requires_topic_approval"):
        return resolved | {
            "orbit_started": False,
            "research_continues": False,
            "knowledge_mutated": False,
            "notification_route_json": notification_route_json,
            "uuma_task_id": uuma_task_id,
            "uuma_run_id": uuma_run_id,
        }
    if not ensure_knowledge_graph("wisdom-oldman", recover=recover_runtime)["ready"]:
        raise KagUnavailableError("Knowledge graph unavailable; knowledge work is BLOCKED")
    answer = _reasoner().answer(
        question,
        requested_mode=ReasoningMode(mode.upper()),
        actor_id=actor_id,
        recover=recover_runtime,
    )
    if answer.get("runtime_status") != "KAG":
        raise KagUnavailableError("Graph reasoning failed; no fallback answer or Orbit was started")
    citations = answer.get("citations") or []
    if not citations or not citations_fit_question(_service(), question, citations):
        answer = answer | {"citations": []}
    answer = grounded_answer(answer)
    if (
        resolved["match_kind"] == "new_topic"
        and _topics().is_broad_topic_request(question)
    ):
        framework_gap_ids = _topics().ensure_research_framework(
            resolved["topic"]["topic_id"],
            resolved["question"]["question_id"],
            actor_id=actor_id,
        )
        answer = answer | {
            "remaining_gap_ids": list(
                dict.fromkeys([*answer.get("remaining_gap_ids", []), *framework_gap_ids])
            )
        }
    enabled = os.environ.get("UUMA_QUESTION_ORBIT_ENABLED", "false").lower() in {
        "1", "true", "yes", "on"
    }
    if not enabled:
        result = {"answer": answer, "orbit_started": False, "orbit_enabled": False}
    else:
        result = _orbits().preflight(
            question,
            answer,
            actor_id=actor_id,
            uuma_task_id=uuma_task_id or None,
            uuma_run_id=uuma_run_id or None,
            notification_route=route,
            topic_id=resolved["topic"]["topic_id"],
            question_id=resolved["question"]["question_id"],
        )
        result["orbit_enabled"] = True
    research_status = str(result.get("orbit_status") or "ANSWERED")
    version = _topics().publish_answer(
        resolved["topic"]["topic_id"],
        resolved["question"]["question_id"],
        answer,
        actor_id=actor_id,
        research_status=research_status,
        orbit_id=result.get("orbit_id"),
        source_ids=[
            str(item["source_id"])
            for item in answer.get("citations", [])
            if isinstance(item, dict) and item.get("source_id")
        ],
        evidence_ids=[
            str(item["evidence_id"])
            for item in answer.get("citations", [])
            if isinstance(item, dict) and item.get("evidence_id")
        ],
    )
    runner_wake = _wake_orbit_runner(research_status)
    return {
        "document_url": version["document_url"],
        "topic_id": resolved["topic"]["topic_id"],
        "topic_title": resolved["topic"]["title"],
        "question_id": resolved["question"]["question_id"],
        "research_continues": result.get("orbit_status") in {"QUEUED", "ACTIVE"},
        "topic_match": {
            "kind": resolved["match_kind"],
            "score": resolved["match_score"],
        },
        "document_version": version["version"],
        "runner_wake": runner_wake,
        **result,
        "topic": resolved["topic"],
        "question": resolved["question"],
    }


@mcp.tool()
def knowledge_topic_get(topic_id: str) -> dict[str, Any]:
    """Return one durable topic, its latest readable document, questions, and research state."""
    _actor()
    return _topics().get_topic(topic_id)


@mcp.tool()
def knowledge_topic_list(limit: int = 100) -> dict[str, Any]:
    """List durable research topics shared across chat sessions."""
    _actor()
    return _topics().list_topics(limit=limit)


@mcp.tool()
def knowledge_topic_graph(topic_id: str) -> dict[str, Any]:
    """Return the read-only question, gap, source, and evidence neighborhood for a topic."""
    _actor()
    return _topics().graph(topic_id)


@mcp.tool()
def knowledge_orbit_start(
    question: str,
    objective: str,
    satisfaction_level: str,
    satisfaction_rationale: str,
    gap_ids_json: str = "[]",
    budget_tier: str = "QUICK",
    uuma_task_id: str = "",
    uuma_run_id: str = "",
    notification_route_json: str = "{}",
) -> dict[str, Any]:
    """Start or reuse a governed Orbit; automatic callers must use QUICK budget."""
    gap_ids = json.loads(gap_ids_json)
    route = json.loads(notification_route_json)
    if not isinstance(gap_ids, list) or any(not isinstance(value, str) for value in gap_ids):
        raise ValueError("gap_ids_json must contain a list of IDs.")
    if not isinstance(route, dict) or any(not isinstance(value, str) for value in route.values()):
        raise ValueError("notification_route_json must contain a string-to-string object.")
    started = _orbits().start(
        question,
        objective,
        SatisfactionLevel(satisfaction_level.upper()),
        satisfaction_rationale,
        actor_id=_actor(),
        gap_ids=gap_ids,
        budget_tier=BudgetTier(budget_tier.upper()),
        uuma_task_id=uuma_task_id or None,
        uuma_run_id=uuma_run_id or None,
        notification_route=route,
    )
    started["runner_wake"] = _wake_orbit_runner(started["orbit"]["status"])
    return started


@mcp.tool()
def knowledge_orbit_status(orbit_id: str) -> dict[str, Any]:
    """Return an Orbit, its research budget/state, and its ordered question frontier."""
    _actor()
    return _orbits().get(orbit_id)


@mcp.tool()
def knowledge_orbit_list(status: str = "", limit: int = 100) -> dict[str, Any]:
    """List durable Orbits, optionally filtered by lifecycle status."""
    _actor()
    return _orbits().list(status=status.upper() or None, limit=limit)


@mcp.tool()
def knowledge_orbit_frontier(orbit_id: str) -> dict[str, Any]:
    """Return the deterministic, explainable frontier order for one Orbit."""
    _actor()
    return _orbits().frontier(orbit_id)


@mcp.tool()
def knowledge_orbit_pause(orbit_id: str, reason: str = "Paused by user.") -> dict[str, Any]:
    """Pause an active or queued Orbit without deleting its state."""
    return _orbits().transition(orbit_id, OrbitStatus.PAUSED, actor_id=_actor(), reason=reason)


@mcp.tool()
def knowledge_orbit_resume(orbit_id: str) -> dict[str, Any]:
    """Return a paused or blocked Orbit to the durable runner queue."""
    orbit = _orbits().transition(orbit_id, OrbitStatus.QUEUED, actor_id=_actor())
    orbit["runner_wake"] = _wake_orbit_runner(orbit["status"])
    return orbit


@mcp.tool()
def knowledge_orbit_stop(orbit_id: str, reason: str) -> dict[str, Any]:
    """Stop an Orbit explicitly while preserving all state and event history."""
    return _orbits().transition(orbit_id, OrbitStatus.STOPPED, actor_id=_actor(), reason=reason)


@mcp.tool()
def knowledge_orbit_set_budget(orbit_id: str, budget_tier: str) -> dict[str, Any]:
    """Apply an explicit Orchestrator/user-review budget tier and resume an exhausted Orbit."""
    orbit = _orbits().set_budget(
        orbit_id, BudgetTier(budget_tier.upper()), actor_id=_actor()
    )
    orbit["runner_wake"] = _wake_orbit_runner(orbit["status"])
    return orbit


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
