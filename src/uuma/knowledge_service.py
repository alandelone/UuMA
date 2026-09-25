from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from .knowledge_models import (
    ChunkKnowledgeLink,
    ChunkRecord,
    ClaimEvidenceLink,
    ClaimRecord,
    ClaimStatus,
    ConflictRecord,
    DocumentVersionRecord,
    EntityRecord,
    EvidenceRecord,
    FreshnessPolicyRecord,
    GapRecord,
    KnowledgePatch,
    PatchOperation,
    PatchOperationKind,
    PatchStatus,
    QuestionRecord,
    ReasoningTraceRecord,
    RelationRecord,
    ResearchRun,
    ResearchRunStatus,
    SchemaModuleRecord,
    SourceRecord,
)
from .knowledge_store import TABLE_IDS, KnowledgeStore


class KnowledgeAuthorizationError(PermissionError):
    pass


class StaleKnowledgeError(RuntimeError):
    pass


def json_record(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


class KnowledgeService:
    WRITERS: ClassVar[set[str]] = {"wisdom-oldman", "orchestrator"}
    REVIEWERS: ClassVar[set[str]] = {"orchestrator"}
    RESEARCH_BUDGETS: ClassVar[dict[str, tuple[float, int, int]]] = {
        "QUICK": (600, 10, 50_000),
        "STANDARD": (3_600, 30, 250_000),
        "DEEP": (21_600, 100, 1_000_000),
    }
    ALWAYS_PROJECTED: ClassVar[set[str]] = {
        "sources",
        "evidence",
        "documents",
        "chunks",
        "freshness_policies",
    }
    ACCEPTED_ONLY_PROJECTED: ClassVar[set[str]] = {
        "claims", "entities", "relations", "schema_modules"
    }
    AGGREGATE_TYPES: ClassVar[dict[str, str]] = {
        "sources": "source",
        "evidence": "evidence",
        "documents": "document",
        "chunks": "chunk",
        "claims": "claim",
        "claim_evidence": "claim_evidence_link",
        "entities": "entity",
        "relations": "relation",
        "chunk_knowledge": "chunk_knowledge_link",
        "schema_modules": "schema_module",
        "freshness_policies": "freshness_policy",
        "questions": "question",
        "gaps": "gap",
        "conflicts": "conflict",
        "patches": "patch",
        "research_runs": "research_run",
        "reasoning_traces": "reasoning_trace",
        "question_orbits": "question_orbit",
        "orbit_frontier": "frontier_item",
        "orbit_cycles": "orbit_cycle",
        "discovery_usage": "discovery_usage",
        "orbit_notifications": "orbit_notification",
        "knowledge_topics": "knowledge_topic",
        "topic_question_links": "topic_question_link",
        "topic_knowledge_links": "topic_knowledge_link",
        "topic_documents": "topic_document",
        "topic_document_versions": "topic_document_version",
        "topic_routes": "topic_route",
    }

    def __init__(self, database_path: str | Path) -> None:
        self.store = KnowledgeStore(database_path)

    @classmethod
    def require_writer(cls, actor_id: str) -> None:
        if actor_id not in cls.WRITERS:
            raise KnowledgeAuthorizationError(
                "Knowledge writes are limited to Wisdom-Oldman and the Orchestrator."
            )

    @classmethod
    def require_reviewer(cls, actor_id: str) -> None:
        if actor_id not in cls.REVIEWERS:
            raise KnowledgeAuthorizationError(
                "Canonical patch decisions require the Orchestrator/user review boundary."
            )

    def _create(
        self,
        table: str,
        record: BaseModel,
        *,
        actor_id: str,
        event_type: str,
        index_kind: str | None = None,
        index_body: str = "",
    ) -> dict[str, Any]:
        self.require_writer(actor_id)
        payload = json_record(record)
        aggregate_id = payload[TABLE_IDS[table]]
        with self.store.transaction() as conn:
            event = self.store.append_event(
                conn,
                event_type=event_type,
                aggregate_type=self.AGGREGATE_TYPES.get(table, table.rstrip("s")),
                aggregate_id=aggregate_id,
                actor_id=actor_id,
                payload={"record": payload},
            )
            self.store.insert_record(conn, table, payload, event.sequence)
            if index_kind:
                self.store.index_text(conn, index_kind, aggregate_id, index_body)
            self._enqueue_if_projectable(conn, table, payload, event.sequence)
        return payload

    def _enqueue_if_projectable(
        self,
        conn,
        table: str,
        record: dict[str, Any],
        sequence: int,
        *,
        operation: str = "UPSERT",
    ) -> None:
        projectable = table in self.ALWAYS_PROJECTED
        if table in self.ACCEPTED_ONLY_PROJECTED:
            projectable = record.get("status") == ClaimStatus.ACCEPTED.value
        elif table == "claim_evidence":
            claim = self._require("claims", record["claim_id"], conn)
            projectable = claim.get("status") == ClaimStatus.ACCEPTED.value
        elif table == "chunk_knowledge":
            if record["target_kind"] == "evidence":
                projectable = True
            elif record["target_kind"] in {"claim", "entity", "relation"}:
                target_table = {
                    "claim": "claims",
                    "entity": "entities",
                    "relation": "relations",
                }[record["target_kind"]]
                target = self._require(target_table, record["target_id"], conn)
                projectable = target.get("status") == ClaimStatus.ACCEPTED.value
        if not projectable:
            return
        self.store.enqueue_projection(
            conn,
            event_sequence=sequence,
            aggregate_type=self.AGGREGATE_TYPES[table],
            aggregate_id=record[TABLE_IDS[table]],
            operation=operation,
            payload={"record": record},
        )

    def _enqueue_projection_transition(
        self,
        conn,
        table: str,
        before: dict[str, Any],
        after: dict[str, Any],
        sequence: int,
    ) -> None:
        if table not in self.ACCEPTED_ONLY_PROJECTED:
            self._enqueue_if_projectable(conn, table, after, sequence)
            return
        was_accepted = before.get("status") == ClaimStatus.ACCEPTED.value
        is_accepted = after.get("status") == ClaimStatus.ACCEPTED.value
        if is_accepted:
            self._enqueue_if_projectable(conn, table, after, sequence)
        elif was_accepted:
            self.store.enqueue_projection(
                conn,
                event_sequence=sequence,
                aggregate_type=self.AGGREGATE_TYPES[table],
                aggregate_id=after[TABLE_IDS[table]],
                operation="DELETE",
                payload={"record": after, "previous_record": before},
            )
        if was_accepted != is_accepted:
            self._enqueue_dependent_links(
                conn,
                table,
                after[TABLE_IDS[table]],
                sequence,
                operation="UPSERT" if is_accepted else "DELETE",
            )

    def _enqueue_dependent_links(
        self, conn, table: str, record_id: str, sequence: int, *, operation: str
    ) -> None:
        if table == "claims":
            rows = conn.execute(
                "SELECT record_json FROM claim_evidence WHERE claim_id = ?", (record_id,)
            ).fetchall()
            for row in rows:
                record = json.loads(row["record_json"])
                self.store.enqueue_projection(
                    conn,
                    event_sequence=sequence,
                    aggregate_type=self.AGGREGATE_TYPES["claim_evidence"],
                    aggregate_id=record["link_id"],
                    operation=operation,
                    payload={"record": record},
                )
        target_kind = {
            "claims": "claim",
            "entities": "entity",
            "relations": "relation",
        }.get(table)
        if target_kind:
            rows = conn.execute(
                "SELECT record_json FROM chunk_knowledge "
                "WHERE target_kind = ? AND target_id = ?",
                (target_kind, record_id),
            ).fetchall()
            for row in rows:
                record = json.loads(row["record_json"])
                self.store.enqueue_projection(
                    conn,
                    event_sequence=sequence,
                    aggregate_type=self.AGGREGATE_TYPES["chunk_knowledge"],
                    aggregate_id=record["chunk_knowledge_link_id"],
                    operation=operation,
                    payload={"record": record},
                )

    def add_source(self, source: SourceRecord, *, actor_id: str) -> dict[str, Any]:
        body = " ".join(
            part for part in (source.title, source.publisher or "", source.locator) if part
        )
        return self._create(
            "sources",
            source,
            actor_id=actor_id,
            event_type="SOURCE_ADDED",
            index_kind="source",
            index_body=body,
        )

    def add_evidence(self, evidence: EvidenceRecord, *, actor_id: str) -> dict[str, Any]:
        self._require("sources", evidence.source_id)
        return self._create(
            "evidence",
            evidence,
            actor_id=actor_id,
            event_type="EVIDENCE_ADDED",
            index_kind="evidence",
            index_body=" ".join(
                part
                for part in (evidence.excerpt, evidence.surrounding_context or "", evidence.location or "")
                if part
            ),
        )

    def add_document(
        self, document: DocumentVersionRecord, *, actor_id: str
    ) -> dict[str, Any]:
        self._require("sources", document.source_id)
        if document.previous_document_id:
            previous = self._require("documents", document.previous_document_id)
            if previous["source_id"] != document.source_id:
                raise ValueError("previous_document_id belongs to another source.")
            if document.version != int(previous["version"]) + 1:
                raise ValueError("A document version must increment its predecessor by one.")
        return self._create(
            "documents",
            document,
            actor_id=actor_id,
            event_type="DOCUMENT_VERSION_ADDED",
            index_kind="document",
            index_body=f"{document.content_ref} {document.media_type} {document.language}",
        )

    def add_chunk(self, chunk: ChunkRecord, *, actor_id: str) -> dict[str, Any]:
        self._require("documents", chunk.document_id)
        return self._create(
            "chunks",
            chunk,
            actor_id=actor_id,
            event_type="CHUNK_ADDED",
            index_kind="chunk",
            index_body=f"{chunk.text} {chunk.location or ''}",
        )

    def propose_claim(self, claim: ClaimRecord, *, actor_id: str) -> dict[str, Any]:
        if claim.status != ClaimStatus.CANDIDATE:
            raise ValueError("New claims must enter the knowledge system as CANDIDATE.")
        return self._create(
            "claims",
            claim,
            actor_id=actor_id,
            event_type="CLAIM_PROPOSED",
            index_kind="claim",
            index_body=" ".join(
                part
                for part in (
                    claim.statement,
                    claim.subject or "",
                    claim.predicate or "",
                    claim.object or "",
                    json.dumps(claim.qualifiers, ensure_ascii=False),
                )
                if part
            ),
        )

    def link_evidence(self, link: ClaimEvidenceLink, *, actor_id: str) -> dict[str, Any]:
        self._require("claims", link.claim_id)
        self._require("evidence", link.evidence_id)
        return self._create(
            "claim_evidence",
            link,
            actor_id=actor_id,
            event_type="EVIDENCE_LINKED",
        )

    def propose_entity(self, entity: EntityRecord, *, actor_id: str) -> dict[str, Any]:
        if entity.status != ClaimStatus.CANDIDATE:
            raise ValueError("New entities must enter as CANDIDATE.")
        if entity.schema_module_id:
            self._require("schema_modules", entity.schema_module_id)
        aliases = " ".join(alias for values in entity.aliases.values() for alias in values)
        return self._create(
            "entities",
            entity,
            actor_id=actor_id,
            event_type="ENTITY_PROPOSED",
            index_kind="entity",
            index_body=f"{entity.canonical_name} {entity.entity_type} {aliases}",
        )

    def propose_relation(self, relation: RelationRecord, *, actor_id: str) -> dict[str, Any]:
        if relation.status != ClaimStatus.CANDIDATE:
            raise ValueError("New relations must enter as CANDIDATE.")
        self._require("entities", relation.subject_entity_id)
        if relation.object_entity_id:
            self._require("entities", relation.object_entity_id)
        if relation.schema_module_id:
            self._require("schema_modules", relation.schema_module_id)
        for claim_id in relation.claim_ids:
            self._require("claims", claim_id)
        return self._create(
            "relations",
            relation,
            actor_id=actor_id,
            event_type="RELATION_PROPOSED",
            index_kind="relation",
            index_body=(
                f"{relation.subject_entity_id} {relation.predicate} "
                f"{relation.object_entity_id or relation.literal_value} "
                f"{json.dumps(relation.qualifiers, ensure_ascii=False)}"
            ),
        )

    def link_chunk(self, link: ChunkKnowledgeLink, *, actor_id: str) -> dict[str, Any]:
        self._require("chunks", link.chunk_id)
        target_tables = {
            "entity": "entities",
            "relation": "relations",
            "claim": "claims",
            "evidence": "evidence",
        }
        self._require(target_tables[link.target_kind], link.target_id)
        return self._create(
            "chunk_knowledge",
            link,
            actor_id=actor_id,
            event_type="CHUNK_KNOWLEDGE_LINKED",
        )

    def propose_schema_module(
        self, module: SchemaModuleRecord, *, actor_id: str
    ) -> dict[str, Any]:
        if module.status != ClaimStatus.CANDIDATE:
            raise ValueError("New schema modules must enter as CANDIDATE.")
        return self._create(
            "schema_modules",
            module,
            actor_id=actor_id,
            event_type="SCHEMA_MODULE_PROPOSED",
            index_kind="schema_module",
            index_body=(
                f"{module.name} {module.description} "
                f"{json.dumps(module.entity_types, ensure_ascii=False)} "
                f"{json.dumps(module.predicates, ensure_ascii=False)}"
            ),
        )

    def add_freshness_policy(
        self, policy: FreshnessPolicyRecord, *, actor_id: str
    ) -> dict[str, Any]:
        table = {
            "source": "sources",
            "document": "documents",
            "evidence": "evidence",
            "claim": "claims",
            "entity": "entities",
            "relation": "relations",
        }[policy.target_kind]
        self._require(table, policy.target_id)
        return self._create(
            "freshness_policies",
            policy,
            actor_id=actor_id,
            event_type="FRESHNESS_POLICY_ADDED",
        )

    def record_reasoning_trace(
        self, trace: ReasoningTraceRecord, *, actor_id: str
    ) -> dict[str, Any]:
        return self._create(
            "reasoning_traces",
            trace,
            actor_id=actor_id,
            event_type="REASONING_TRACE_RECORDED",
        )

    def add_question(self, question: QuestionRecord, *, actor_id: str) -> dict[str, Any]:
        if question.parent_question_id:
            self._require("questions", question.parent_question_id)
        return self._create(
            "questions",
            question,
            actor_id=actor_id,
            event_type="QUESTION_ADDED",
            index_kind="question",
            index_body=f"{question.text} {question.why_worth_knowing}",
        )

    def add_gap(self, gap: GapRecord, *, actor_id: str) -> dict[str, Any]:
        if gap.question_id:
            self._require("questions", gap.question_id)
        for claim_id in gap.related_claim_ids:
            self._require("claims", claim_id)
        return self._create(
            "gaps",
            gap,
            actor_id=actor_id,
            event_type="GAP_ADDED",
            index_kind="gap",
            index_body=" ".join(
                part
                for part in (gap.reason, gap.why_worthwhile, gap.current_knowledge or "")
                if part
            ),
        )

    def record_conflict(self, conflict: ConflictRecord, *, actor_id: str) -> dict[str, Any]:
        if len(set(conflict.claim_ids)) < 2:
            raise ValueError("A conflict requires at least two distinct claims.")
        for claim_id in conflict.claim_ids:
            self._require("claims", claim_id)
        return self._create(
            "conflicts",
            conflict,
            actor_id=actor_id,
            event_type="CONFLICT_RECORDED",
            index_kind="conflict",
            index_body=f"{conflict.description} {conflict.context_analysis or ''}",
        )

    def start_research_run(self, run: ResearchRun, *, actor_id: str) -> dict[str, Any]:
        if run.root_question_id:
            self._require("questions", run.root_question_id)
        for gap_id in run.active_gap_ids:
            self._require("gaps", gap_id)
        run = self._enforce_research_budget(run)
        return self._create(
            "research_runs",
            run,
            actor_id=actor_id,
            event_type="RESEARCH_RUN_STARTED",
            index_kind="research_run",
            index_body=f"{run.objective} {run.satisfaction_rationale}",
        )

    def update_research_run(
        self, research_run_id: str, changes: dict[str, Any], *, actor_id: str
    ) -> dict[str, Any]:
        self.require_writer(actor_id)
        allowed = {
            "status",
            "active_gap_ids",
            "knowledge_satisfaction",
            "satisfaction_level",
            "satisfaction_rationale",
            "budget_tier",
            "active_seconds",
            "sources_used",
            "model_tokens_used",
            "current_question_id",
            "cycle_count",
            "search_queries_used",
            "stop_reason",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"Unsupported research run fields: {sorted(unexpected)}")
        with self.store.transaction() as conn:
            before = self._require("research_runs", research_run_id, conn)
            after = dict(before) | changes | {"updated_at": datetime.now(UTC).isoformat()}
            for gap_id in after["active_gap_ids"]:
                self._require("gaps", gap_id, conn)
            after_model = ResearchRun.model_validate(after)
            after = json_record(self._enforce_research_budget(after_model))
            event = self.store.append_event(
                conn,
                event_type="RESEARCH_RUN_UPDATED",
                aggregate_type="research_run",
                aggregate_id=research_run_id,
                actor_id=actor_id,
                payload={"before": before, "after": after},
            )
            self.store.update_record(conn, "research_runs", after, event.sequence)
            self.store.index_text(
                conn,
                "research_run",
                research_run_id,
                f"{after['objective']} {after['satisfaction_rationale']}",
            )
        return after

    @classmethod
    def _enforce_research_budget(cls, run: ResearchRun) -> ResearchRun:
        if run.status.value not in {"PLANNED", "ACTIVE", "PAUSED"}:
            return run
        seconds, sources, tokens = cls.RESEARCH_BUDGETS[run.budget_tier.value]
        exhausted = []
        if run.active_seconds >= seconds:
            exhausted.append(f"active time {run.active_seconds:g}/{seconds:g} seconds")
        if run.sources_used >= sources:
            exhausted.append(f"sources {run.sources_used}/{sources}")
        if run.model_tokens_used >= tokens:
            exhausted.append(f"model tokens {run.model_tokens_used}/{tokens}")
        if not exhausted:
            return run
        return ResearchRun.model_validate(
            run.model_dump()
            | {
                "status": ResearchRunStatus.BUDGET_EXHAUSTED,
                "stop_reason": "Research budget exhausted: " + ", ".join(exhausted) + ".",
            }
        )

    def propose_patch(self, patch: KnowledgePatch, *, actor_id: str) -> dict[str, Any]:
        self.require_writer(actor_id)
        if patch.status != PatchStatus.PROPOSED:
            raise ValueError("A new patch must have PROPOSED status.")
        if patch.proposed_by != actor_id:
            raise ValueError("proposed_by must match the authenticated actor.")
        diff = [
            change
            for operation in patch.operations
            for change in self._preview_operation(operation)
        ]
        patch = patch.model_copy(update={"diff": diff})
        return self._create(
            "patches", patch, actor_id=actor_id, event_type="PATCH_PROPOSED"
        )

    def apply_patch(
        self, patch_id: str, *, actor_id: str, review_note: str
    ) -> dict[str, Any]:
        self.require_reviewer(actor_id)
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            patch_data = self._require("patches", patch_id, conn)
            patch = KnowledgePatch.model_validate(patch_data)
            if patch.status != PatchStatus.PROPOSED:
                raise ValueError(f"Patch {patch_id} is {patch.status}; only PROPOSED can be applied.")
            for proposed_change in patch.diff:
                table = self._table_for_id(proposed_change["target_id"])
                current = self._require(table, proposed_change["target_id"], conn)
                if current != proposed_change["before"]:
                    raise StaleKnowledgeError(
                        f"{proposed_change['target_id']} changed after this patch was proposed."
                    )
            undo: list[dict[str, Any]] = []
            applied_diff: list[dict[str, Any]] = []
            for operation in patch.operations:
                changes = self._apply_operation(conn, operation, actor_id=actor_id, undo=undo)
                applied_diff.extend(changes)
            patch = patch.model_copy(
                update={
                    "status": PatchStatus.APPLIED,
                    "review_note": review_note,
                    "diff": applied_diff,
                    "undo": undo,
                    "updated_at": now,
                }
            )
            payload = json_record(patch)
            event = self.store.append_event(
                conn,
                event_type="PATCH_APPLIED",
                aggregate_type="patch",
                aggregate_id=patch_id,
                actor_id=actor_id,
                payload={"diff": applied_diff, "review_note": review_note},
            )
            self.store.update_record(conn, "patches", payload, event.sequence)
        return payload

    def reject_patch(
        self, patch_id: str, *, actor_id: str, review_note: str
    ) -> dict[str, Any]:
        self.require_reviewer(actor_id)
        with self.store.transaction() as conn:
            patch = KnowledgePatch.model_validate(self._require("patches", patch_id, conn))
            if patch.status != PatchStatus.PROPOSED:
                raise ValueError("Only a proposed patch can be rejected.")
            patch = patch.model_copy(
                update={
                    "status": PatchStatus.REJECTED,
                    "review_note": review_note,
                    "updated_at": datetime.now(UTC),
                }
            )
            payload = json_record(patch)
            event = self.store.append_event(
                conn,
                event_type="PATCH_REJECTED",
                aggregate_type="patch",
                aggregate_id=patch_id,
                actor_id=actor_id,
                payload={"review_note": review_note},
            )
            self.store.update_record(conn, "patches", payload, event.sequence)
        return payload

    def reverse_patch(
        self, patch_id: str, *, actor_id: str, review_note: str
    ) -> dict[str, Any]:
        self.require_reviewer(actor_id)
        with self.store.transaction() as conn:
            patch = KnowledgePatch.model_validate(self._require("patches", patch_id, conn))
            if patch.status != PatchStatus.APPLIED:
                raise ValueError("Only an applied patch can be reversed.")
            for applied_change in patch.diff:
                table = self._table_for_id(applied_change["target_id"])
                current = self._require(table, applied_change["target_id"], conn)
                if current != applied_change["after"]:
                    raise StaleKnowledgeError(
                        f"{applied_change['target_id']} has newer changes; reverse those first."
                    )
            self._assert_reversal_dependencies(conn, patch.undo)
            for item in reversed(patch.undo):
                table = item["table"]
                before = item["record"]
                current = self._require(table, before[TABLE_IDS[table]], conn)
                event = self.store.append_event(
                    conn,
                    event_type="KNOWLEDGE_CHANGE_REVERSED",
                    aggregate_type=table.rstrip("s"),
                    aggregate_id=before[TABLE_IDS[table]],
                    actor_id=actor_id,
                    payload={"patch_id": patch_id, "restored": before},
                )
                self.store.update_record(conn, table, before, event.sequence)
                self._reindex(conn, table, before)
                self._enqueue_projection_transition(
                    conn, table, current, before, event.sequence
                )
            patch = patch.model_copy(
                update={
                    "status": PatchStatus.REVERSED,
                    "review_note": review_note,
                    "updated_at": datetime.now(UTC),
                }
            )
            payload = json_record(patch)
            event = self.store.append_event(
                conn,
                event_type="PATCH_REVERSED",
                aggregate_type="patch",
                aggregate_id=patch_id,
                actor_id=actor_id,
                payload={"review_note": review_note},
            )
            self.store.update_record(conn, "patches", payload, event.sequence)
        return payload

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        rows = self.store.search(query, limit)
        return {"query": query, "count": len(rows), "results": rows}

    def get(self, object_id: str) -> dict[str, Any]:
        prefix_to_table = {
            "src_": "sources",
            "ev_": "evidence",
            "doc_": "documents",
            "chunk_": "chunks",
            "claim_": "claims",
            "link_": "claim_evidence",
            "entity_": "entities",
            "relation_": "relations",
            "cklink_": "chunk_knowledge",
            "schema_": "schema_modules",
            "freshness_": "freshness_policies",
            "trace_": "reasoning_traces",
            "question_": "questions",
            "gap_": "gaps",
            "conflict_": "conflicts",
            "patch_": "patches",
            "research_": "research_runs",
            "orbit_": "question_orbits",
            "frontier_": "orbit_frontier",
            "cycle_": "orbit_cycles",
            "usage_": "discovery_usage",
            "notice_": "orbit_notifications",
            "topic_": "knowledge_topics",
            "tqlink_": "topic_question_links",
            "tklink_": "topic_knowledge_links",
            "topicdoc_": "topic_documents",
            "topicver_": "topic_document_versions",
            "topicroute_": "topic_routes",
        }
        table = next((value for prefix, value in prefix_to_table.items() if object_id.startswith(prefix)), None)
        if table is None:
            raise KeyError(object_id)
        record = self._require(table, object_id)
        result: dict[str, Any] = {
            "kind": self.AGGREGATE_TYPES.get(table, table.rstrip("s")),
            "record": record,
        }
        with self.store.connect() as conn:
            if table == "claims":
                rows = conn.execute(
                    "SELECT record_json FROM claim_evidence WHERE claim_id = ?", (object_id,)
                ).fetchall()
                links = [json.loads(row["record_json"]) for row in rows]
                result["evidence_links"] = links
                result["evidence"] = [
                    self._require("evidence", link["evidence_id"], conn) for link in links
                ]
            elif table == "evidence":
                result["source"] = self._require("sources", record["source_id"], conn)
            elif table == "documents":
                result["source"] = self._require("sources", record["source_id"], conn)
                rows = conn.execute(
                    "SELECT record_json FROM chunks WHERE document_id = ? ORDER BY ordinal",
                    (object_id,),
                ).fetchall()
                result["chunks"] = [json.loads(row["record_json"]) for row in rows]
            elif table == "chunks":
                document = self._require("documents", record["document_id"], conn)
                result["document"] = document
                result["source"] = self._require("sources", document["source_id"], conn)
                rows = conn.execute(
                    "SELECT record_json FROM chunk_knowledge WHERE chunk_id = ?",
                    (object_id,),
                ).fetchall()
                result["knowledge_links"] = [json.loads(row["record_json"]) for row in rows]
            elif table == "entities":
                outgoing = conn.execute(
                    "SELECT record_json FROM relations WHERE subject_entity_id = ?",
                    (object_id,),
                ).fetchall()
                incoming = conn.execute(
                    "SELECT record_json FROM relations WHERE object_entity_id = ?",
                    (object_id,),
                ).fetchall()
                result["outgoing_relations"] = [json.loads(row["record_json"]) for row in outgoing]
                result["incoming_relations"] = [json.loads(row["record_json"]) for row in incoming]
            elif table == "relations":
                result["subject"] = self._require(
                    "entities", record["subject_entity_id"], conn
                )
                if record.get("object_entity_id"):
                    result["object"] = self._require(
                        "entities", record["object_entity_id"], conn
                    )
                result["claims"] = [
                    self._require("claims", claim_id, conn)
                    for claim_id in record.get("claim_ids", [])
                ]
        return result

    def list_records(
        self, kind: str, *, status: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        kind_to_table = {
            "source": "sources",
            "evidence": "evidence",
            "document": "documents",
            "chunk": "chunks",
            "claim": "claims",
            "claim_evidence_link": "claim_evidence",
            "entity": "entities",
            "relation": "relations",
            "chunk_knowledge_link": "chunk_knowledge",
            "schema_module": "schema_modules",
            "freshness_policy": "freshness_policies",
            "reasoning_trace": "reasoning_traces",
            "question": "questions",
            "gap": "gaps",
            "conflict": "conflicts",
            "patch": "patches",
            "research_run": "research_runs",
            "question_orbit": "question_orbits",
            "frontier_item": "orbit_frontier",
            "orbit_cycle": "orbit_cycles",
            "discovery_usage": "discovery_usage",
            "orbit_notification": "orbit_notifications",
            "knowledge_topic": "knowledge_topics",
            "topic_question_link": "topic_question_links",
            "topic_knowledge_link": "topic_knowledge_links",
            "topic_document": "topic_documents",
            "topic_document_version": "topic_document_versions",
            "topic_route": "topic_routes",
        }
        table = kind_to_table.get(kind)
        if table is None:
            raise ValueError(f"Unknown knowledge kind: {kind}")
        records = self.store.list_records(table, status=status, limit=limit)
        return {"kind": kind, "count": len(records), "records": records}

    def projection_health(self) -> dict[str, Any]:
        return self.store.projection_health()

    def graph_neighborhood(
        self, entity_id: str, *, depth: int = 1, limit: int = 100
    ) -> dict[str, Any]:
        self._require("entities", entity_id)
        depth = max(1, min(depth, 3))
        limit = max(1, min(limit, 500))
        seen_entities = {entity_id}
        frontier = {entity_id}
        relations: dict[str, dict[str, Any]] = {}
        with self.store.connect() as conn:
            for _ in range(depth):
                if not frontier or len(relations) >= limit:
                    break
                placeholders = ",".join("?" for _ in frontier)
                rows = conn.execute(
                    f"SELECT record_json FROM relations WHERE status = 'ACCEPTED' "
                    f"AND (subject_entity_id IN ({placeholders}) "
                    f"OR object_entity_id IN ({placeholders})) LIMIT ?",
                    (*frontier, *frontier, limit - len(relations)),
                ).fetchall()
                next_frontier: set[str] = set()
                for row in rows:
                    relation = json.loads(row["record_json"])
                    relations[relation["relation_id"]] = relation
                    for candidate in (
                        relation["subject_entity_id"], relation.get("object_entity_id")
                    ):
                        if candidate and candidate not in seen_entities:
                            next_frontier.add(candidate)
                seen_entities.update(next_frontier)
                frontier = next_frontier
            entities = [self._require("entities", item, conn) for item in seen_entities]
        return {
            "root_entity_id": entity_id,
            "depth": depth,
            "entities": entities,
            "relations": list(relations.values()),
            "truncated": len(relations) >= limit,
        }

    def history(self, aggregate_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        events = [event.model_dump(mode="json") for event in self.store.iter_events(
            aggregate_id=aggregate_id, limit=limit
        )]
        valid, broken_sequence, broken_event = self.store.verify_chain()
        return {
            "count": len(events),
            "events": events,
            "chain_valid": valid,
            "broken_sequence": broken_sequence,
            "broken_event": broken_event,
        }

    def patch_diff(self, patch_id: str) -> dict[str, Any]:
        patch = self._require("patches", patch_id)
        return {
            "patch_id": patch_id,
            "status": patch["status"],
            "rationale": patch["rationale"],
            "diff": patch["diff"],
            "review_note": patch["review_note"],
        }

    def _preview_operation(self, operation: PatchOperation) -> list[dict[str, Any]]:
        table = self._operation_table(operation.kind)
        before = self._require(table, operation.target_id)
        after = dict(before)
        if operation.kind == PatchOperationKind.SUPERSEDE_CLAIM:
            replacement_id = operation.changes.get("replacement_claim_id")
            if not replacement_id:
                raise ValueError("SUPERSEDE_CLAIM requires replacement_claim_id.")
            after.update(
                {
                    "status": ClaimStatus.SUPERSEDED.value,
                    "superseded_by": replacement_id,
                }
            )
        else:
            after.update(operation.changes)
        if operation.kind in {
            PatchOperationKind.ACCEPT_CLAIM,
            PatchOperationKind.ACCEPT_ENTITY,
            PatchOperationKind.ACCEPT_RELATION,
            PatchOperationKind.ACCEPT_SCHEMA_MODULE,
        }:
            after["status"] = ClaimStatus.ACCEPTED.value
        changes = [{
            "kind": operation.kind.value,
            "target_id": operation.target_id,
            "before": before,
            "proposed": after,
        }]
        if operation.kind == PatchOperationKind.SUPERSEDE_CLAIM:
            replacement_id = operation.changes.get("replacement_claim_id")
            assert replacement_id is not None
            replacement = self._require("claims", replacement_id)
            proposed_replacement = dict(replacement)
            proposed_replacement["status"] = ClaimStatus.ACCEPTED.value
            changes.append(
                {
                    "kind": operation.kind.value,
                    "target_id": replacement_id,
                    "before": replacement,
                    "proposed": proposed_replacement,
                }
            )
        return changes

    def _assert_reversal_dependencies(self, conn, undo: list[dict[str, Any]]) -> None:
        restored = {
            (item["table"], item["record"][TABLE_IDS[item["table"]]]): item["record"]
            for item in undo
        }

        def effective(table: str, record_id: str) -> dict[str, Any]:
            return restored.get((table, record_id)) or self._require(table, record_id, conn)

        relation_rows = conn.execute("SELECT record_json FROM relations").fetchall()
        for row in relation_rows:
            current = json.loads(row["record_json"])
            relation = effective("relations", current["relation_id"])
            if relation.get("status") != ClaimStatus.ACCEPTED.value:
                continue
            dependencies = [
                effective("entities", relation["subject_entity_id"]),
                *(
                    [effective("entities", relation["object_entity_id"])]
                    if relation.get("object_entity_id")
                    else []
                ),
                *[effective("claims", claim_id) for claim_id in relation.get("claim_ids", [])],
                *(
                    [effective("schema_modules", relation["schema_module_id"])]
                    if relation.get("schema_module_id")
                    else []
                ),
            ]
            if any(item.get("status") != ClaimStatus.ACCEPTED.value for item in dependencies):
                raise StaleKnowledgeError(
                    f"Reversal would leave accepted relation {relation['relation_id']} "
                    "with a non-accepted dependency."
                )

        entity_rows = conn.execute("SELECT record_json FROM entities").fetchall()
        for row in entity_rows:
            current = json.loads(row["record_json"])
            entity = effective("entities", current["entity_id"])
            schema_id = entity.get("schema_module_id")
            if (
                entity.get("status") == ClaimStatus.ACCEPTED.value
                and schema_id
                and effective("schema_modules", schema_id).get("status")
                != ClaimStatus.ACCEPTED.value
            ):
                raise StaleKnowledgeError(
                    f"Reversal would leave accepted entity {entity['entity_id']} "
                    "with a non-accepted schema module."
                )

    def _apply_operation(
        self,
        conn,
        operation: PatchOperation,
        *,
        actor_id: str,
        undo: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        table = self._operation_table(operation.kind)
        before = self._require(table, operation.target_id, conn)
        changes: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        now = datetime.now(UTC).isoformat()

        if operation.kind in {PatchOperationKind.ACCEPT_CLAIM, PatchOperationKind.UPDATE_CLAIM}:
            after = dict(before)
            allowed = {"statement", "subject", "predicate", "object", "qualifiers", "valid_from", "valid_until"}
            unexpected = set(operation.changes) - allowed
            if operation.kind == PatchOperationKind.ACCEPT_CLAIM and operation.changes:
                raise ValueError("ACCEPT_CLAIM does not accept field changes.")
            if unexpected:
                raise ValueError(f"Unsupported claim fields: {sorted(unexpected)}")
            after.update(operation.changes)
            if operation.kind == PatchOperationKind.ACCEPT_CLAIM:
                after["status"] = ClaimStatus.ACCEPTED.value
            after["revision"] = int(before["revision"]) + 1
            after["updated_at"] = now
            after = json_record(ClaimRecord.model_validate(after))
            changes.append(("claims", before, after))
        elif operation.kind in {
            PatchOperationKind.ACCEPT_ENTITY,
            PatchOperationKind.UPDATE_ENTITY,
        }:
            after = dict(before)
            allowed = {"canonical_name", "entity_type", "aliases", "properties", "schema_module_id"}
            unexpected = set(operation.changes) - allowed
            if operation.kind == PatchOperationKind.ACCEPT_ENTITY and operation.changes:
                raise ValueError("ACCEPT_ENTITY does not accept field changes.")
            if unexpected:
                raise ValueError(f"Unsupported entity fields: {sorted(unexpected)}")
            after.update(operation.changes)
            if after.get("schema_module_id"):
                schema = self._require("schema_modules", after["schema_module_id"], conn)
                if (
                    (
                        operation.kind == PatchOperationKind.ACCEPT_ENTITY
                        or after.get("status") == ClaimStatus.ACCEPTED.value
                    )
                    and schema.get("status") != ClaimStatus.ACCEPTED.value
                ):
                    raise ValueError("An accepted entity requires an accepted schema module.")
            if operation.kind == PatchOperationKind.ACCEPT_ENTITY:
                after["status"] = ClaimStatus.ACCEPTED.value
            after["revision"] = int(before["revision"]) + 1
            after["updated_at"] = now
            changes.append(("entities", before, json_record(EntityRecord.model_validate(after))))
        elif operation.kind in {
            PatchOperationKind.ACCEPT_RELATION,
            PatchOperationKind.UPDATE_RELATION,
        }:
            after = dict(before)
            allowed = {
                "subject_entity_id", "predicate", "object_entity_id", "literal_value",
                "qualifiers", "claim_ids", "schema_module_id",
            }
            unexpected = set(operation.changes) - allowed
            if operation.kind == PatchOperationKind.ACCEPT_RELATION and operation.changes:
                raise ValueError("ACCEPT_RELATION does not accept field changes.")
            if unexpected:
                raise ValueError(f"Unsupported relation fields: {sorted(unexpected)}")
            after.update(operation.changes)
            subject = self._require("entities", after["subject_entity_id"], conn)
            object_entity = None
            if after.get("object_entity_id"):
                object_entity = self._require("entities", after["object_entity_id"], conn)
            claims = []
            for claim_id in after.get("claim_ids", []):
                claims.append(self._require("claims", claim_id, conn))
            schema = None
            if after.get("schema_module_id"):
                schema = self._require("schema_modules", after["schema_module_id"], conn)
            will_be_accepted = (
                operation.kind == PatchOperationKind.ACCEPT_RELATION
                or after.get("status") == ClaimStatus.ACCEPTED.value
            )
            if will_be_accepted:
                dependencies = [subject, object_entity, schema, *claims]
                if any(
                    item is not None and item.get("status") != ClaimStatus.ACCEPTED.value
                    for item in dependencies
                ):
                    raise ValueError(
                        "An accepted relation requires accepted entity, claim, and schema dependencies."
                    )
            if operation.kind == PatchOperationKind.ACCEPT_RELATION:
                after["status"] = ClaimStatus.ACCEPTED.value
            after["revision"] = int(before["revision"]) + 1
            after["updated_at"] = now
            changes.append(("relations", before, json_record(RelationRecord.model_validate(after))))
        elif operation.kind in {
            PatchOperationKind.ACCEPT_SCHEMA_MODULE,
            PatchOperationKind.UPDATE_SCHEMA_MODULE,
        }:
            after = dict(before)
            allowed = {"description", "entity_types", "predicates", "constraints", "logical_rules"}
            unexpected = set(operation.changes) - allowed
            if operation.kind == PatchOperationKind.ACCEPT_SCHEMA_MODULE and operation.changes:
                raise ValueError("ACCEPT_SCHEMA_MODULE does not accept field changes.")
            if unexpected:
                raise ValueError(f"Unsupported schema module fields: {sorted(unexpected)}")
            after.update(operation.changes)
            if operation.kind == PatchOperationKind.ACCEPT_SCHEMA_MODULE:
                after["status"] = ClaimStatus.ACCEPTED.value
            after["revision"] = int(before["revision"]) + 1
            after["updated_at"] = now
            changes.append(("schema_modules", before, json_record(SchemaModuleRecord.model_validate(after))))
        elif operation.kind == PatchOperationKind.UPDATE_FRESHNESS:
            after = dict(before)
            allowed = {
                "review_interval_days", "volatility", "status", "last_verified_at",
                "next_review_at", "stale_reason",
            }
            unexpected = set(operation.changes) - allowed
            if unexpected:
                raise ValueError(f"Unsupported freshness fields: {sorted(unexpected)}")
            after.update(operation.changes)
            after["updated_at"] = now
            changes.append(
                ("freshness_policies", before, json_record(FreshnessPolicyRecord.model_validate(after)))
            )
        elif operation.kind == PatchOperationKind.SUPERSEDE_CLAIM:
            replacement_id = operation.changes.get("replacement_claim_id")
            if not replacement_id:
                raise ValueError("SUPERSEDE_CLAIM requires replacement_claim_id.")
            replacement_before = self._require("claims", replacement_id, conn)
            old_after = dict(before) | {
                "status": ClaimStatus.SUPERSEDED.value,
                "superseded_by": replacement_id,
                "revision": int(before["revision"]) + 1,
                "updated_at": now,
            }
            replacement_after = dict(replacement_before) | {
                "status": ClaimStatus.ACCEPTED.value,
                "revision": int(replacement_before["revision"]) + 1,
                "updated_at": now,
            }
            changes.extend(
                [
                    ("claims", before, json_record(ClaimRecord.model_validate(old_after))),
                    (
                        "claims",
                        replacement_before,
                        json_record(ClaimRecord.model_validate(replacement_after)),
                    ),
                ]
            )
        elif operation.kind == PatchOperationKind.UPDATE_GAP:
            after = dict(before)
            allowed = {"status", "current_knowledge", "reason", "why_worthwhile"}
            unexpected = set(operation.changes) - allowed
            if unexpected:
                raise ValueError(f"Unsupported gap fields: {sorted(unexpected)}")
            after.update(operation.changes)
            after["updated_at"] = now
            after = json_record(GapRecord.model_validate(after))
            changes.append(("gaps", before, after))
        elif operation.kind == PatchOperationKind.UPDATE_CONFLICT:
            after = dict(before)
            allowed = {"status", "context_analysis", "description"}
            unexpected = set(operation.changes) - allowed
            if unexpected:
                raise ValueError(f"Unsupported conflict fields: {sorted(unexpected)}")
            after.update(operation.changes)
            after["updated_at"] = now
            after = json_record(ConflictRecord.model_validate(after))
            changes.append(("conflicts", before, after))
        else:
            raise ValueError(f"Unsupported patch operation: {operation.kind}")

        diff = []
        for changed_table, changed_before, changed_after in changes:
            undo.append({"table": changed_table, "record": changed_before})
            changed_id = changed_after[TABLE_IDS[changed_table]]
            event = self.store.append_event(
                conn,
                event_type=operation.kind.value,
                aggregate_type=changed_table.rstrip("s"),
                aggregate_id=changed_id,
                actor_id=actor_id,
                payload={"before": changed_before, "after": changed_after},
            )
            self.store.update_record(conn, changed_table, changed_after, event.sequence)
            self._reindex(conn, changed_table, changed_after)
            self._enqueue_projection_transition(
                conn, changed_table, changed_before, changed_after, event.sequence
            )
            diff.append(
                {
                    "kind": operation.kind.value,
                    "target_id": changed_id,
                    "before": changed_before,
                    "after": changed_after,
                }
            )
        return diff

    @staticmethod
    def _operation_table(kind: PatchOperationKind) -> str:
        if kind in {
            PatchOperationKind.ACCEPT_CLAIM,
            PatchOperationKind.UPDATE_CLAIM,
            PatchOperationKind.SUPERSEDE_CLAIM,
        }:
            return "claims"
        if kind in {PatchOperationKind.ACCEPT_ENTITY, PatchOperationKind.UPDATE_ENTITY}:
            return "entities"
        if kind in {PatchOperationKind.ACCEPT_RELATION, PatchOperationKind.UPDATE_RELATION}:
            return "relations"
        if kind in {
            PatchOperationKind.ACCEPT_SCHEMA_MODULE,
            PatchOperationKind.UPDATE_SCHEMA_MODULE,
        }:
            return "schema_modules"
        if kind == PatchOperationKind.UPDATE_FRESHNESS:
            return "freshness_policies"
        if kind == PatchOperationKind.UPDATE_GAP:
            return "gaps"
        if kind == PatchOperationKind.UPDATE_CONFLICT:
            return "conflicts"
        raise ValueError(f"Unsupported patch operation: {kind}")

    @staticmethod
    def _table_for_id(object_id: str) -> str:
        prefix_to_table = {
            "claim_": "claims",
            "entity_": "entities",
            "relation_": "relations",
            "schema_": "schema_modules",
            "freshness_": "freshness_policies",
            "gap_": "gaps",
            "conflict_": "conflicts",
        }
        table = next(
            (value for prefix, value in prefix_to_table.items() if object_id.startswith(prefix)),
            None,
        )
        if table is None:
            raise ValueError(f"Unsupported patch target: {object_id}")
        return table

    def _reindex(self, conn, table: str, record: dict[str, Any]) -> None:
        if table == "claims":
            body = " ".join(
                str(record.get(field) or "")
                for field in ("statement", "subject", "predicate", "object")
            ) + " " + json.dumps(record.get("qualifiers", {}), ensure_ascii=False)
            self.store.index_text(conn, "claim", record["claim_id"], body)
        elif table == "gaps":
            body = " ".join(
                str(record.get(field) or "")
                for field in ("reason", "why_worthwhile", "current_knowledge")
            )
            self.store.index_text(conn, "gap", record["gap_id"], body)
        elif table == "conflicts":
            body = f"{record['description']} {record.get('context_analysis') or ''}"
            self.store.index_text(conn, "conflict", record["conflict_id"], body)
        elif table == "entities":
            aliases = " ".join(
                alias for values in record.get("aliases", {}).values() for alias in values
            )
            body = f"{record['canonical_name']} {record['entity_type']} {aliases}"
            self.store.index_text(conn, "entity", record["entity_id"], body)
        elif table == "relations":
            body = (
                f"{record['subject_entity_id']} {record['predicate']} "
                f"{record.get('object_entity_id') or record.get('literal_value')} "
                f"{json.dumps(record.get('qualifiers', {}), ensure_ascii=False)}"
            )
            self.store.index_text(conn, "relation", record["relation_id"], body)
        elif table == "schema_modules":
            body = (
                f"{record['name']} {record['description']} "
                f"{json.dumps(record.get('entity_types', {}), ensure_ascii=False)} "
                f"{json.dumps(record.get('predicates', {}), ensure_ascii=False)}"
            )
            self.store.index_text(conn, "schema_module", record["schema_module_id"], body)

    def _require(
        self, table: str, record_id: str, conn=None
    ) -> dict[str, Any]:
        record = self.store.get_record(table, record_id, conn)
        if record is None:
            raise KeyError(f"{table}:{record_id}")
        return record
