from __future__ import annotations

import json
from typing import Any

from .kag_adapter import KagBackend, KagUnavailableError
from .knowledge_models import (
    ChunkKnowledgeLink,
    ClaimEvidenceLink,
    ClaimRecord,
    EntityRecord,
    EvidenceRecord,
    EvidenceStance,
    RelationRecord,
)
from .knowledge_service import KnowledgeService


class KnowledgeConstructor:
    """Convert KAG extraction output into governed canonical candidates."""

    def __init__(self, service: KnowledgeService, backend: KagBackend) -> None:
        self.service = service
        self.backend = backend

    def extract_document(
        self,
        document_id: str,
        *,
        actor_id: str = "wisdom-oldman",
        max_chunks: int = 20,
        offset: int = 0,
        recover: bool = True,
    ) -> dict[str, Any]:
        details = self.service.get(document_id)
        if details["kind"] != "document":
            raise ValueError(f"Expected a document id, got {document_id}.")
        all_chunks = details["chunks"]
        batch_size = max(1, min(max_chunks, 100))
        offset = max(0, offset)
        chunks = all_chunks[offset : offset + batch_size]
        request_chunks = [
            {
                "chunk_id": chunk["chunk_id"],
                "name": f"{details['source']['title']} #{chunk['ordinal']}",
                "text": chunk["text"],
            }
            for chunk in chunks
        ]
        degraded = False
        try:
            health = self.backend.health()
            if health.get("ready") is not True:
                raise KagUnavailableError(str(health))
            extracted = self.backend.extract(request_chunks)
        except KagUnavailableError:
            if not recover:
                raise
            try:
                self.backend.recover()
                extracted = self.backend.extract(request_chunks)
            except KagUnavailableError:
                degraded = True
                extracted = {
                    "extractor": "DEGRADED_CHUNK_EVIDENCE",
                    "chunks": [
                        {"chunk_id": item["chunk_id"], "entities": [], "relations": []}
                        for item in request_chunks
                    ],
                }
        extracted_chunks = extracted.get("chunks")
        if not isinstance(extracted_chunks, list):
            # Validate external payload values without changing the caller's exception contract.
            raise ValueError("KAG extraction response is missing its chunk results.")  # noqa: TRY004
        by_chunk = {chunk["chunk_id"]: chunk for chunk in chunks}
        self._validate_extraction(extracted_chunks, set(by_chunk))

        created = {"evidence": [], "entities": [], "claims": [], "relations": [], "links": []}
        reused = {"evidence": [], "entities": [], "claims": [], "relations": [], "links": []}
        source = details["source"]
        for result in extracted_chunks:
            chunk = by_chunk[result["chunk_id"]]
            if not degraded and not result["entities"] and not result["relations"]:
                continue
            evidence, was_created = self._evidence_for_chunk(
                source["source_id"],
                chunk,
                actor_id,
                extraction_method=str(extracted.get("extractor") or "unknown"),
            )
            (created if was_created else reused)["evidence"].append(evidence["evidence_id"])
            self._ensure_chunk_link(
                chunk["chunk_id"], "evidence", evidence["evidence_id"], "EXTRACTED_FROM",
                actor_id, created, reused,
            )
            if degraded:
                continue
            ref_entities: dict[str, dict[str, Any]] = {}
            for raw_entity in result["entities"]:
                entity, entity_created = self._entity_for_raw(raw_entity, actor_id)
                ref_entities[str(raw_entity["source_ref"])] = entity
                bucket = created if entity_created else reused
                bucket["entities"].append(entity["entity_id"])
                self._ensure_chunk_link(
                    chunk["chunk_id"], "entity", entity["entity_id"], "MENTIONS",
                    actor_id, created, reused,
                )
            for raw_relation in result["relations"]:
                subject = ref_entities.get(str(raw_relation["source_ref"]))
                if subject is None:
                    subject, subject_created = self._entity_for_raw(
                        {
                            "source_ref": raw_relation["source_ref"],
                            "name": str(raw_relation["source_ref"]),
                            "entity_type": "Others",
                            "properties": {},
                        },
                        actor_id,
                    )
                    (created if subject_created else reused)["entities"].append(
                        subject["entity_id"]
                    )
                target = ref_entities.get(str(raw_relation["target_ref"]))
                if target is None:
                    target, target_created = self._entity_for_raw(
                        {
                            "source_ref": raw_relation["target_ref"],
                            "name": str(raw_relation["target_ref"]),
                            "entity_type": "Others",
                            "properties": {},
                        },
                        actor_id,
                    )
                    (created if target_created else reused)["entities"].append(target["entity_id"])
                qualifiers = {
                    "source_chunk_id": chunk["chunk_id"],
                    "extraction_method": extracted.get(
                        "extractor", "OpenSPG/KAG schema-constrained extraction"
                    ),
                    "relation_properties": raw_relation.get("properties", {}),
                }
                statement = (
                    f"{subject['canonical_name']} {raw_relation['predicate']} "
                    f"{target['canonical_name']}."
                )
                claim, claim_created = self._claim_for_statement(statement, qualifiers, actor_id)
                (created if claim_created else reused)["claims"].append(claim["claim_id"])
                self._ensure_claim_evidence(claim, evidence, actor_id, created, reused)
                relation, relation_created = self._relation_for_raw(
                    subject, target, raw_relation, claim, qualifiers, actor_id
                )
                (created if relation_created else reused)["relations"].append(
                    relation["relation_id"]
                )
                self._ensure_chunk_link(
                    chunk["chunk_id"], "claim", claim["claim_id"], "EXTRACTED_FROM",
                    actor_id, created, reused,
                )
                self._ensure_chunk_link(
                    chunk["chunk_id"], "relation", relation["relation_id"], "EXTRACTED_FROM",
                    actor_id, created, reused,
                )
        for values in created.values():
            values[:] = list(dict.fromkeys(values))
        for values in reused.values():
            values[:] = list(dict.fromkeys(values))
        return {
            "document_id": document_id,
            "chunks_requested": len(request_chunks),
            "chunks_processed": len(extracted_chunks),
            "offset": offset,
            "next_offset": offset + len(chunks) if offset + len(chunks) < len(all_chunks) else None,
            "document_complete": offset + len(chunks) >= len(all_chunks),
            "total_chunks": len(all_chunks),
            "extractor": extracted.get("extractor"),
            "degraded": degraded,
            "created": created,
            "reused": reused,
            "canonical_status": "CANDIDATE",
            "requires_review": not degraded,
        }

    @staticmethod
    def _validate_extraction(results: list[Any], chunk_ids: set[str]) -> None:
        for result in results:
            if not isinstance(result, dict) or result.get("chunk_id") not in chunk_ids:
                raise ValueError("KAG extraction returned an unknown chunk.")
            if not isinstance(result.get("entities"), list) or not isinstance(
                result.get("relations"), list
            ):
                # A malformed external payload is a validation failure, not a Python API misuse.
                raise ValueError("KAG extraction entities/relations must be lists.")  # noqa: TRY004
            for entity in result["entities"]:
                required = {"source_ref", "name", "entity_type"}
                if not isinstance(entity, dict) or not required.issubset(entity):
                    raise ValueError("KAG extraction returned an invalid entity.")
            for relation in result["relations"]:
                required = {"source_ref", "predicate", "target_ref"}
                if not isinstance(relation, dict) or not required.issubset(relation):
                    raise ValueError("KAG extraction returned an invalid relation.")

    def _evidence_for_chunk(
        self,
        source_id: str,
        chunk: dict[str, Any],
        actor_id: str,
        *,
        extraction_method: str,
    ) -> tuple[dict[str, Any], bool]:
        excerpt = chunk["text"][:16000]
        location = chunk.get("location") or f"chunk {chunk['ordinal']}"
        with self.service.store.connect() as conn:
            rows = conn.execute(
                "SELECT record_json FROM evidence WHERE source_id = ?", (source_id,)
            ).fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            if record["excerpt"] == excerpt and record.get("location") == location:
                return record, False
        return (
            self.service.add_evidence(
                EvidenceRecord(
                    source_id=source_id,
                    excerpt=excerpt,
                    location=location,
                    surrounding_context=chunk["text"][:16000],
                    extraction_method=extraction_method,
                ),
                actor_id=actor_id,
            ),
            True,
        )

    def _entity_for_raw(
        self, raw: dict[str, Any], actor_id: str
    ) -> tuple[dict[str, Any], bool]:
        name = str(raw["name"]).strip()
        entity_type = str(raw.get("entity_type") or "Others").strip()
        if not name:
            raise ValueError("Extracted entity name is empty.")
        with self.service.store.connect() as conn:
            rows = conn.execute(
                "SELECT record_json FROM entities WHERE entity_type = ?", (entity_type,)
            ).fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            if record["canonical_name"].casefold() == name.casefold():
                return record, False
        return (
            self.service.propose_entity(
                EntityRecord(
                    canonical_name=name,
                    entity_type=entity_type,
                    properties=raw.get("properties") or {},
                ),
                actor_id=actor_id,
            ),
            True,
        )

    def _claim_for_statement(
        self, statement: str, qualifiers: dict[str, Any], actor_id: str
    ) -> tuple[dict[str, Any], bool]:
        with self.service.store.connect() as conn:
            rows = conn.execute("SELECT record_json FROM claims").fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            if record["statement"] == statement and record["qualifiers"] == qualifiers:
                return record, False
        return (
            self.service.propose_claim(
                ClaimRecord(statement=statement, qualifiers=qualifiers), actor_id=actor_id
            ),
            True,
        )

    def _relation_for_raw(
        self,
        subject: dict[str, Any],
        target: dict[str, Any],
        raw: dict[str, Any],
        claim: dict[str, Any],
        qualifiers: dict[str, Any],
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        with self.service.store.connect() as conn:
            rows = conn.execute(
                "SELECT record_json FROM relations WHERE subject_entity_id = ? "
                "AND object_entity_id = ? AND predicate = ?",
                (subject["entity_id"], target["entity_id"], str(raw["predicate"])),
            ).fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            if record["qualifiers"] == qualifiers:
                return record, False
        return (
            self.service.propose_relation(
                RelationRecord(
                    subject_entity_id=subject["entity_id"],
                    predicate=str(raw["predicate"]),
                    object_entity_id=target["entity_id"],
                    qualifiers=qualifiers,
                    claim_ids=[claim["claim_id"]],
                ),
                actor_id=actor_id,
            ),
            True,
        )

    def _ensure_claim_evidence(
        self,
        claim: dict[str, Any],
        evidence: dict[str, Any],
        actor_id: str,
        created: dict[str, list[str]],
        reused: dict[str, list[str]],
    ) -> None:
        with self.service.store.connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM claim_evidence WHERE claim_id = ? "
                "AND evidence_id = ? AND stance = 'SUPPORTS'",
                (claim["claim_id"], evidence["evidence_id"]),
            ).fetchone()
        if row:
            reused["links"].append(json.loads(row["record_json"])["link_id"])
            return
        link = self.service.link_evidence(
            ClaimEvidenceLink(
                claim_id=claim["claim_id"],
                evidence_id=evidence["evidence_id"],
                stance=EvidenceStance.SUPPORTS,
                rationale="KAG extracted this candidate relation from the located source chunk.",
            ),
            actor_id=actor_id,
        )
        created["links"].append(link["link_id"])

    def _ensure_chunk_link(
        self,
        chunk_id: str,
        target_kind: str,
        target_id: str,
        link_type: str,
        actor_id: str,
        created: dict[str, list[str]],
        reused: dict[str, list[str]],
    ) -> None:
        with self.service.store.connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM chunk_knowledge WHERE chunk_id = ? "
                "AND target_kind = ? AND target_id = ? AND link_type = ?",
                (chunk_id, target_kind, target_id, link_type),
            ).fetchone()
        if row:
            reused["links"].append(
                json.loads(row["record_json"])["chunk_knowledge_link_id"]
            )
            return
        link = self.service.link_chunk(
            ChunkKnowledgeLink(
                chunk_id=chunk_id,
                target_kind=target_kind,
                target_id=target_id,
                link_type=link_type,
                extraction_method="OpenSPG/KAG v0.8 construction",
            ),
            actor_id=actor_id,
        )
        created["links"].append(link["chunk_knowledge_link_id"])
