from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .knowledge_models import KnowledgeEvent

GENESIS_HASH = "0" * 64
TABLE_IDS = {
    "sources": "source_id",
    "evidence": "evidence_id",
    "claims": "claim_id",
    "claim_evidence": "link_id",
    "questions": "question_id",
    "gaps": "gap_id",
    "conflicts": "conflict_id",
    "patches": "patch_id",
    "research_runs": "research_run_id",
    "documents": "document_id",
    "chunks": "chunk_id",
    "entities": "entity_id",
    "relations": "relation_id",
    "chunk_knowledge": "chunk_knowledge_link_id",
    "schema_modules": "schema_module_id",
    "freshness_policies": "freshness_policy_id",
    "reasoning_traces": "reasoning_trace_id",
    "question_orbits": "orbit_id",
    "orbit_frontier": "frontier_item_id",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class KnowledgeStore:
    """Separate, hash-audited SQLite store for durable knowledge projections."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._fts5 = False
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_events_aggregate
                    ON knowledge_events(aggregate_type, aggregate_id, sequence);
                CREATE TRIGGER IF NOT EXISTS knowledge_events_no_update
                BEFORE UPDATE ON knowledge_events BEGIN
                    SELECT RAISE(ABORT, 'knowledge events are immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS knowledge_events_no_delete
                BEFORE DELETE ON knowledge_events BEGIN
                    SELECT RAISE(ABORT, 'knowledge events are immutable');
                END;

                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    locator TEXT NOT NULL,
                    content_digest TEXT,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sources_locator ON sources(locator);

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);

                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);

                CREATE TABLE IF NOT EXISTS claim_evidence (
                    link_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
                    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
                    stance TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(claim_id, evidence_id, stance)
                );
                CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);

                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gaps (
                    gap_id TEXT PRIMARY KEY,
                    gap_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status, gap_type);

                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);

                CREATE TABLE IF NOT EXISTS patches (
                    patch_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);

                CREATE TABLE IF NOT EXISTS research_runs (
                    research_run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_runs_status ON research_runs(status);

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    version INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(source_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id, version);

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    ordinal INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(document_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, ordinal);

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_entities_type_status
                    ON entities(entity_type, status);

                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
                    object_entity_id TEXT REFERENCES entities(entity_id),
                    predicate TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_relations_subject
                    ON relations(subject_entity_id, predicate, status);
                CREATE INDEX IF NOT EXISTS idx_relations_object
                    ON relations(object_entity_id, predicate, status);

                CREATE TABLE IF NOT EXISTS chunk_knowledge (
                    chunk_knowledge_link_id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(chunk_id, target_kind, target_id, link_type)
                );
                CREATE INDEX IF NOT EXISTS idx_chunk_knowledge_target
                    ON chunk_knowledge(target_kind, target_id);

                CREATE TABLE IF NOT EXISTS schema_modules (
                    schema_module_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE INDEX IF NOT EXISTS idx_schema_modules_status
                    ON schema_modules(status, name);

                CREATE TABLE IF NOT EXISTS freshness_policies (
                    freshness_policy_id TEXT PRIMARY KEY,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    UNIQUE(target_kind, target_id)
                );
                CREATE INDEX IF NOT EXISTS idx_freshness_status
                    ON freshness_policies(status);

                CREATE TABLE IF NOT EXISTS reasoning_traces (
                    reasoning_trace_id TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS question_orbits (
                    orbit_id TEXT PRIMARY KEY,
                    normalized_root_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_question_orbits_root_status
                    ON question_orbits(normalized_root_key, status, updated_sequence);

                CREATE TABLE IF NOT EXISTS orbit_frontier (
                    frontier_item_id TEXT PRIMARY KEY,
                    orbit_id TEXT NOT NULL REFERENCES question_orbits(orbit_id),
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_orbit_frontier_order
                    ON orbit_frontier(orbit_id, status, priority, updated_sequence);

                CREATE TABLE IF NOT EXISTS projection_outbox (
                    projection_job_id TEXT PRIMARY KEY,
                    event_sequence INTEGER NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    last_error TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(event_sequence, aggregate_type, aggregate_id, operation)
                );
                CREATE INDEX IF NOT EXISTS idx_projection_outbox_status
                    ON projection_outbox(status, event_sequence);
                """
            )
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts "
                    "USING fts5(kind UNINDEXED, object_id UNINDEXED, body, tokenize='unicode61')"
                )
                self._fts5 = True
            except sqlite3.OperationalError:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS knowledge_fts ("
                    "kind TEXT NOT NULL, object_id TEXT NOT NULL, body TEXT NOT NULL, "
                    "PRIMARY KEY(kind, object_id))"
                )
                self._fts5 = False

    def append_event(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> KnowledgeEvent:
        occurred_at = datetime.now(UTC)
        event_id = f"kevt_{uuid4().hex}"
        row = conn.execute(
            "SELECT event_hash FROM knowledge_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = row["event_hash"] if row else GENESIS_HASH
        material = {
            "event_id": event_id,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor_id": actor_id,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload,
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()
        cursor = conn.execute(
            """
            INSERT INTO knowledge_events(
                event_id, event_type, aggregate_type, aggregate_id, actor_id,
                occurred_at, payload_json, previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                aggregate_type,
                aggregate_id,
                actor_id,
                occurred_at.isoformat(),
                canonical_json(payload),
                previous_hash,
                event_hash,
            ),
        )
        return KnowledgeEvent(
            sequence=int(cursor.lastrowid),
            event_id=event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor_id=actor_id,
            occurred_at=occurred_at,
            payload=payload,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

    def insert_record(
        self,
        conn: sqlite3.Connection,
        table: str,
        record: dict[str, Any],
        sequence: int,
    ) -> None:
        if table not in TABLE_IDS:
            raise ValueError(f"unsupported knowledge table: {table}")
        columns: dict[str, Any] = {TABLE_IDS[table]: record[TABLE_IDS[table]]}
        if table == "sources":
            columns |= {"locator": record["locator"], "content_digest": record["content_digest"]}
        elif table == "evidence":
            columns["source_id"] = record["source_id"]
        elif table == "documents":
            columns |= {
                "source_id": record["source_id"],
                "version": record["version"],
                "content_digest": record["content_digest"],
            }
        elif table == "chunks":
            columns |= {
                "document_id": record["document_id"],
                "ordinal": record["ordinal"],
                "content_digest": record["content_digest"],
            }
        elif table in {"claims", "entities"}:
            columns |= {"status": record["status"], "revision": record["revision"]}
            if table == "entities":
                columns["entity_type"] = record["entity_type"]
        elif table == "relations":
            columns |= {
                "subject_entity_id": record["subject_entity_id"],
                "object_entity_id": record["object_entity_id"],
                "predicate": record["predicate"],
                "status": record["status"],
                "revision": record["revision"],
            }
        elif table == "claim_evidence":
            columns |= {
                "claim_id": record["claim_id"],
                "evidence_id": record["evidence_id"],
                "stance": record["stance"],
            }
        elif table == "chunk_knowledge":
            columns |= {
                "chunk_id": record["chunk_id"],
                "target_kind": record["target_kind"],
                "target_id": record["target_id"],
                "link_type": record["link_type"],
            }
        elif table == "schema_modules":
            columns |= {
                "status": record["status"],
                "revision": record["revision"],
                "name": record["name"],
                "version": record["version"],
            }
        elif table == "freshness_policies":
            columns |= {
                "target_kind": record["target_kind"],
                "target_id": record["target_id"],
                "status": record["status"],
            }
        elif table == "question_orbits":
            columns |= {
                "normalized_root_key": record["normalized_root_key"],
                "status": record["status"],
            }
        elif table == "orbit_frontier":
            columns |= {
                "orbit_id": record["orbit_id"],
                "priority": record["priority"],
                "status": record["status"],
            }
        elif table in {"questions", "conflicts", "patches", "research_runs"}:
            columns["status"] = record["status"]
        elif table == "gaps":
            columns |= {"gap_type": record["gap_type"], "status": record["status"]}
        columns |= {"record_json": canonical_json(record), "updated_sequence": sequence}
        names = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})", tuple(columns.values())
        )

    def update_record(
        self,
        conn: sqlite3.Connection,
        table: str,
        record: dict[str, Any],
        sequence: int,
    ) -> None:
        if table not in TABLE_IDS:
            raise ValueError(f"unsupported knowledge table: {table}")
        record_id = record[TABLE_IDS[table]]
        assignments: dict[str, Any] = {
            "record_json": canonical_json(record),
            "updated_sequence": sequence,
        }
        if table in {"claims", "entities", "relations", "schema_modules"}:
            assignments |= {"status": record["status"], "revision": record["revision"]}
        elif table in {
            "questions", "gaps", "conflicts", "patches", "research_runs",
            "freshness_policies", "question_orbits", "orbit_frontier",
        }:
            assignments["status"] = record["status"]
        clause = ", ".join(f"{name} = ?" for name in assignments)
        cursor = conn.execute(
            f"UPDATE {table} SET {clause} WHERE {TABLE_IDS[table]} = ?",
            (*assignments.values(), record_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(record_id)

    def get_record(
        self, table: str, record_id: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        if table not in TABLE_IDS:
            raise ValueError(f"unsupported knowledge table: {table}")
        if conn is not None:
            row = conn.execute(
                f"SELECT record_json FROM {table} WHERE {TABLE_IDS[table]} = ?", (record_id,)
            ).fetchone()
            return json.loads(row["record_json"]) if row else None
        with self.connect() as opened:
            return self.get_record(table, record_id, opened)

    def list_records(
        self,
        table: str,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if table not in TABLE_IDS:
            raise ValueError(f"unsupported knowledge table: {table}")
        limit = max(1, min(limit, 500))
        where = " WHERE status = ?" if status and table in {
            "claims", "questions", "gaps", "conflicts", "patches", "research_runs",
            "entities", "relations", "schema_modules", "freshness_policies",
            "question_orbits", "orbit_frontier"
        } else ""
        params: tuple[Any, ...] = (status, limit) if where else (limit,)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT record_json FROM {table}{where} ORDER BY updated_sequence DESC LIMIT ?",
                params,
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    def index_text(
        self, conn: sqlite3.Connection, kind: str, object_id: str, body: str
    ) -> None:
        conn.execute("DELETE FROM knowledge_fts WHERE kind = ? AND object_id = ?", (kind, object_id))
        conn.execute(
            "INSERT INTO knowledge_fts(kind, object_id, body) VALUES (?, ?, ?)",
            (kind, object_id, body),
        )

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not tokens:
            return []
        with self.connect() as conn:
            if self._fts5:
                expression = " AND ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
                rows = conn.execute(
                    "SELECT kind, object_id, bm25(knowledge_fts) AS score "
                    "FROM knowledge_fts WHERE knowledge_fts MATCH ? ORDER BY score LIMIT ?",
                    (expression, limit),
                ).fetchall()
                if not rows and len(tokens) > 1:
                    expression = " OR ".join(
                        f'"{token.replace(chr(34), "")}"' for token in tokens
                    )
                    rows = conn.execute(
                        "SELECT kind, object_id, bm25(knowledge_fts) AS score "
                        "FROM knowledge_fts WHERE knowledge_fts MATCH ? ORDER BY score LIMIT ?",
                        (expression, limit),
                    ).fetchall()
            else:
                pattern = f"%{query}%"
                rows = conn.execute(
                    "SELECT kind, object_id, 0.0 AS score FROM knowledge_fts "
                    "WHERE body LIKE ? LIMIT ?",
                    (pattern, limit),
                ).fetchall()
        results = []
        kind_to_table = {
            "source": "sources",
            "evidence": "evidence",
            "claim": "claims",
            "question": "questions",
            "gap": "gaps",
            "conflict": "conflicts",
            "research_run": "research_runs",
            "document": "documents",
            "chunk": "chunks",
            "entity": "entities",
            "relation": "relations",
            "schema_module": "schema_modules",
        }
        for row in rows:
            table = kind_to_table.get(row["kind"])
            record = self.get_record(table, row["object_id"]) if table else None
            if record:
                results.append({"kind": row["kind"], "score": row["score"], "record": record})
        return results

    def enqueue_projection(
        self,
        conn: sqlite3.Connection,
        *,
        event_sequence: int,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        operation: str = "UPSERT",
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        job = {
            "projection_job_id": f"projection_{uuid4().hex}",
            "event_sequence": event_sequence,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "operation": operation,
            "status": "PENDING",
            "attempts": 0,
            "last_error": None,
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """
            INSERT INTO projection_outbox(
                projection_job_id, event_sequence, aggregate_type, aggregate_id,
                operation, status, attempts, last_error, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["projection_job_id"], event_sequence, aggregate_type, aggregate_id,
                operation, job["status"], 0, None, canonical_json(payload), now, now,
            ),
        )
        return job

    def pending_projection_jobs(
        self, limit: int = 100, *, running_lease_seconds: float = 900
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        running_before = (
            datetime.now(UTC) - timedelta(seconds=max(1, running_lease_seconds))
        ).isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projection_outbox "
                "WHERE status IN ('PENDING', 'FAILED') "
                "OR (status = 'RUNNING' AND updated_at <= ?) "
                "ORDER BY event_sequence LIMIT ?",
                (running_before, limit),
            ).fetchall()
        return [self._row_to_projection_job(row) for row in rows]

    def mark_projection_job(
        self, projection_job_id: str, *, status: str, error: str | None = None
    ) -> None:
        if status not in {"RUNNING", "APPLIED", "FAILED"}:
            raise ValueError(f"unsupported projection status: {status}")
        now = datetime.now(UTC).isoformat()
        attempt_increment = 1 if status == "RUNNING" else 0
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE projection_outbox
                SET status = ?, attempts = attempts + ?, last_error = ?, updated_at = ?
                WHERE projection_job_id = ?
                """,
                (status, attempt_increment, error, now, projection_job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(projection_job_id)

    def projection_health(self) -> dict[str, Any]:
        with self.connect() as conn:
            counts = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM projection_outbox GROUP BY status"
                ).fetchall()
            }
            applied = conn.execute(
                "SELECT COALESCE(MAX(event_sequence), 0) AS watermark "
                "FROM projection_outbox WHERE status = 'APPLIED'"
            ).fetchone()["watermark"]
            latest = conn.execute(
                "SELECT COALESCE(MAX(event_sequence), 0) AS sequence FROM projection_outbox"
            ).fetchone()["sequence"]
            pending = conn.execute(
                "SELECT COUNT(*) AS count FROM projection_outbox "
                "WHERE status IN ('PENDING', 'RUNNING', 'FAILED')"
            ).fetchone()["count"]
        return {
            "watermark": int(applied),
            "latest_sequence": int(latest),
            "lag": int(pending),
            "counts": counts,
        }

    def iter_events(
        self, *, aggregate_id: str | None = None, limit: int = 200
    ) -> list[KnowledgeEvent]:
        limit = max(1, min(limit, 1000))
        query = "SELECT * FROM knowledge_events"
        params: tuple[Any, ...]
        if aggregate_id:
            query += " WHERE aggregate_id = ?"
            params = (aggregate_id, limit)
        else:
            params = (limit,)
        query += " ORDER BY sequence DESC LIMIT ?"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in reversed(rows)]

    def verify_chain(self) -> tuple[bool, int | None, str | None]:
        previous_hash = GENESIS_HASH
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM knowledge_events ORDER BY sequence").fetchall()
        for row in rows:
            event = self._row_to_event(row)
            material = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "actor_id": event.actor_id,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": event.payload,
                "previous_hash": previous_hash,
            }
            expected = hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()
            if event.previous_hash != previous_hash or event.event_hash != expected:
                return False, event.sequence, event.event_id
            previous_hash = event.event_hash
        return True, None, None

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> KnowledgeEvent:
        return KnowledgeEvent(
            sequence=row["sequence"],
            event_id=row["event_id"],
            event_type=row["event_type"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            actor_id=row["actor_id"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            payload=json.loads(row["payload_json"]),
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
        )

    @staticmethod
    def _row_to_projection_job(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "projection_job_id": row["projection_job_id"],
            "event_sequence": row["event_sequence"],
            "aggregate_type": row["aggregate_type"],
            "aggregate_id": row["aggregate_id"],
            "operation": row["operation"],
            "status": row["status"],
            "attempts": row["attempts"],
            "last_error": row["last_error"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
