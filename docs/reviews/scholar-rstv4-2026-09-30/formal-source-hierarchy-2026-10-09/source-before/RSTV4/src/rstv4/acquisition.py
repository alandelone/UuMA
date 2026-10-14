from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import urllib.parse
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .collection_inputs import normalize_input_doi, prepare_inputs
from .database import initialize_catalog, transaction
from .models import (
    BrowserAcquisitionInput,
    BrowserAcquisitionReceiptInput,
    CollectionBudgetInput,
    CollectionBudgetUpdateInput,
    CollectionCreateInput,
    CollectionScopeInput,
    CollectionSearchInput,
    CollectionTargetInput,
    DeepReadRequestInput,
    JournalMetricsImportInput,
    LegacyPaperMigrationInput,
    LocalPdfImportInput,
    PdfRegistrationInput,
    SourceCandidate,
    new_id,
)
from .sources import PROVIDERS, ProviderResult

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
FIELD_PATTERN = re.compile(r"(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*[{\"]", re.MULTILINE)
FINAL_JOB_STATES = {"SUCCEEDED", "SKIPPED", "FAILED_TERMINAL"}
ACTIVE_JOB_STATES = {"READY", "RETRY_WAIT", "RUNNING", "RESOURCE_WAIT"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    encoded = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}"


def digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_input_doi(value)
    return normalized or None


def normalize_title(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def browser_start_url(value: str | None) -> str | None:
    """Limit browser handoffs to DOI and the explicitly supported publisher article pages."""
    if not value:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or port not in (None, 443) or parsed.query or parsed.fragment):
        return None
    path = parsed.path
    supported = (
        (host == "doi.org" and path.startswith("/10."))
        or (host == "ieeexplore.ieee.org" and bool(re.fullmatch(
            r"/(?:abstract/)?document/\d+/?", path
        )))
        or (host == "www.sciencedirect.com" and bool(re.fullmatch(
            r"/science/article/(?:abs/)?pii/[A-Za-z0-9]+/?", path
        )))
        or (host == "www.mdpi.com" and bool(re.fullmatch(
            r"/\d{4}-\d{4}/\d+/\d+/\d+/?", path
        )))
    )
    return value if supported else None


def _bibtex_entries(text: str) -> list[dict[str, str]]:
    """Small dependency-free BibTeX reader for seed identity fields.

    It deliberately does not attempt to preserve complete BibTeX semantics; raw input remains
    attached to the collection seed and source observations.
    """
    entries: list[dict[str, str]] = []
    cursor = 0
    while True:
        start = text.find("@", cursor)
        if start < 0:
            break
        brace = text.find("{", start)
        if brace < 0:
            break
        depth = 1
        index = brace + 1
        while index < len(text) and depth:
            depth += int(text[index] == "{") - int(text[index] == "}")
            index += 1
        if depth:
            break
        body = text[brace + 1 : index - 1]
        first_comma = body.find(",")
        fields_text = body[first_comma + 1 :] if first_comma >= 0 else body
        fields: dict[str, str] = {}
        matches = list(FIELD_PATTERN.finditer(fields_text))
        for position, match in enumerate(matches):
            value_start = match.end() - 1
            opener = fields_text[value_start]
            closer = "}" if opener == "{" else '"'
            value_index = value_start + 1
            nesting = 1 if opener == "{" else 0
            while value_index < len(fields_text):
                char = fields_text[value_index]
                if opener == "{" and char == "{":
                    nesting += 1
                elif char == closer:
                    if opener == "{" and nesting > 1:
                        nesting -= 1
                    else:
                        break
                value_index += 1
            fields[match.group("key").casefold()] = " ".join(
                fields_text[value_start + 1 : value_index].replace("\n", " ").split()
            )
        if fields.get("title") or fields.get("doi"):
            fields["_raw"] = text[start:index]
            entries.append(fields)
        cursor = index
    return entries


class AcquisitionService:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.db_path = self.root / "data" / "catalog.db"
        self.artifacts_root = self.root / "data" / "artifacts" / "papers"
        self.import_root = self.root / "data" / "paper-import"
        initialize_catalog(self.db_path)

    def import_local_pdf_directories(self, payload: LocalPdfImportInput) -> dict[str, Any]:
        """Stage and ingest local PDFs, preserving uncertain identity for review."""
        from .local_pdf_import import LocalPdfImporter

        return LocalPdfImporter(self).import_directories(payload)

    def local_pdf_import_status(self) -> dict[str, Any]:
        from .local_pdf_import import LocalPdfImporter

        return LocalPdfImporter(self).status()

    def quarantine_local_pdf_parser_outputs(self, root_path: str) -> dict[str, int]:
        from .local_pdf_import import LocalPdfImporter

        return LocalPdfImporter(self).quarantine_parser_outputs(root_path)

    def create_collection(self, payload: CollectionCreateInput) -> dict[str, Any]:
        prepared = prepare_inputs(payload.dois, payload.bibtex, payload.queries, allow_catalog_only=bool(payload.paper_ids))
        omitted = {"idempotency_key"} | ({"paper_ids"} if not payload.paper_ids else set())
        if payload.budget is None:
            omitted.add("budget")
        request_json = json.dumps(payload.model_dump(exclude=omitted),
                                  ensure_ascii=False, sort_keys=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            collection_id = stable_id("collection", payload.idempotency_key)
            prior = conn.execute("SELECT creation_request_json FROM collections WHERE collection_id=?",
                                 (collection_id,)).fetchone()
            if prior is not None:
                if prior["creation_request_json"] != request_json:
                    raise ValueError("Collection request key already belongs to different inputs")
                return self.get_collection(collection_id)
            topic_id = self.collection_topic(conn, payload)
            selected = self.selected_catalog_papers(conn, payload.paper_ids)
            selected_by_doi = {row["doi"]: row for row in selected if row["doi"]}
            timestamp = utc_now()
            conn.execute(
                """INSERT INTO collections
                   (collection_id,field_id,track_id,name,scope_json,scope_version,status,
                    revision,created_at,updated_at,topic_id,creation_request_json)
                   VALUES(?,?,?,?,?,1,'ACTIVE',1,?,?,?,?)""",
                (
                    collection_id,
                    payload.field_id,
                    payload.track_id,
                    payload.name,
                    json.dumps(payload.scope, ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                    topic_id,
                    request_json,
                ),
            )
            from . import collection_runtime

            initial_budget = payload.budget or CollectionBudgetInput()
            if initial_budget.max_papers is not None and len(selected) > initial_budget.max_papers:
                raise ValueError("Selected Catalog papers exceed this Collection paper budget")
            collection_runtime.initialize_policy(conn, collection_id, payload.idempotency_key,
                                                 initial_budget.model_dump(), timestamp)
            for paper in selected:
                self._attach_catalog_paper(conn, collection_id, paper, "CATALOG_PAPER",
                                           paper["paper_id"], paper["paper_id"])
            for entry in prepared["seeds"]:
                matched = selected_by_doi.get(entry["identity"].get("doi"))
                if matched:
                    self._attach_catalog_paper(conn, collection_id, matched, entry["kind"],
                                               entry["raw"], entry["normalized"])
                else:
                    self._add_seed(
                        conn, collection_id, entry["kind"], entry["raw"],
                        entry["normalized"], entry["identity"],
                    )
            for query in prepared["queries"]:
                self._enqueue(
                    conn, collection_id=collection_id, paper_id=None,
                    job_type="SEARCH_LITERATURE", queue_class="NETWORK",
                    payload={"query": query, "providers": list(PROVIDERS), "limit_per_provider": 10},
                    rule_version="literature-search-v1", priority=80,
                )
        return self.get_collection(collection_id)

    @staticmethod
    def collection_topic(conn: sqlite3.Connection, payload: CollectionTargetInput) -> str | None:
        if not conn.execute("SELECT 1 FROM research_fields WHERE field_id=?",
                            (payload.field_id,)).fetchone():
            raise ValueError(f"Unknown field: {payload.field_id}")
        topic_id = payload.topic_id
        if payload.track_id:
            track = conn.execute("SELECT field_id,primary_topic_id FROM research_tracks WHERE track_id=?",
                                 (payload.track_id,)).fetchone()
            if track is None or track["field_id"] != payload.field_id:
                raise ValueError("Collection track must belong to its field")
            if topic_id and track["primary_topic_id"] != topic_id:
                raise ValueError("Collection track must belong to its selected topic")
            topic_id = topic_id or track["primary_topic_id"]
        if topic_id and not conn.execute("SELECT 1 FROM field_topics WHERE field_id=? AND topic_id=?",
                                         (payload.field_id, topic_id)).fetchone():
            raise ValueError("Collection topic must belong to its field")
        return topic_id

    @staticmethod
    def selected_catalog_papers(conn: sqlite3.Connection, paper_ids: list[str]) -> list[dict]:
        result = []
        for paper_id in paper_ids:
            row = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown Catalog paper: {paper_id}")
            result.append(dict(row))
        return result

    def _attach_catalog_paper(self, conn: sqlite3.Connection, collection_id: str,
                              paper: dict, kind: str, raw: str, normalized: str) -> None:
        timestamp = utc_now()
        conn.execute("INSERT OR IGNORE INTO collection_seeds VALUES(?,?,?,?,?,?,?)",
                     (stable_id("seed", collection_id, kind, normalized), collection_id,
                      kind, raw, normalized, paper["paper_id"], timestamp))
        conn.execute("INSERT OR IGNORE INTO collection_memberships VALUES(?,?,'CATALOG_SELECTION',NULL,'DISCOVERED',?)",
                     (collection_id, paper["paper_id"], timestamp))
        context = self._screening_context(conn, collection_id, paper["paper_id"])
        self._enqueue(conn, collection_id=collection_id, paper_id=paper["paper_id"],
                      job_type="SCREEN", queue_class="MODEL_SCREEN",
                      payload={"scope_version": context["collection"]["scope_version"],
                               "screen_context_sha256": digest(context)},
                      rule_version="screen-v1-scope-1", priority=60)

    @staticmethod
    def _screening_context(conn: sqlite3.Connection, collection_id: str, paper_id: str) -> dict:
        owner = conn.execute("SELECT collection_id,field_id,topic_id,track_id,scope_version,scope_json FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
        paper = conn.execute("SELECT paper_id,doi,title,authors_json,published_year,abstract FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
        if owner is None or paper is None:
            raise ValueError("Unknown screening Collection or paper")
        scope = dict(owner);scope["scope"] = json.loads(scope.pop("scope_json"))
        identity = dict(paper);identity["authors"] = json.loads(identity.pop("authors_json"))
        return {"collection": scope, "paper": identity}

    def screening_context(self, collection_id: str, paper_id: str) -> dict:
        with transaction(self.db_path) as conn:
            self._require_membership(conn, collection_id, paper_id)
            return self._screening_context(conn, collection_id, paper_id)

    def release_budget_candidates(self, collection_id: str, limit: int = 250) -> int:
        from . import collection_runtime

        released = 0
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT paper_id,metadata_json FROM collection_candidate_frontier WHERE collection_id=? AND state='DEFERRED_BUDGET' ORDER BY updated_at,paper_id LIMIT ?", (collection_id, min(max(limit, 1), 500))).fetchall()
            for row in rows:
                if not collection_runtime.can_add_paper(conn, collection_id, row[0]):
                    break
                saved = json.loads(row[1])
                kind = saved.get("discovery_kind", "SEARCH")
                conn.execute("INSERT OR IGNORE INTO collection_memberships VALUES(?,?,?,NULL,'DISCOVERED',?)", (collection_id, row[0], kind, utc_now()))
                context = self._screening_context(conn, collection_id, row[0])
                self._enqueue(conn, collection_id=collection_id, paper_id=row[0], job_type="SCREEN", queue_class="MODEL_SCREEN", payload={"scope_version": context["collection"]["scope_version"], "screen_context_sha256": digest(context)}, rule_version="screen-v1-search-current", priority=50)
                if kind == "SEED" and context["paper"]["doi"]:
                    self._enqueue(conn, collection_id=collection_id, paper_id=row[0], job_type="LOCATE_PDF", queue_class="NETWORK", payload={"doi": context["paper"]["doi"]}, rule_version="fulltext-v1", priority=50)
                conn.execute("UPDATE collection_candidate_frontier SET state='MATERIALIZED',updated_at=? WHERE collection_id=? AND paper_id=?", (utc_now(), collection_id, row[0]))
                released += 1
        return released

    def request_collection_search(
        self, collection_id: str, payload: CollectionSearchInput
    ) -> dict[str, Any]:
        """Queue a bounded, idempotent literature search inside a Collection."""
        self.get_collection(collection_id)
        providers = payload.providers or list(PROVIDERS)
        unknown = set(providers) - set(PROVIDERS)
        if unknown:
            raise ValueError(f"Unknown search providers: {sorted(unknown)}")
        with transaction(self.db_path) as conn:
            job_id = self._enqueue(
                conn,
                collection_id=collection_id,
                paper_id=None,
                job_type="SEARCH_LITERATURE",
                queue_class="NETWORK",
                payload={
                    "query": payload.query,
                    "providers": providers,
                    "limit_per_provider": payload.limit_per_provider,
                },
                rule_version="literature-search-v1",
                priority=80,
                idempotency_key=stable_id(
                    "collection_search", collection_id, payload.idempotency_key
                ),
            )
        return self.get_job(job_id)

    def publish_collection_search_results(
        self, collection_id: str, query: str, results: list[ProviderResult]
    ) -> dict[str, Any]:
        """Record every provider observation and screen each unique Catalog paper once."""
        self.get_collection(collection_id)
        paper_ids: set[str] = set()
        new_members = 0
        raw_candidates = 0
        provider_status = []
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            from . import collection_runtime

            for result in results:
                timestamp = utc_now()
                conn.execute(
                    """INSERT INTO retrieval_runs
                       (retrieval_id,query,provider,status,detail,started_at,completed_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        new_id("retrieval"), query, result.provider,
                        "FAILED" if result.error else "COMPLETED", result.error,
                        timestamp, timestamp,
                    ),
                )
                provider_status.append(
                    {"provider": result.provider, "count": len(result.candidates),
                     "error": result.error, "elapsed_s": result.elapsed_s}
                )
                for candidate in result.candidates:
                    raw_candidates += 1
                    doi = normalize_doi(candidate.doi)
                    paper_id = self._upsert_paper_in_conn(
                        conn, title=candidate.title, doi=doi, authors=candidate.authors,
                        year=candidate.published_year, abstract=candidate.abstract,
                        preserve_existing=True,
                    )
                    metadata = candidate.model_dump(mode="json")
                    paper_ids.add(paper_id)
                    observation_digest = digest(metadata)
                    conn.execute(
                        """INSERT OR IGNORE INTO metadata_observations
                           VALUES(?,?,?,?,?,?,?)""",
                        (
                            stable_id("metadata", paper_id, result.provider,
                                      observation_digest),
                            paper_id, result.provider, timestamp, "SUCCESS",
                            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                            observation_digest,
                        ),
                    )
                    self._record_journal_links(
                        conn, paper_id, result.provider, metadata, timestamp
                    )
                    if conn.execute(
                        "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (paper_id,)
                    ).fetchone():
                        continue
                    external_id = candidate.external_id or doi or stable_id(
                        "source", candidate.title, candidate.published_year
                    )
                    conn.execute(
                        """INSERT OR IGNORE INTO paper_sources
                           VALUES(?,?,?,?,?,?)""",
                        (
                            stable_id("paper_source", result.provider, external_id),
                            paper_id, result.provider, external_id, timestamp,
                            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    conn.execute(
                        """UPDATE papers SET landing_url=COALESCE(landing_url,?),
                           pdf_url=COALESCE(pdf_url,?) WHERE paper_id=?""",
                        (candidate.landing_url, candidate.pdf_url, paper_id),
                    )
                    existing = conn.execute(
                        """SELECT 1 FROM collection_memberships
                           WHERE collection_id=? AND paper_id=?""",
                        (collection_id, paper_id),
                    ).fetchone()
                    if existing:
                        continue
                    if not collection_runtime.can_add_paper(conn, collection_id, paper_id):
                        conn.execute("INSERT INTO collection_candidate_frontier VALUES(?,?,'DEFERRED_BUDGET',?,?) ON CONFLICT(collection_id,paper_id) DO UPDATE SET metadata_json=excluded.metadata_json,updated_at=excluded.updated_at", (collection_id, paper_id, json.dumps(metadata, ensure_ascii=False, sort_keys=True), timestamp))
                        continue
                    conn.execute(
                        """INSERT INTO collection_memberships
                           VALUES(?,?,'SEARCH',NULL,'DISCOVERED',?)""",
                        (collection_id, paper_id, timestamp),
                    )
                    new_members += 1
                    self._enqueue(
                        conn, collection_id=collection_id, paper_id=paper_id,
                        job_type="SCREEN", queue_class="MODEL_SCREEN",
                        payload={"scope_version": self._screening_context(conn, collection_id, paper_id)["collection"]["scope_version"], "screen_context_sha256": digest(self._screening_context(conn, collection_id, paper_id))},
                        rule_version="screen-v1-search-current", priority=50,
                    )
        return {
            "query": query, "raw_candidates": raw_candidates,
            "unique_catalog_papers": len(paper_ids), "new_collection_members": new_members,
            "providers": provider_status,
        }

    def _add_seed(
        self,
        conn: sqlite3.Connection,
        collection_id: str,
        seed_type: str,
        raw_value: str,
        normalized_value: str,
        identity: dict[str, Any],
    ) -> None:
        seed_id = stable_id("seed", collection_id, seed_type, normalized_value)
        timestamp = utc_now()
        conn.execute(
            """INSERT OR IGNORE INTO collection_seeds
               VALUES(?,?,?,?,?,NULL,?)""",
            (seed_id, collection_id, seed_type, raw_value, normalized_value, timestamp),
        )
        self._enqueue(
            conn,
            collection_id=collection_id,
            paper_id=None,
            job_type="RESOLVE_SEED",
            queue_class="NETWORK",
            payload={"seed_id": seed_id, "identity": identity},
            rule_version="identity-v1",
            priority=100,
        )

    def get_collection(self, collection_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM collections WHERE collection_id=?", (collection_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown collection: {collection_id}")
            result = dict(row)
            result["scope"] = json.loads(result.pop("scope_json"))
            result["seeds"] = [
                dict(item)
                for item in conn.execute(
                    "SELECT * FROM collection_seeds WHERE collection_id=? ORDER BY created_at",
                    (collection_id,),
                )
            ]
            result["counts"] = {
                "papers": conn.execute(
                    "SELECT COUNT(*) FROM collection_memberships WHERE collection_id=?",
                    (collection_id,),
                ).fetchone()[0],
                "jobs": conn.execute(
                    "SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=?",
                    (collection_id,),
                ).fetchone()[0],
            }
        return result

    def pause_collection(self, collection_id: str, expected_revision: int) -> dict[str, Any]:
        return self._set_collection_status(collection_id, expected_revision, "PAUSED")

    def resume_collection(self, collection_id: str, expected_revision: int) -> dict[str, Any]:
        self._set_collection_status(collection_id, expected_revision, "ACTIVE")
        self.release_budget_candidates(collection_id)
        self.release_deferred_references(collection_id)
        return self.get_collection(collection_id)

    def _set_collection_status(
        self, collection_id: str, expected_revision: int, status: str
    ) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            from . import collection_runtime

            if status == "ACTIVE":
                stopped = collection_runtime.dispatch_stop(conn, collection_id)
                measured = collection_runtime.usage(conn, collection_id)
                limits = collection_runtime.current_limits(conn, collection_id)
                previous = measured["stop_reason"]
                if previous and limits:
                    dimension = previous["dimension"]
                    limit = limits.get("max_" + dimension)
                    observed = measured.get(dimension, previous["observed"])
                    if limit is not None and (observed >= limit if dimension == "papers" else previous["observed"] > limit):
                        stopped = previous
                if stopped:
                    raise ValueError("Collection budget is still exhausted; adjust its limit before resuming")
            cursor = conn.execute(
                """UPDATE collections SET status=?,revision=revision+1,updated_at=?
                   WHERE collection_id=? AND revision=?""",
                (status, utc_now(), collection_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError("Collection revision changed")
            collection_runtime.transition(conn, collection_id, status == "ACTIVE")
        return self.get_collection(collection_id)

    def update_collection_budget(self, collection_id: str, payload: CollectionBudgetUpdateInput) -> dict:
        from . import collection_runtime

        request = {"collection_id": collection_id, **payload.model_dump()}
        request_json = collection_runtime.encoded(request)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT request_json,result_json FROM collection_budget_events WHERE request_id=?",
                                 (payload.request_id,)).fetchone()
            if prior:
                if prior[0] != request_json:
                    raise ValueError("Budget request key already belongs to another change")
                return json.loads(prior[1])
            owner = conn.execute("SELECT revision,status FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
            if owner is None:
                raise ValueError("Unknown collection")
            if owner[0] != payload.expected_revision:
                raise ValueError("Collection revision changed")
            limits = payload.limits.model_dump()
            revision = owner[0] + 1
            result = {"collection_id": collection_id, "revision": revision, "status": owner[1], "limits": limits}
            stamp = utc_now()
            conn.execute("INSERT INTO collection_budget_events VALUES(?,?,?,?,?,?,?)",
                         (collection_runtime.stable_key("budget", payload.request_id), collection_id,
                          payload.request_id, request_json, collection_runtime.encoded(limits),
                          collection_runtime.encoded(result), stamp))
            conn.execute("UPDATE collections SET revision=?,updated_at=? WHERE collection_id=?", (revision, stamp, collection_id))
            runtime = conn.execute("SELECT 1 FROM collection_runtime_state WHERE collection_id=?", (collection_id,)).fetchone()
            if runtime is None:
                collection_runtime.transition(conn, collection_id, owner[1] == "ACTIVE")
        return result

    def collection_progress(self, collection_id: str, *, reference_limit: int = 50,
                            reference_offset: int = 0) -> dict:
        from . import collection_runtime

        with transaction(self.db_path) as conn:
            owner = conn.execute("SELECT * FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
            if owner is None:
                raise ValueError("Unknown collection")
            measured = collection_runtime.usage(conn, collection_id)
            limits = collection_runtime.current_limits(conn, collection_id)
            states = {row[0]: row[1] for row in conn.execute("SELECT status,COUNT(*) FROM acquisition_jobs WHERE collection_id=? GROUP BY status", (collection_id,))}
            refs = [dict(row) for row in conn.execute(
                "SELECT r.*,COALESCE(f.state,r.resolution_status) AS frontier_state FROM reference_entries r "
                "JOIN collection_memberships m ON m.paper_id=r.citing_paper_id "
                "LEFT JOIN collection_reference_frontier f ON f.collection_id=m.collection_id AND f.reference_entry_id=r.reference_entry_id "
                "WHERE m.collection_id=? ORDER BY r.created_at,r.reference_entry_id LIMIT ? OFFSET ?",
                (collection_id, min(max(reference_limit, 1), 200), max(0, reference_offset)))]
            total_refs = conn.execute("SELECT COUNT(*) FROM reference_entries r JOIN collection_memberships m ON m.paper_id=r.citing_paper_id WHERE m.collection_id=?", (collection_id,)).fetchone()[0]
            unresolved_count = conn.execute("SELECT COUNT(*) FROM reference_entries r JOIN collection_memberships m ON m.paper_id=r.citing_paper_id LEFT JOIN collection_reference_frontier f ON f.collection_id=m.collection_id AND f.reference_entry_id=r.reference_entry_id WHERE m.collection_id=? AND COALESCE(f.state,r.resolution_status)!='RESOLVED'", (collection_id,)).fetchone()[0]
            history = [dict(row) for row in conn.execute("SELECT request_id,limits_json,request_json,created_at FROM collection_budget_events WHERE collection_id=? ORDER BY rowid", (collection_id,))]
            workers = collection_runtime.worker_rows(conn)
            held_candidates = conn.execute("SELECT COUNT(*) FROM collection_candidate_frontier WHERE collection_id=? AND state='DEFERRED_BUDGET'", (collection_id,)).fetchone()[0]
        for ref in refs:
            ref["identity_resolution_status"] = ref["resolution_status"]
            ref["resolution_status"] = ref.pop("frontier_state")
            ref["location"] = json.loads(ref.pop("location_json"))
            ref["resolution_note"] = {"UNRESOLVED": "尚未定位规范论文", "DEFERRED_BACKPRESSURE": "等待筛选积压减少",
                                      "DEFERRED_BUDGET": "预算触限，原文与位置保留"}.get(ref["resolution_status"], ref["resolution_status"])
        frontier = sum(count for state, count in states.items() if state not in FINAL_JOB_STATES)
        completion = "PARTIAL_BUDGET" if measured["stop_reason"] else "PAUSED" if owner["status"] == "PAUSED" else (
            "WAITING_REVIEW" if states.get("NEEDS_HUMAN") else "PROCESSING" if frontier else
            "PARTIAL_FAILURE" if states.get("FAILED_TERMINAL") else
            "PARTIAL_UNRESOLVED_REFERENCES" if unresolved_count else "CURRENT_FRONTIER_COMPLETE")
        return {"collection_id": collection_id, "revision": owner["revision"], "status": owner["status"],
                "completion": completion, "frontier_jobs": frontier, "budget": {"limits": limits,
                "configuration": "RECORDED" if limits else "LEGACY_UNRECORDED", "usage": measured, "history": history},
                "references": refs, "reference_total": total_refs, "reference_offset": reference_offset,
                "unresolved_references": unresolved_count, "budget_held_candidates": held_candidates,
                "references_have_more": reference_offset + len(refs) < total_refs,
                "workers": workers, "worker_observation": "INDEPENDENT_HEARTBEATS", "fixed_depth_cutoff": None}

    def update_scope(
        self, collection_id: str, payload: CollectionScopeInput
    ) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE collections SET scope_json=?,scope_version=scope_version+1,
                   revision=revision+1,updated_at=? WHERE collection_id=? AND revision=?""",
                (
                    json.dumps(payload.scope, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                    collection_id,
                    payload.expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Collection revision changed")
            current_scope_version = conn.execute("SELECT scope_version FROM collections WHERE collection_id=?", (collection_id,)).fetchone()[0]
            members = conn.execute(
                "SELECT paper_id FROM collection_memberships WHERE collection_id=?",
                (collection_id,),
            ).fetchall()
            for member in members:
                self._enqueue(
                    conn,
                    collection_id=collection_id,
                    paper_id=member["paper_id"],
                    job_type="SCREEN",
                    queue_class="MODEL_SCREEN",
                    payload={"scope_version": current_scope_version,
                             "screen_context_sha256": digest(self._screening_context(conn, collection_id, member["paper_id"]))},
                    rule_version=f"screen-v1-scope-{current_scope_version}",
                    priority=50,
                )
        return self.get_collection(collection_id)

    def list_papers(
        self, collection_id: str | None = None, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        with transaction(self.db_path) as conn:
            if collection_id:
                rows = conn.execute(
                    """SELECT p.*,m.status AS collection_status,m.discovery_kind
                       FROM collection_memberships m JOIN papers p ON p.paper_id=m.paper_id
                       WHERE m.collection_id=?
                       AND NOT EXISTS(SELECT 1 FROM catalog_quarantine q
                                      WHERE q.paper_id=p.paper_id)
                       ORDER BY p.updated_at DESC LIMIT ? OFFSET ?""",
                    (collection_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM papers p
                       WHERE NOT EXISTS(SELECT 1 FROM catalog_quarantine q
                                        WHERE q.paper_id=p.paper_id)
                       ORDER BY p.updated_at DESC LIMIT ? OFFSET ?""",
                    (limit, offset),
                ).fetchall()
        return [self._decode_paper(row) for row in rows]

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown paper: {paper_id}")
            result = self._decode_paper(row)
            result["catalog_status"] = (
                "QUARANTINED" if conn.execute(
                    "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (paper_id,)
                ).fetchone() else "ACTIVE"
            )
            from .acquisition_model_calls import list_calls
            result["model_calls"] = list_calls(conn, paper_id)
            result["identities"] = self._rows(
                conn, "paper_identities", "paper_id", paper_id
            )
            result["sources"] = self._rows(conn, "paper_sources", "paper_id", paper_id)
            result["files"] = self._rows(
                conn, "source_file_versions", "paper_id", paper_id
            )
            result["assessments"] = self._rows(
                conn, "paper_assessments", "paper_id", paper_id
            )
            result["references"] = [
                dict(item)
                for item in conn.execute(
                    "SELECT * FROM reference_entries WHERE citing_paper_id=? ORDER BY created_at",
                    (paper_id,),
                )
            ]
            result["processing"] = [
                dict(item)
                for item in conn.execute(
                    """SELECT * FROM acquisition_jobs WHERE paper_id=?
                       ORDER BY created_at,job_id""",
                    (paper_id,),
                )
            ]
        return result

    @staticmethod
    def _decode_paper(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["authors"] = json.loads(result.pop("authors_json"))
        return result

    @staticmethod
    def _rows(
        conn: sqlite3.Connection, table: str, key: str, value: str
    ) -> list[dict[str, Any]]:
        allowed = {
            ("paper_identities", "paper_id"),
            ("paper_sources", "paper_id"),
            ("source_file_versions", "paper_id"),
            ("paper_assessments", "paper_id"),
        }
        if (table, key) not in allowed:
            raise ValueError("Unsupported related data query")
        return [
            dict(item)
            for item in conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,))
        ]

    def get_processing_history(
        self, paper_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                """SELECT a.*,j.job_type,j.collection_id FROM acquisition_attempts a
                   JOIN acquisition_jobs j ON j.job_id=a.job_id WHERE j.paper_id=?
                   ORDER BY a.started_at DESC LIMIT ? OFFSET ?""",
                (paper_id, min(max(limit, 1), 500), max(offset, 0)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_frontier(
        self, collection_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                """SELECT * FROM acquisition_jobs WHERE collection_id=?
                   AND status NOT IN ('SUCCEEDED','SKIPPED','FAILED_TERMINAL')
                   ORDER BY priority DESC,available_at,created_at LIMIT ? OFFSET ?""",
                (collection_id, min(max(limit, 1), 500), max(offset, 0)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_failures(
        self, collection_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                """SELECT * FROM acquisition_jobs WHERE collection_id=?
                   AND status IN ('RETRY_WAIT','RESOURCE_WAIT','NEEDS_HUMAN','FAILED_TERMINAL')
                   ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                (collection_id, min(max(limit, 1), 500), max(offset, 0)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_usage(self, collection_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                """SELECT job_type,status,COUNT(*) AS count FROM acquisition_jobs
                   WHERE collection_id=? GROUP BY job_type,status""",
                (collection_id,),
            ).fetchall()
            attempts = conn.execute(
                """SELECT COUNT(*) FROM acquisition_attempts a JOIN acquisition_jobs j
                   ON j.job_id=a.job_id WHERE j.collection_id=?""",
                (collection_id,),
            ).fetchone()[0]
        return {
            "collection_id": collection_id,
            "jobs": [dict(row) for row in rows],
            "attempts": attempts,
        }

    def report_worker_presence(self, worker_id: str, instance_id: str, role: str,
                               hostname: str, process_id: int, state: str,
                               job_id: str | None = None) -> None:
        if role not in {"network", "parser", "model"} or state not in {"IDLE", "RUNNING", "STOPPED"}:
            raise ValueError("Unknown worker presence state")
        observed = datetime.now(UTC)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT instance_id,started_at FROM acquisition_worker_presence WHERE worker_id=?",
                                 (worker_id,)).fetchone()
            started = prior[1] if prior and prior[0] == instance_id else observed.isoformat()
            conn.execute("INSERT INTO acquisition_worker_presence VALUES(?,?,?,?,?,?,?,?,?,?) "
                         "ON CONFLICT(worker_id) DO UPDATE SET instance_id=excluded.instance_id,role=excluded.role,"
                         "hostname=excluded.hostname,process_id=excluded.process_id,state=excluded.state,"
                         "job_id=excluded.job_id,started_at=excluded.started_at,observed_at=excluded.observed_at,expires_at=excluded.expires_at",
                         (worker_id, instance_id, role, hostname, process_id, state, job_id, started,
                          observed.isoformat(), (observed + timedelta(seconds=45)).isoformat()))

    def request_deep_read(self, collection_id: str, payload: DeepReadRequestInput) -> dict[str, Any]:
        request = payload.model_dump(exclude_none=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._require_membership(conn, collection_id, payload.paper_id)
            prior = conn.execute("SELECT * FROM acquisition_jobs WHERE idempotency_key=?", (payload.idempotency_key,)).fetchone()
            if prior is not None:
                stored = json.loads(prior["input_json"])
                same = (prior["collection_id"] == collection_id and prior["paper_id"] == payload.paper_id
                        and prior["job_type"] == "SKELETON" and stored.get("user_requested") is True
                        and (stored.get("request") == request if "request" in stored else
                             stored.get("reason") == payload.reason and payload.parse_run_id is None))
                if not same:
                    raise ValueError("Deep read request key was reused with different inputs")
                job_id = prior["job_id"]
            else:
                parse = conn.execute("SELECT pr.parse_run_id FROM parse_runs pr JOIN source_file_versions sf ON sf.file_version_id=pr.file_version_id WHERE sf.paper_id=? AND pr.status='SUCCEEDED' ORDER BY pr.completed_at DESC,pr.parse_run_id DESC LIMIT 1", (payload.paper_id,)).fetchone()
                parse_run_id = payload.parse_run_id or (parse[0] if parse else None)
                if not parse_run_id:
                    raise ValueError("Deep read requires a completed parse")
                self._require_parse_source(conn, parse_run_id, payload.paper_id)
                job_id = self._enqueue(conn, collection_id=collection_id, paper_id=payload.paper_id,
                    job_type="SKELETON", queue_class="MODEL_SKELETON",
                    payload={"reason":payload.reason,"user_requested":True,"parse_run_id":parse_run_id,"request":request},
                    rule_version="skeleton-v1",priority=200,idempotency_key=payload.idempotency_key)
        return self.get_job(job_id)

    def retry_step(self, job_id: str, expected_fencing_token: int | None = None, *,
                   expected_status: str | None = None,
                   expected_updated_at: str | None = None) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM acquisition_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown job: {job_id}")
            if (
                expected_fencing_token is not None
                and row["fencing_token"] != expected_fencing_token
            ):
                raise ValueError("Job fencing token changed")
            if ((expected_status is not None and row["status"] != expected_status)
                    or (expected_updated_at is not None and row["updated_at"] != expected_updated_at)):
                raise ValueError("Job status changed; refresh before retrying")
            if row["status"] not in {
                "RETRY_WAIT", "RESOURCE_WAIT", "NEEDS_HUMAN", "FAILED_TERMINAL"
            }:
                raise ValueError("Only a stopped or waiting step can be retried")
            cursor = conn.execute(
                """UPDATE acquisition_jobs SET status='READY',available_at=?,lease_owner=NULL,
                   lease_expires_at=NULL,last_error_code=NULL,last_error_detail=NULL,updated_at=?
                    WHERE job_id=? AND fencing_token=? AND status=? AND updated_at=?""",
                (utc_now(), utc_now(), job_id, row["fencing_token"], row["status"], row["updated_at"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Job status changed; refresh before retrying")
        return self.get_job(job_id)

    def register_pdf(
        self,
        collection_id: str,
        payload: PdfRegistrationInput,
        *,
        extra_allowed_root: Path | None = None,
    ) -> dict[str, Any]:
        source = Path(payload.path).expanduser().resolve()
        allowed = [self.import_root.resolve(), (self.root / "文献POOL").resolve()]
        if extra_allowed_root:
            allowed.append(extra_allowed_root.resolve())
        if not any(source == root or root in source.parents for root in allowed):
            raise PermissionError("PDF must be inside a registered import directory")
        if not source.is_file():
            raise FileNotFoundError(source)
        size = source.stat().st_size
        if size > 100 * 1024 * 1024:
            raise ValueError("PDF exceeds the 100 MiB default limit")
        with source.open("rb") as stream:
            raw_head = stream.read(1024)
            stream.seek(max(0, size - 2048))
            raw_tail = stream.read()
        if not raw_head.startswith(b"%PDF-") or b"%%EOF" not in raw_tail:
            raise ValueError("File is not a complete PDF")
        sha256 = self._file_digest(source)
        from . import collection_runtime

        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._require_membership(conn, collection_id, payload.paper_id)
            capacity = collection_runtime.file_capacity(conn, collection_id, sha256, size)
        if not capacity:
            raise collection_runtime.CollectionBudgetExceeded("Registered PDF budget reached; original file retained and Collection paused")
        target_dir = self.artifacts_root / payload.paper_id / sha256
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "source.pdf"
        if not target.exists():
            temporary = target.with_suffix(".partial")
            shutil.copy2(source, temporary)
            if self._file_digest(temporary) != sha256:
                temporary.unlink(missing_ok=True)
                raise ValueError("PDF digest changed while copying")
            os.replace(temporary, target)
        validation = self._validate_pdf_identity(source, payload.paper_id)
        file_version_id = stable_id("source_file", payload.paper_id, sha256)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._require_membership(conn, collection_id, payload.paper_id)
            capacity = collection_runtime.file_capacity(conn, collection_id, sha256, size)
            if capacity:
                self._require_membership(conn, collection_id, payload.paper_id)
                conn.execute(
                    """INSERT OR IGNORE INTO source_file_versions
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        file_version_id,
                        payload.paper_id,
                        sha256,
                        size,
                        "application/pdf",
                        str(target),
                        payload.acquisition_method,
                        payload.source_url,
                        validation["identity_status"],
                        json.dumps(validation, ensure_ascii=False, sort_keys=True),
                        utc_now(),
                    ),
                )
                if validation["identity_status"] == "VERIFIED":
                    self._enqueue(
                        conn,
                        collection_id=collection_id,
                        paper_id=payload.paper_id,
                        job_type="PARSE_PDF",
                        queue_class="PARSER",
                        payload={"file_version_id": file_version_id},
                        rule_version="parser-v1",
                        priority=80,
                    )
        if not capacity:
            raise collection_runtime.CollectionBudgetExceeded("Registered PDF budget changed during processing; original file retained")
        return {"file_version_id": file_version_id, **validation, "storage_path": str(target)}

    def reuse_registered_pdf(
        self, collection_id: str, paper_id: str
    ) -> dict[str, Any] | None:
        """Reuse an intact Catalog PDF before attempting another acquisition."""
        with transaction(self.db_path) as conn:
            self._require_membership(conn, collection_id, paper_id)
            if conn.execute(
                "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (paper_id,)
            ).fetchone():
                return {"status": "CATALOG_QUARANTINED"}
            files = conn.execute(
                """SELECT file_version_id,sha256,size_bytes,storage_path,identity_status
                   FROM source_file_versions WHERE paper_id=?
                   ORDER BY CASE identity_status WHEN 'VERIFIED' THEN 0 ELSE 1 END,
                            created_at DESC""",
                (paper_id,),
            ).fetchall()

        for source in files:
            path = Path(source["storage_path"])
            try:
                if not path.is_file() or path.stat().st_size != source["size_bytes"]:
                    continue
                if self._file_digest(path) != source["sha256"]:
                    continue
            except OSError:
                continue

            result = {
                "status": "REUSED_CATALOG_PDF" if source["identity_status"] == "VERIFIED"
                else "REGISTERED_PDF_NEEDS_REVIEW",
                "file_version_id": source["file_version_id"],
                "identity_status": source["identity_status"],
                "storage_path": str(path),
            }
            if source["identity_status"] != "VERIFIED":
                return result
            with transaction(self.db_path) as conn:
                self._require_membership(conn, collection_id, paper_id)
                current = conn.execute(
                    """SELECT 1 FROM source_file_versions
                       WHERE file_version_id=? AND paper_id=? AND identity_status='VERIFIED'""",
                    (source["file_version_id"], paper_id),
                ).fetchone()
                if current is None:
                    continue
                result["parse_job_id"] = self._enqueue(
                    conn,
                    collection_id=collection_id,
                    paper_id=paper_id,
                    job_type="PARSE_PDF",
                    queue_class="PARSER",
                    payload={"file_version_id": source["file_version_id"]},
                    rule_version="parser-v1",
                    priority=80,
                )
            return result
        return None

    def _validate_pdf_identity(self, path: Path, paper_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
        if paper is None:
            raise ValueError(f"Unknown paper: {paper_id}")
        with path.open("rb") as stream:
            payload = stream.read(2 * 1024 * 1024).decode("latin-1", errors="ignore")
        evidence_source = "raw_pdf_bytes"
        try:
            reader = PdfReader(path, strict=False)
            extracted = [reader.metadata.title or "" if reader.metadata else ""]
            for page in reader.pages[:3]:
                extracted.append(page.extract_text() or "")
            text = "\n".join(extracted)[:100_000]
            if text.strip():
                payload = text + "\n" + payload
                evidence_source = "pdf_text_and_raw_bytes"
        except (PdfReadError, AttributeError, IndexError, KeyError, TypeError, ValueError, OSError):
            # A damaged or unusual PDF must still pass the conservative raw-byte check.
            pass
        doi = normalize_doi(paper["doi"])
        title_tokens = [
            token for token in normalize_title(paper["title"]).split() if len(token) > 3
        ]
        normalized_payload = normalize_title(payload)
        observed_dois = {normalize_doi(match.group()) for match in DOI_PATTERN.finditer(payload)}
        doi_match = bool(doi and doi in observed_dois)
        title_matches = sum(token in normalized_payload for token in title_tokens[:12])
        title_ratio = title_matches / max(1, min(12, len(title_tokens)))
        verified = doi_match or title_ratio >= 0.6
        return {
            "identity_status": "VERIFIED" if verified else "NEEDS_REVIEW",
            "doi_match": doi_match,
            "title_token_ratio": round(title_ratio, 3),
            "technical_pdf_valid": True,
            "evidence_source": evidence_source,
        }

    def request_browser_acquisition(
        self, collection_id: str, payload: BrowserAcquisitionInput
    ) -> dict[str, Any]:
        request_id = stable_id("browser_request", payload.idempotency_key)
        with transaction(self.db_path) as conn:
            self._require_membership(conn, collection_id, payload.paper_id)
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id=?", (payload.paper_id,)
            ).fetchone()
            if payload.start_url and not browser_start_url(payload.start_url):
                raise ValueError("Browser start URL is not a supported article or DOI page")
            doi_url = (
                "https://doi.org/" + urllib.parse.quote(paper["doi"], safe="/")
                if paper["doi"] else None
            )
            start_url = (
                payload.start_url or browser_start_url(paper["landing_url"]) or doi_url
            )
            target = self.import_root / "browser" / request_id
            timestamp = utc_now()
            conn.execute(
                """INSERT OR IGNORE INTO browser_acquisition_requests
                   VALUES(?,?,?,?,NULL,NULL,NULL,'QUEUED',?,?, '[]',NULL,?,?)""",
                (
                    request_id,
                    collection_id,
                    payload.paper_id,
                    payload.idempotency_key,
                    json.dumps(
                        {
                            "doi": paper["doi"], "title": paper["title"],
                            "start_url": start_url,
                        },
                        ensure_ascii=False,
                    ),
                    str(target),
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        return dict(row)

    def list_browser_acquisition_requests(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM browser_acquisition_requests WHERE status=?
                       ORDER BY created_at LIMIT ?""",
                    (status, min(max(limit, 1), 500)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM browser_acquisition_requests
                       ORDER BY created_at LIMIT ?""",
                    (min(max(limit, 1), 500),),
                ).fetchall()
        return [dict(row) for row in rows]

    def claim_browser_acquisition(self) -> dict[str, Any] | None:
        """Lease one queued browser handoff to the authorized local Chrome extension."""
        stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT r.* FROM browser_acquisition_requests r
                   JOIN collections c ON c.collection_id=r.collection_id
                   WHERE c.status='ACTIVE' AND (
                       r.status='QUEUED' OR (r.status='RUNNING' AND r.updated_at<?))
                   ORDER BY r.created_at LIMIT 1""",
                (stale_at,),
            ).fetchone()
            if row is None:
                return None
            execution_id = new_id("browser_execution")
            conn.execute(
                """UPDATE browser_acquisition_requests
                   SET status='RUNNING',execution_id=?,updated_at=? WHERE request_id=?""",
                (execution_id, utc_now(), row["request_id"]),
            )
        return {
            "request_id": row["request_id"],
            "collection_id": row["collection_id"],
            "paper_id": row["paper_id"],
            "execution_id": execution_id,
            "expected_identity": json.loads(row["expected_identity_json"]),
        }

    def resume_browser_acquisition(self, request_id: str, execution_id: str) -> dict[str, Any]:
        """Resume only a browser task that stopped for human interaction."""
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None or row["execution_id"] != execution_id:
                raise ValueError("Unknown or stale browser execution")
            if row["status"] != "WAITING_HUMAN":
                raise ValueError("Only a waiting browser request can be resumed")
            conn.execute(
                """UPDATE browser_acquisition_requests SET status='QUEUED',
                   execution_id=NULL,updated_at=? WHERE request_id=?""",
                (utc_now(), request_id),
            )
        return {"request_id": request_id, "status": "QUEUED"}

    def submit_browser_acquisition_receipt(
        self, payload: BrowserAcquisitionReceiptInput
    ) -> dict[str, Any]:
        registered = []
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown browser request: {payload.request_id}")
            if row["execution_id"] and row["execution_id"] != payload.execution_id:
                raise ValueError("Browser request is already bound to another execution")
            target = Path(row["target_directory"]).resolve()
            outputs = []
            for raw_path in payload.output_paths:
                path = Path(raw_path).resolve()
                if target not in path.parents:
                    raise PermissionError(
                        "Browser output must be inside its assigned target directory"
                    )
                outputs.append(str(path))
        if payload.status in {"COMPLETED", "PARTIAL"} and outputs:
            for path in outputs:
                registered.append(
                    self.register_pdf(
                        row["collection_id"],
                        PdfRegistrationInput(
                            paper_id=row["paper_id"], path=path,
                            acquisition_method={
                                "rstv4-chrome-extension": "chrome-network-worker",
                                "rstv4-chrome-human-upload": "chrome-human-assisted",
                            }.get(payload.action_id, "copycat-browser"),
                            source_url=payload.source_url,
                            idempotency_key=f"browser-{payload.request_id}-{digest(path)}",
                        ),
                    )
                )
            if payload.action_id in {
                "rstv4-chrome-extension", "rstv4-chrome-human-upload"
            }:
                outputs = [item["storage_path"] for item in registered]
        with transaction(self.db_path) as conn:
            current = conn.execute(
                "SELECT execution_id FROM browser_acquisition_requests WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
            if current is None or (
                current["execution_id"] and current["execution_id"] != payload.execution_id
            ):
                raise ValueError("Browser execution changed before receipt was saved")
            conn.execute(
                """UPDATE browser_acquisition_requests SET action_id=?,action_version=?,
                   execution_id=?,status=?,output_refs_json=?,error_json=?,updated_at=?
                   WHERE request_id=?""",
                (
                    payload.action_id,
                    payload.action_version,
                    payload.execution_id,
                    payload.status,
                    json.dumps(outputs, ensure_ascii=False),
                    json.dumps(payload.error, ensure_ascii=False) if payload.error else None,
                    utc_now(),
                    payload.request_id,
                ),
            )
            result = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
        if registered:
            response = dict(result)
            response["registered_files"] = registered
            return response
        return dict(result)

    def migrate_legacy_paperpool(self, payload: LegacyPaperMigrationInput) -> dict[str, Any]:
        source_path = Path(payload.database_path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        backup = source_path.with_suffix(".pre-native-paperpool.bak")
        if not backup.exists():
            shutil.copy2(source_path, backup)
        with sqlite3.connect(source_path) as source:
            source.row_factory = sqlite3.Row
            columns = {
                row["name"] for row in source.execute("PRAGMA table_info(paper)").fetchall()
            }
            required = {"id", "title", "year", "authors", "file", "DOI"}
            missing = required - columns
            if missing:
                raise ValueError(f"Legacy paper table is missing columns: {sorted(missing)}")
            selections = ["id", "title", "year", "authors", "file", "DOI"]
            if "Pp_abstract" in columns:
                selections.append("Pp_abstract")
            query = f"SELECT {','.join(selections)} FROM paper"
            params: list[Any] = []
            if payload.paper_ids:
                query += f" WHERE id IN ({','.join('?' for _ in payload.paper_ids)})"
                params.extend(payload.paper_ids)
            rows = source.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                result = self._migrate_legacy_row(source_path, row, payload.copy_files)
            except Exception as exc:  # noqa: BLE001 - audit each legacy row separately
                result = {"legacy_id": row["id"], "status": "NEEDS_REVIEW", "detail": str(exc)}
            results.append(result)
        return {
            "source": str(source_path),
            "backup": str(backup),
            "rows": len(rows),
            "imported": sum(item["status"] == "IMPORTED" for item in results),
            "results": results,
        }

    def _migrate_legacy_row(
        self, source_path: Path, row: sqlite3.Row, copy_files: bool
    ) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            prior = conn.execute(
                """SELECT paper_id,file_version_id FROM legacy_paper_mappings
                   WHERE source_database=? AND legacy_id=?""",
                (str(source_path), row["id"]),
            ).fetchone()
        if prior is not None:
            return {
                "legacy_id": row["id"],
                "paper_id": prior["paper_id"],
                "file_version_id": prior["file_version_id"],
                "status": "SKIPPED",
            }
        title = str(row["title"] or "").strip()
        if not title:
            raise ValueError("Missing title")
        doi = normalize_doi(row["DOI"])
        authors = self._decode_authors(row["authors"])
        year = int(row["year"]) if str(row["year"] or "").isdigit() else None
        abstract = (  # sqlite3.Row membership checks values, not column names
            row["Pp_abstract"] if "Pp_abstract" in row.keys() else None  # noqa: SIM118
        )
        paper_id = self._upsert_paper(
            title=title, doi=doi, authors=authors, year=year, abstract=abstract
        )
        file_version_id = None
        detail: dict[str, Any] = {"file": "NOT_IMPORTED"}
        raw_path = str(row["file"] or "").strip()
        if copy_files and raw_path:
            path = Path(raw_path).expanduser()
            if path.is_file():
                registered = self._register_unscoped_pdf(
                    paper_id, path, acquisition_method="legacy-paperpool"
                )
                file_version_id = registered["file_version_id"]
                detail = {"file": registered["identity_status"]}
            else:
                detail = {"file": "MISSING", "legacy_path": raw_path}
        with transaction(self.db_path) as conn:
            observation = {
                "title": title,
                "doi": doi,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "legacy_id": row["id"],
            }
            conn.execute(
                """INSERT OR IGNORE INTO metadata_observations
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    stable_id("metadata", "LEGACY_PAPERPOOL", source_path, row["id"]),
                    paper_id,
                    "LEGACY_PAPERPOOL",
                    utc_now(),
                    "SUCCESS",
                    json.dumps(observation, ensure_ascii=False, sort_keys=True),
                    digest(observation),
                ),
            )
            conn.execute(
                """INSERT OR REPLACE INTO legacy_paper_mappings
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    str(source_path),
                    row["id"],
                    paper_id,
                    file_version_id,
                    "IMPORTED",
                    json.dumps(detail, ensure_ascii=False),
                    utc_now(),
                ),
            )
        return {"legacy_id": row["id"], "paper_id": paper_id, "status": "IMPORTED", **detail}

    def _register_unscoped_pdf(
        self, paper_id: str, source: Path, *, acquisition_method: str
    ) -> dict[str, Any]:
        """Register an immutable legacy file without inventing a Field or processing scope."""
        source = source.resolve()
        size = source.stat().st_size
        if size > 100 * 1024 * 1024:
            raise ValueError("PDF exceeds the 100 MiB default limit")
        with source.open("rb") as stream:
            head = stream.read(1024)
            stream.seek(max(0, size - 2048))
            tail = stream.read()
        if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise ValueError("Legacy file is not a complete PDF")
        sha256 = self._file_digest(source)
        target_dir = self.artifacts_root / paper_id / sha256
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "source.pdf"
        if not target.exists():
            temporary = target.with_suffix(".partial")
            shutil.copy2(source, temporary)
            if self._file_digest(temporary) != sha256:
                temporary.unlink(missing_ok=True)
                raise ValueError("PDF digest changed while copying")
            os.replace(temporary, target)
        validation = self._validate_pdf_identity(source, paper_id)
        file_version_id = stable_id("source_file", paper_id, sha256)
        with transaction(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    file_version_id,
                    paper_id,
                    sha256,
                    size,
                    "application/pdf",
                    str(target),
                    acquisition_method,
                    None,
                    validation["identity_status"],
                    json.dumps(validation, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
        return {"file_version_id": file_version_id, **validation, "storage_path": str(target)}

    def _migration_collection(self, paper_id: str) -> str:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT field_id FROM research_fields ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                raise ValueError("Create a research field before importing legacy files")
            collection_id = stable_id("collection", "legacy-paperpool-migration")
            timestamp = utc_now()
            conn.execute(
                """INSERT OR IGNORE INTO collections
                   (collection_id,field_id,track_id,name,scope_json,scope_version,status,
                    revision,created_at,updated_at)
                   VALUES(?,?,NULL,'Legacy PaperPool migration','{}',1,'PAUSED',1,?,?)""",
                (collection_id, row["field_id"], timestamp, timestamp),
            )
            conn.execute(
                """INSERT OR IGNORE INTO collection_memberships
                   VALUES(?,?, 'LEGACY_IMPORT',NULL,'IMPORTED',?)""",
                (collection_id, paper_id, timestamp),
            )
        return collection_id

    def _upsert_paper(
        self,
        *,
        title: str,
        doi: str | None,
        authors: list[str],
        year: int | None,
        abstract: str | None = None,
        preserve_existing: bool = False,
    ) -> str:
        with transaction(self.db_path) as conn:
            return self._upsert_paper_in_conn(
                conn, title=title, doi=doi, authors=authors,
                year=year, abstract=abstract,
                preserve_existing=preserve_existing,
            )

    def _upsert_paper_in_conn(
        self,
        conn: sqlite3.Connection,
        *,
        title: str,
        doi: str | None,
        authors: list[str],
        year: int | None,
        abstract: str | None = None,
        preserve_existing: bool = False,
    ) -> str:
        normalized_title = normalize_title(title)
        canonical_key = (
            f"doi:{doi}"
            if doi
            else f"work:{digest([normalized_title, authors[:1], year])}"
        )
        row = conn.execute(
            """SELECT paper_id,authors_json,published_year FROM papers
               WHERE canonical_key=? OR (doi IS NOT NULL AND doi=?)""",
            (canonical_key, doi),
        ).fetchone()
        timestamp = utc_now()
        if row:
            paper_id = row["paper_id"]
            if not preserve_existing:
                conn.execute(
                    """UPDATE papers SET title=?,normalized_title=?,authors_json=?,
                       published_year=?,abstract=COALESCE(?,abstract),updated_at=?
                       WHERE paper_id=?""",
                    (
                        title,
                        normalized_title,
                        json.dumps(authors, ensure_ascii=False)
                        if authors else row["authors_json"],
                        year if year is not None else row["published_year"],
                        abstract or None,
                        timestamp,
                        paper_id,
                    ),
                )
        else:
            paper_id = stable_id("paper", canonical_key)
            conn.execute(
                """INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,?)""",
                (
                    paper_id,
                    canonical_key,
                    doi,
                    normalized_title,
                    title,
                    json.dumps(authors, ensure_ascii=False),
                    year,
                    abstract or None,
                    timestamp,
                    timestamp,
                ),
            )
        if doi:
            conn.execute(
                """INSERT OR IGNORE INTO paper_identities
                   VALUES(?,?, 'DOI',?,'CONFIRMED','canonical',?)""",
                (stable_id("identity", "DOI", doi), paper_id, doi, timestamp),
            )
        return paper_id

    @staticmethod
    def _decode_authors(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [part.strip() for part in str(value).split(" and ") if part.strip()]

    def resolve_seed(self, seed_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            seed = conn.execute(
                "SELECT * FROM collection_seeds WHERE seed_id=?", (seed_id,)
            ).fetchone()
            if seed is None:
                raise ValueError(f"Unknown seed: {seed_id}")
        doi = normalize_doi(metadata.get("doi"))
        title = str(metadata.get("title") or (f"DOI {doi}" if doi else "")).strip()
        if not title:
            raise ValueError("Resolved seed has no title")
        authors = self._decode_authors(metadata.get("authors") or metadata.get("author"))
        raw_year = metadata.get("published_year") or metadata.get("year")
        year = int(raw_year) if str(raw_year or "").isdigit() else None
        paper_id = self._upsert_paper(
            title=title,
            doi=doi,
            authors=authors,
            year=year,
            abstract=metadata.get("abstract"),
            preserve_existing=True,
        )
        timestamp = utc_now()
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            from . import collection_runtime

            conn.execute(
                "UPDATE collection_seeds SET paper_id=? WHERE seed_id=?", (paper_id, seed_id)
            )
            provider = str(metadata.get("source_provider") or "seed")
            observation_digest = digest(metadata)
            conn.execute(
                """INSERT OR IGNORE INTO metadata_observations
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    stable_id("metadata", paper_id, provider, observation_digest),
                    paper_id,
                    provider,
                    timestamp,
                    "SUCCESS",
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    observation_digest,
                ),
            )
            self._record_journal_links(conn, paper_id, provider, metadata, timestamp)
            if collection_runtime.can_add_paper(conn, seed["collection_id"], paper_id):
                conn.execute(
                    """INSERT OR IGNORE INTO collection_memberships
                       VALUES(?,?, 'SEED',NULL,'DISCOVERED',?)""",
                    (seed["collection_id"], paper_id, timestamp),
                )
                self._enqueue(
                    conn,
                    collection_id=seed["collection_id"],
                    paper_id=paper_id,
                    job_type="SCREEN",
                    queue_class="MODEL_SCREEN",
                    payload={"scope_version": 1},
                    rule_version="screen-v1-scope-1",
                    priority=60,
                )
                if doi:
                    self._enqueue(
                        conn,
                        collection_id=seed["collection_id"],
                        paper_id=paper_id,
                        job_type="LOCATE_PDF",
                        queue_class="NETWORK",
                        payload={"doi": doi},
                        rule_version="fulltext-v1",
                        priority=50,
                    )
            else:
                saved = {"discovery_kind": "SEED", "metadata": metadata}
                conn.execute("INSERT INTO collection_candidate_frontier VALUES(?,?,'DEFERRED_BUDGET',?,?) ON CONFLICT(collection_id,paper_id) DO UPDATE SET metadata_json=excluded.metadata_json,updated_at=excluded.updated_at", (seed["collection_id"], paper_id, json.dumps(saved, ensure_ascii=False, sort_keys=True), timestamp))
        return self.get_paper(paper_id)

    def enrich_paper_metadata(self, paper_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Attach a provider observation without changing an established paper identity."""
        with transaction(self.db_path) as conn:
            paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
            if paper is None:
                raise ValueError(f"Unknown paper: {paper_id}")
            observed_doi = normalize_doi(metadata.get("doi"))
            if paper["doi"] and observed_doi and observed_doi != paper["doi"]:
                raise ValueError("Provider DOI conflicts with the established paper identity")
            title = str(metadata.get("title") or paper["title"]).strip()
            authors = self._decode_authors(metadata.get("authors") or metadata.get("author"))
            raw_year = metadata.get("published_year") or metadata.get("year")
            year = int(raw_year) if str(raw_year or "").isdigit() else paper["published_year"]
            timestamp = utc_now()
            conn.execute(
                """UPDATE papers SET title=?,normalized_title=?,authors_json=?,published_year=?,
                   abstract=COALESCE(?,abstract),updated_at=? WHERE paper_id=?""",
                (
                    title,
                    normalize_title(title),
                    json.dumps(authors, ensure_ascii=False) if authors else paper["authors_json"],
                    year,
                    metadata.get("abstract") or None,
                    timestamp,
                    paper_id,
                ),
            )
            provider = str(metadata.get("source_provider") or "provider")
            observation_digest = digest(metadata)
            conn.execute(
                """INSERT OR IGNORE INTO metadata_observations VALUES(?,?,?,?,?,?,?)""",
                (
                    stable_id("metadata", paper_id, provider, observation_digest),
                    paper_id,
                    provider,
                    timestamp,
                    "SUCCESS",
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    observation_digest,
                ),
            )
            self._record_journal_links(conn, paper_id, provider, metadata, timestamp)
        return self.get_paper(paper_id)

    @staticmethod
    def _record_journal_links(
        conn: sqlite3.Connection,
        paper_id: str,
        provider: str,
        metadata: dict[str, Any],
        timestamp: str,
    ) -> None:
        raw = metadata.get("raw") or {}
        values = raw.get("ISSN") or raw.get("issn") or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            issn = re.sub(r"[^0-9Xx]", "", str(value)).upper()
            if len(issn) == 8:
                conn.execute(
                    """INSERT OR IGNORE INTO paper_journal_links VALUES(?,?,?,?)""",
                    (paper_id, issn, provider, timestamp),
                )

    def import_journal_metrics_csv(
        self, payload: JournalMetricsImportInput
    ) -> dict[str, Any]:
        source = Path(payload.path).expanduser().resolve()
        allowed = self.import_root.resolve()
        if allowed not in source.parents:
            raise PermissionError("Journal export must be inside data/paper-import")
        if not source.is_file():
            raise FileNotFoundError(source)
        imported = 0
        errors: list[dict[str, Any]] = []
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        with transaction(self.db_path) as conn:
            for index, row in enumerate(rows, 2):
                try:
                    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
                    issn = re.sub(
                        r"[^0-9Xx]", "", str(normalized.get("issn") or "")
                    ).upper()
                    category = str(normalized.get("category") or "").strip()
                    quartile = str(normalized.get("quartile") or "").strip().upper() or None
                    citescore_text = str(normalized.get("citescore") or "").strip()
                    citescore = float(citescore_text) if citescore_text else None
                    if (
                        len(issn) != 8
                        or not category
                        or quartile not in {None, "Q1", "Q2", "Q3", "Q4"}
                    ):
                        raise ValueError("requires ISSN, category, and optional Q1-Q4 quartile")
                    raw_json = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    conn.execute(
                        """INSERT OR REPLACE INTO journal_metric_observations
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            stable_id(
                                "metric", issn, payload.source, payload.metric_year,
                                category, "CiteScore",
                            ),
                            issn,
                            payload.source,
                            payload.metric_year,
                            category,
                            quartile,
                            "CiteScore",
                            citescore,
                            raw_json,
                            utc_now(),
                        ),
                    )
                    imported += 1
                except Exception as exc:  # noqa: BLE001 - report each import row separately
                    errors.append({"line": index, "detail": str(exc)})
        return {"source": str(source), "rows": len(rows), "imported": imported, "errors": errors}

    def publish_skeleton_result(
        self,
        parse_run_id: str,
        units: list[dict[str, Any]],
        *,
        model_name: str | None,
        prompt_version: str = "paper-skeleton-v1",
        context_builder_version: str = "semantic-block-v1",
        job_id: str | None = None,
        worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        """Atomically publish complete Layer 1-4 checkpoints and the FieldKG-compatible view."""
        if not units or any(not all(f"layer{n}" in unit for n in range(1, 5)) for unit in units):
            raise ValueError("Every published Skeleton unit must contain Layers 1-4")
        timestamp = utc_now()
        skeleton_run_id = stable_id(
            "skeleton_run", parse_run_id, prompt_version, context_builder_version, model_name, digest(units)
        )
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            source = self._require_parse_source(conn, parse_run_id)
            if job_id is not None:
                assigned = conn.execute("SELECT * FROM acquisition_jobs WHERE job_id=?", (job_id,)).fetchone()
                if assigned is None or assigned["paper_id"] != source["paper_id"] or assigned["job_type"] != "SKELETON":
                    raise ValueError("Skeleton source does not belong to its task")
                self._require_membership(conn, assigned["collection_id"], source["paper_id"])
                self._require_publication_lease(conn, job_id, worker_id, fencing_token)
            parse = conn.execute(
                "SELECT * FROM parse_runs WHERE parse_run_id=? AND status='SUCCEEDED'",
                (parse_run_id,),
            ).fetchone()
            if parse is None:
                raise ValueError("Skeleton requires a completed parse run")
            conn.execute(
                """INSERT OR IGNORE INTO skeleton_runs VALUES(
                   ?,?,'standard',?,?,?,'SUCCEEDED',?,?)""",
                (
                    skeleton_run_id,
                    parse_run_id,
                    model_name,
                    prompt_version,
                    context_builder_version,
                    timestamp,
                    timestamp,
                ),
            )
            for unit in units:
                section_key = str(unit.get("block_id") or unit.get("sequence"))
                for layer in range(1, 5):
                    output = unit[f"layer{layer}"]
                    layer_contract = unit.get("layer_contracts", {}).get(str(layer), {})
                    input_digest = digest(
                        [unit.get("raw_text"), *[unit.get(f"layer{n}") for n in range(1, layer)]]
                    )
                    conn.execute(
                        """INSERT OR IGNORE INTO skeleton_checkpoints VALUES(
                           ?,?,?,?,?,?,'SUCCEEDED',?,?,?)""",
                        (
                            stable_id(
                                "checkpoint", skeleton_run_id, section_key, layer, input_digest
                            ),
                            skeleton_run_id,
                            section_key,
                            layer,
                            input_digest,
                            json.dumps(output, ensure_ascii=False, sort_keys=True),
                            layer_contract.get("actual_model", model_name),
                            layer_contract.get("prompt_version", f"skeleton-l{layer}-v1"),
                            timestamp,
                        ),
                    )
            paper_version = conn.execute(
                """SELECT pv.* FROM paper_versions pv
                   JOIN source_file_versions sf ON sf.paper_id=pv.paper_id
                   WHERE sf.file_version_id=? AND pv.pdf_digest=sf.sha256
                   AND json_extract(pv.source_json,'$.parse_run_id')=?
                   ORDER BY pv.version DESC LIMIT 1""",
                (parse["file_version_id"], parse_run_id),
            ).fetchone()
            if paper_version is None:
                raise ValueError("Parse run has no published paper version")
            content_digest = digest(units)
            skeleton_id = stable_id("skeleton", paper_version["paper_version_id"], content_digest)
            conn.execute(
                """INSERT OR IGNORE INTO paper_skeletons(
                   skeleton_id,paper_version_id,version,extractor_model,prompt_version,
                   content_digest,created_at) VALUES(?,?,COALESCE((SELECT MAX(version)+1
                   FROM paper_skeletons WHERE paper_version_id=?),1),?,?,?,?)""",
                (
                    skeleton_id,
                    paper_version["paper_version_id"],
                    paper_version["paper_version_id"],
                    model_name,
                    prompt_version,
                    content_digest,
                    timestamp,
                ),
            )
            for index, unit in enumerate(units):
                unit_id = stable_id("unit", skeleton_id, index)
                conn.execute(
                    """INSERT OR IGNORE INTO skeleton_units VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        unit_id,
                        skeleton_id,
                        index,
                        unit.get("page_number"),
                        unit.get("section"),
                        unit["raw_text"],
                        json.dumps(unit["layer1"], ensure_ascii=False, sort_keys=True),
                        json.dumps(unit["layer2"], ensure_ascii=False, sort_keys=True),
                        json.dumps(unit["layer3"], ensure_ascii=False, sort_keys=True),
                        str(unit["layer4"].get("role") or unit["layer4"].get("label") or "UNKNOWN"),
                        digest(unit),
                    ),
                )
                for triplet in unit["layer1"].get("triplets", []):
                    if all(triplet.get(key) for key in ("subject", "predicate", "object")):
                        conn.execute(
                            """INSERT OR IGNORE INTO skeleton_triplets
                               VALUES(?,?,?,?,?,?)""",
                            (
                                stable_id("triplet", unit_id, triplet),
                                unit_id,
                                triplet["subject"],
                                triplet["predicate"],
                                triplet["object"],
                                digest(triplet),
                            ),
                        )
        return {"skeleton_run_id": skeleton_run_id, "skeleton_id": skeleton_id, "units": len(units)}

    def record_assessment(
        self,
        collection_id: str,
        paper_id: str,
        assessment_type: str,
        result: dict[str, Any],
        evidence: list[dict[str, Any]],
        *,
        rule_version: str,
        input_digest: str,
        model_tier: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        parse_run_id: str | None = None,
        job_id: str | None = None,
        worker_id: str | None = None,
        fencing_token: int | None = None,
        expected_screen_context_sha256: str | None = None,
    ) -> dict[str, Any]:
        collection = self.get_collection(collection_id)
        assessment_id = stable_id(
            "assessment",
            paper_id,
            collection["field_id"],
            collection["track_id"],
            assessment_type,
            rule_version,
            input_digest,
        )
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._require_membership(conn, collection_id, paper_id)
            screen_context = None
            if assessment_type == "SCREEN":
                screen_context = self._screening_context(conn, collection_id, paper_id)
                screen_digest = digest(screen_context)
                if expected_screen_context_sha256 is not None and screen_digest != expected_screen_context_sha256:
                    raise ValueError("Screening context changed during processing")
                assessment_id = stable_id("assessment", assessment_id, screen_digest)
            if parse_run_id is not None:
                self._require_parse_source(conn, parse_run_id, paper_id)
            if job_id is not None:
                self._require_publication_lease(conn, job_id, worker_id, fencing_token)
            conn.execute(
                """INSERT OR IGNORE INTO paper_assessments
                   VALUES(?,?,?,?,?,'COMPLETED',?,?,?,?,?,?,?,?)""",
                (
                    assessment_id,
                    paper_id,
                    collection["field_id"],
                    collection["track_id"],
                    assessment_type,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    rule_version,
                    model_tier,
                    model_name,
                    prompt_version,
                    input_digest,
                    utc_now(),
                ),
            )
            if screen_context is not None:
                conn.execute("INSERT OR IGNORE INTO screening_input_snapshots VALUES(?,?,?,?,?)",
                             (assessment_id, collection_id, digest(screen_context),
                              json.dumps(screen_context, ensure_ascii=False, sort_keys=True), utc_now()))
            row = conn.execute(
                "SELECT * FROM paper_assessments WHERE assessment_id=?", (assessment_id,)
            ).fetchone()
        return dict(row)

    def _require_parse_source(self, conn: sqlite3.Connection, parse_run_id: str,
                              paper_id: str | None = None) -> dict:
        source = conn.execute("SELECT sf.* FROM source_file_versions sf JOIN parse_runs pr ON pr.file_version_id=sf.file_version_id WHERE pr.parse_run_id=? AND pr.status='SUCCEEDED'", (parse_run_id,)).fetchone()
        if source is None or source["identity_status"] != "VERIFIED" or (paper_id is not None and source["paper_id"] != paper_id):
            raise ValueError("Parsed source identity requires review before using its output")
        path = Path(source["storage_path"])
        if not path.is_file() or path.stat().st_size != source["size_bytes"] or self._file_digest(path) != source["sha256"]:
            raise ValueError("Original parsed PDF changed")
        return dict(source)

    @staticmethod
    def _require_publication_lease(conn: sqlite3.Connection, job_id: str,
                                  worker_id: str | None, fencing_token: int | None) -> None:
        if conn.execute("SELECT 1 FROM acquisition_jobs WHERE job_id=? AND status='RUNNING' AND lease_owner=? AND fencing_token=?",
                        (job_id, worker_id, fencing_token)).fetchone() is None:
            raise ValueError("Publication lease is stale")

    def publish_parse_result(
        self,
        collection_id: str,
        paper_id: str,
        file_version_id: str,
        *,
        parser_name: str,
        parser_version: str,
        config: dict[str, Any],
        manifest: dict[str, Any],
        blocks: list[dict[str, Any]],
        references: list[dict[str, Any]],
        job_id: str | None = None,
        worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        output_digest = digest({"manifest": manifest, "blocks": blocks, "references": references})
        publication_config = {"parser_configuration": config, "output_revision_sha256": output_digest}
        config_digest = digest(publication_config)
        stored_manifest = {**manifest, "publication": {
            "parser_configuration": config, "parser_configuration_sha256": digest(config),
            "output_revision_sha256": output_digest, "publication_configuration_sha256": config_digest}}
        parse_run_id = stable_id(
            "parse_run", file_version_id, parser_name, parser_version, config_digest, output_digest
        )
        timestamp = utc_now()
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._require_membership(conn, collection_id, paper_id)
            if job_id is not None:
                leased = conn.execute("SELECT * FROM acquisition_jobs WHERE job_id=? AND collection_id=? AND paper_id=? AND job_type='PARSE_PDF' AND status='RUNNING' AND lease_owner=? AND fencing_token=?",
                                      (job_id, collection_id, paper_id, worker_id, fencing_token)).fetchone()
                if leased is None or json.loads(leased["input_json"]).get("file_version_id") != file_version_id:
                    raise ValueError("Parser publication lease or source is stale")
            source_file = conn.execute(
                """SELECT * FROM source_file_versions WHERE file_version_id=?
                   AND paper_id=? AND identity_status='VERIFIED'""",
                (file_version_id, paper_id),
            ).fetchone()
            if source_file is None:
                raise ValueError("Only an identity-verified PDF may be parsed")
            source_path = Path(source_file["storage_path"])
            if (not source_path.is_file() or source_path.stat().st_size != source_file["size_bytes"]
                    or self._file_digest(source_path) != source_file["sha256"]):
                raise ValueError("Original PDF changed before parser publication")
            missing = manifest.get("quality", {}).get("reference_page_alignment", {}).get("missing_source_numbered_references", [])
            if missing:
                raise ValueError("Parser quality gate still has missing original references")
            if not any(str(block.get("text") or "").strip() for block in blocks):
                raise ValueError("Parser output has no readable document blocks")
            conn.execute(
                """INSERT OR IGNORE INTO parse_runs
                   VALUES(?,?,?,?,?,'SUCCEEDED',?,?,?)""",
                (
                    parse_run_id,
                    file_version_id,
                    parser_name,
                    parser_version,
                    config_digest,
                    json.dumps(stored_manifest, ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                ),
            )
            for sequence, block in enumerate(blocks):
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                block_digest = digest(block)
                conn.execute(
                    """INSERT OR IGNORE INTO document_blocks
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        stable_id("block", parse_run_id, sequence, block_digest),
                        parse_run_id,
                        sequence,
                        block.get("page_number"),
                        block.get("section"),
                        block.get("block_type", "TEXT"),
                        text,
                        json.dumps(block.get("location", {}), ensure_ascii=False),
                        block_digest,
                    ),
                )
            paper_version_id = stable_id("paper_version", paper_id, source_file["sha256"], parse_run_id)
            conn.execute(
                """INSERT OR IGNORE INTO paper_versions(
                   paper_version_id,paper_id,version,pdf_path,pdf_digest,parsed_path,
                   parsed_digest,source_json,created_at)
                   VALUES(?,?,COALESCE((SELECT MAX(version)+1 FROM paper_versions
                   WHERE paper_id=?),1),?,?,?,?,?,?)""",
                (
                    paper_version_id,
                    paper_id,
                    paper_id,
                    source_file["storage_path"],
                    source_file["sha256"],
                    manifest.get("structured_path"),
                    output_digest,
                    json.dumps(
                        {"parse_run_id": parse_run_id, "file_version_id": file_version_id}
                    ),
                    timestamp,
                ),
            )
            for entry in references:
                self._record_reference(
                    conn, collection_id, paper_id, file_version_id, entry, timestamp
                )
            self._enqueue(
                conn,
                collection_id=collection_id,
                paper_id=paper_id,
                job_type="QUICK_READ",
                queue_class="MODEL_READ",
                payload={"parse_run_id": parse_run_id},
                rule_version="quick-read-v1",
                priority=70,
            )
        return {"parse_run_id": parse_run_id, "paper_version_id": paper_version_id,
                "blocks": len(blocks), "references": len(references)}

    def _record_reference(
        self,
        conn: sqlite3.Connection,
        collection_id: str,
        citing_paper_id: str,
        file_version_id: str,
        entry: dict[str, Any],
        timestamp: str,
    ) -> None:
        raw_text = str(entry.get("raw_text") or "").strip()
        if not raw_text:
            return
        entry_digest = digest(
            [raw_text, entry.get("page_number"), entry.get("location", {})]
        )
        reference_entry_id = stable_id("reference", file_version_id, entry_digest)
        doi_match = DOI_PATTERN.search(raw_text)
        doi = normalize_doi(entry.get("doi") or (doi_match.group(0) if doi_match else None))
        target_paper_id = None
        screen_backlog = conn.execute(
            """SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=?
               AND job_type='SCREEN' AND status NOT IN ('SUCCEEDED','SKIPPED','FAILED_TERMINAL')""",
            (collection_id,),
        ).fetchone()[0]
        deferred = bool(doi and screen_backlog >= 500)
        from . import collection_runtime

        budget_deferred = False
        if doi and not deferred:
            existing = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (doi,)).fetchone()
            budget_deferred = not collection_runtime.can_add_paper(conn, collection_id, existing[0] if existing else None)
        if doi and not deferred and not budget_deferred:
            target_paper_id = self._ensure_doi_paper(
                conn, doi, entry.get("title"), entry.get("year"), timestamp
            )
            conn.execute(
                """INSERT OR IGNORE INTO collection_memberships
                   VALUES(?,?, 'PDF_REFERENCE',?,'DISCOVERED',?)""",
                (collection_id, target_paper_id, citing_paper_id, timestamp),
            )
        conn.execute(
                """INSERT OR IGNORE INTO reference_entries
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                reference_entry_id,
                citing_paper_id,
                file_version_id,
                raw_text,
                entry.get("page_number"),
                json.dumps(entry.get("location", {}), ensure_ascii=False),
                target_paper_id,
                (
                    "RESOLVED" if target_paper_id
                    else "DEFERRED_BACKPRESSURE" if deferred
                    else "UNRESOLVED"
                ),
                entry_digest,
                timestamp,
            ),
        )
        if budget_deferred:
            conn.execute("INSERT INTO collection_reference_frontier VALUES(?,?,'DEFERRED_BUDGET',?) "
                         "ON CONFLICT(collection_id,reference_entry_id) DO UPDATE SET state='DEFERRED_BUDGET',updated_at=excluded.updated_at",
                         (collection_id, reference_entry_id, timestamp))
        if target_paper_id:
            conn.execute("UPDATE reference_entries SET target_paper_id=?,resolution_status='RESOLVED' WHERE reference_entry_id=?",
                         (target_paper_id, reference_entry_id))
            conn.execute("INSERT INTO collection_reference_frontier VALUES(?,?,'RESOLVED',?) "
                         "ON CONFLICT(collection_id,reference_entry_id) DO UPDATE SET state='RESOLVED',updated_at=excluded.updated_at",
                         (collection_id, reference_entry_id, timestamp))
            conn.execute(
                """INSERT OR IGNORE INTO citation_observations
                   VALUES(?,?,?,?, 'UNCLASSIFIED','PDF',?)""",
                (
                    stable_id("citation", citing_paper_id, target_paper_id, reference_entry_id),
                    citing_paper_id,
                    target_paper_id,
                    reference_entry_id,
                    timestamp,
                ),
            )
            self._enqueue(
                conn,
                collection_id=collection_id,
                paper_id=target_paper_id,
                job_type="RESOLVE_PAPER",
                queue_class="NETWORK",
                payload={"doi": doi, "reference_entry_id": reference_entry_id},
                rule_version="identity-v1",
                priority=40,
            )

    def request_reference_lookups(
        self, collection_id: str, paper_id: str, *, limit: int = 20
    ) -> dict[str, Any]:
        """Queue a bounded lookup batch for DOI-free references of one parsed paper."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        self.get_collection(collection_id)
        job_ids = []
        with transaction(self.db_path) as conn:
            self._require_membership(conn, collection_id, paper_id)
            rows = conn.execute(
                """SELECT reference_entry_id,raw_text FROM reference_entries
                   WHERE citing_paper_id=? AND resolution_status='UNRESOLVED'
                   ORDER BY created_at,reference_entry_id""",
                (paper_id,),
            ).fetchall()
            for row in rows:
                raw_text = row["raw_text"]
                if (
                    DOI_PATTERN.search(raw_text)
                    or len(raw_text) < 60
                    or not re.search(r"\b(?:19|20)\d{2}\b", raw_text)
                ):
                    continue
                key = stable_id(
                    "reference_lookup", collection_id, row["reference_entry_id"]
                )
                if conn.execute(
                    "SELECT 1 FROM acquisition_jobs WHERE job_id=?",
                    (stable_id("job", key),),
                ).fetchone():
                    continue
                job_ids.append(self._enqueue(
                    conn, collection_id=collection_id, paper_id=paper_id,
                    job_type="RESOLVE_REFERENCE", queue_class="NETWORK",
                    payload={"reference_entry_id": row["reference_entry_id"]},
                    rule_version="bibliographic-v1", priority=20,
                    idempotency_key=key,
                ))
                if len(job_ids) >= limit:
                    break
        return {"collection_id": collection_id, "paper_id": paper_id,
                "queued": len(job_ids), "job_ids": job_ids}

    def publish_bibliographic_reference_match(
        self, collection_id: str, reference_entry_id: str, candidate: SourceCandidate
    ) -> dict[str, Any]:
        """Attach a conservatively matched DOI and preserve the cited source observation."""
        doi = normalize_doi(candidate.doi)
        if not doi:
            raise ValueError("Bibliographic match needs a DOI")
        with transaction(self.db_path) as conn:
            reference = conn.execute(
                "SELECT * FROM reference_entries WHERE reference_entry_id=?",
                (reference_entry_id,),
            ).fetchone()
            if reference is None:
                raise ValueError(f"Unknown reference: {reference_entry_id}")
            self._require_membership(conn, collection_id, reference["citing_paper_id"])
        target_paper_id = self._upsert_paper(
            title=candidate.title, doi=doi, authors=candidate.authors,
            year=candidate.published_year, abstract=candidate.abstract,
        )
        self.enrich_paper_metadata(target_paper_id, candidate.model_dump(mode="json"))
        timestamp = utc_now()
        with transaction(self.db_path) as conn:
            reference = conn.execute(
                "SELECT * FROM reference_entries WHERE reference_entry_id=?",
                (reference_entry_id,),
            ).fetchone()
            if reference is None:
                raise ValueError(f"Unknown reference: {reference_entry_id}")
            self._require_membership(conn, collection_id, reference["citing_paper_id"])
            if reference["target_paper_id"] not in (None, target_paper_id):
                raise ValueError("Reference already points to a different paper")
            conn.execute(
                """UPDATE reference_entries SET target_paper_id=?,
                   resolution_status='RESOLVED' WHERE reference_entry_id=?""",
                (target_paper_id, reference_entry_id),
            )
            conn.execute(
                """INSERT OR IGNORE INTO collection_memberships
                   VALUES(?,?,'PDF_REFERENCE',?,'DISCOVERED',?)""",
                (collection_id, target_paper_id, reference["citing_paper_id"], timestamp),
            )
            conn.execute(
                """INSERT OR IGNORE INTO citation_observations
                   VALUES(?,?,?,?, 'UNCLASSIFIED','PDF',?)""",
                (
                    stable_id("citation", reference["citing_paper_id"], target_paper_id,
                              reference_entry_id),
                    reference["citing_paper_id"], target_paper_id, reference_entry_id,
                    timestamp,
                ),
            )
            self._enqueue(
                conn, collection_id=collection_id, paper_id=target_paper_id,
                job_type="SCREEN", queue_class="MODEL_SCREEN",
                payload={"scope_version": 1},
                rule_version="screen-v1-scope-1", priority=40,
            )
            self._enqueue(
                conn, collection_id=collection_id, paper_id=target_paper_id,
                job_type="LOCATE_PDF", queue_class="NETWORK",
                payload={"doi": doi}, rule_version="fulltext-v1", priority=30,
            )
        return {"reference_entry_id": reference_entry_id,
                "target_paper_id": target_paper_id, "doi": doi}

    @staticmethod
    def _ensure_doi_paper(
        conn: sqlite3.Connection,
        doi: str,
        title: Any,
        year: Any,
        timestamp: str,
    ) -> str:
        row = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (doi,)).fetchone()
        if row:
            return row["paper_id"]
        paper_id = stable_id("paper", f"doi:{doi}")
        conn.execute(
            """INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,?)""",
            (
                paper_id,
                f"doi:{doi}",
                doi,
                normalize_title(str(title or f"DOI {doi}")),
                str(title or f"DOI {doi}"),
                "[]",
                year if str(year or "").isdigit() else None,
                None,
                timestamp,
                timestamp,
            ),
        )
        return paper_id

    def release_deferred_references(self, collection_id: str, *, limit: int = 250) -> int:
        """Resume target materialization only after the unscreened backlog falls to 250."""
        with transaction(self.db_path) as conn:
            backlog = conn.execute(
                """SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=?
                   AND job_type='SCREEN'
                   AND status NOT IN ('SUCCEEDED','SKIPPED','FAILED_TERMINAL')""",
                (collection_id,),
            ).fetchone()[0]
            if backlog > 250:
                return 0
            rows = conn.execute(
                """SELECT r.* FROM reference_entries r JOIN collection_memberships m
                   ON m.paper_id=r.citing_paper_id WHERE m.collection_id=?
                   AND (r.resolution_status='DEFERRED_BACKPRESSURE' OR EXISTS(
                     SELECT 1 FROM collection_reference_frontier f WHERE f.collection_id=?
                     AND f.reference_entry_id=r.reference_entry_id AND f.state='DEFERRED_BUDGET'))
                   ORDER BY r.created_at LIMIT ?""",
                (collection_id, collection_id, min(max(limit, 1), 500)),
            ).fetchall()
            timestamp = utc_now()
            released = 0
            for row in rows:
                match = DOI_PATTERN.search(row["raw_text"])
                if not match:
                    continue
                doi = normalize_doi(match.group(0))
                if not doi:
                    continue
                from . import collection_runtime

                existing = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (doi,)).fetchone()
                if not collection_runtime.can_add_paper(conn, collection_id, existing[0] if existing else None):
                    conn.execute("INSERT INTO collection_reference_frontier VALUES(?,?,'DEFERRED_BUDGET',?) "
                                 "ON CONFLICT(collection_id,reference_entry_id) DO UPDATE SET state='DEFERRED_BUDGET',updated_at=excluded.updated_at",
                                 (collection_id, row["reference_entry_id"], timestamp))
                    continue
                target = self._ensure_doi_paper(conn, doi, None, None, timestamp)
                conn.execute(
                    """UPDATE reference_entries SET target_paper_id=?,resolution_status='RESOLVED'
                       WHERE reference_entry_id=?""",
                    (target, row["reference_entry_id"]),
                )
                conn.execute("INSERT INTO collection_reference_frontier VALUES(?,?,'RESOLVED',?) "
                             "ON CONFLICT(collection_id,reference_entry_id) DO UPDATE SET state='RESOLVED',updated_at=excluded.updated_at",
                             (collection_id, row["reference_entry_id"], timestamp))
                conn.execute(
                    """INSERT OR IGNORE INTO collection_memberships
                       VALUES(?,?,'PDF_REFERENCE',?,'DISCOVERED',?)""",
                    (collection_id, target, row["citing_paper_id"], timestamp),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO citation_observations
                       VALUES(?,?,?,?, 'UNCLASSIFIED','PDF',?)""",
                    (
                        stable_id(
                            "citation",
                            row["citing_paper_id"],
                            target,
                            row["reference_entry_id"],
                        ),
                        row["citing_paper_id"],
                        target,
                        row["reference_entry_id"],
                        timestamp,
                    ),
                )
                self._enqueue(
                    conn, collection_id=collection_id, paper_id=target,
                    job_type="RESOLVE_PAPER", queue_class="NETWORK",
                    payload={"doi": doi, "reference_entry_id": row["reference_entry_id"]},
                    rule_version="identity-v1", priority=40,
                )
                released += 1
        return released

    def get_core_candidates(
        self, collection_id: str, *, scope_kind: str = "FIELD", limit: int = 100
    ) -> list[dict[str, Any]]:
        collection = self.get_collection(collection_id)
        scope_kind = scope_kind.upper()
        if scope_kind not in {"FIELD", "TRACK"}:
            raise ValueError("scope_kind must be FIELD or TRACK")
        scope_id = collection["field_id"] if scope_kind == "FIELD" else collection["track_id"]
        if not scope_id:
            raise ValueError("This collection has no track scope")
        with transaction(self.db_path) as conn:
            members = {
                row["paper_id"]
                for row in conn.execute(
                    "SELECT paper_id FROM collection_memberships WHERE collection_id=?",
                    (collection_id,),
                )
            }
            seeds = {
                row["paper_id"]
                for row in conn.execute(
                    """SELECT paper_id FROM collection_seeds
                       WHERE collection_id=? AND paper_id IS NOT NULL""",
                    (collection_id,),
                )
            }
            edges = [
                (row["citing_paper_id"], row["cited_paper_id"])
                for row in conn.execute(
                    """SELECT c.citing_paper_id,c.cited_paper_id FROM citation_observations c
                       JOIN collection_memberships m ON m.paper_id=c.citing_paper_id
                       WHERE m.collection_id=?""",
                    (collection_id,),
                )
                if row["cited_paper_id"] in members
            ]
            relevance = {}
            for assessment in conn.execute(
                "SELECT a.*,s.context_sha256 FROM paper_assessments a "
                "JOIN screening_input_snapshots s ON s.assessment_id=a.assessment_id "
                "WHERE s.collection_id=? AND a.assessment_type='SCREEN' ORDER BY a.created_at,a.rowid",
                (collection_id,),
            ):
                if assessment["paper_id"] in members and assessment["context_sha256"] == digest(self._screening_context(conn, collection_id, assessment["paper_id"])):
                    relevance[assessment["paper_id"]] = json.loads(assessment["result_json"]).get("category", "UNKNOWN")
            mapped_category = collection["scope"].get("scopus_category")
            quartiles: dict[str, str] = {}
            if mapped_category:
                quartiles = {
                    row["paper_id"]: row["quartile"]
                    for row in conn.execute(
                        """SELECT l.paper_id,m.quartile,MAX(m.metric_year)
                           FROM paper_journal_links l
                           JOIN journal_metric_observations m ON m.issn=l.issn
                           WHERE m.source='SCOPUS_CITESCORE' AND m.category=?
                           AND m.quartile IS NOT NULL GROUP BY l.paper_id""",
                        (mapped_category,),
                    )
                }
        adjacency: dict[str, set[str]] = {paper: set() for paper in members}
        incoming: dict[str, set[str]] = {paper: set() for paper in members}
        for source, target in edges:
            adjacency.setdefault(source, set()).add(target)
            incoming.setdefault(target, set()).add(source)
        coverage: dict[str, int] = {paper: 0 for paper in members}
        for seed in seeds:
            pending = deque(adjacency.get(seed, set()))
            seen = set(pending)
            while pending:
                current = pending.popleft()
                coverage[current] = coverage.get(current, 0) + 1
                for target in adjacency.get(current, set()):
                    if target not in seen and target != seed:
                        seen.add(target)
                        pending.append(target)
        group_order = {
            "DIRECT": 0,
            "METHOD_DATA": 1,
            "BACKGROUND": 2,
            "UNKNOWN": 3,
            "IRRELEVANT": 4,
        }
        quartile_order = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}
        ranked = sorted(
            members,
            key=lambda paper: (
                group_order.get(relevance.get(paper, "UNKNOWN"), 3),
                -coverage.get(paper, 0),
                -len(incoming.get(paper, set())),
                quartile_order.get(quartiles.get(paper, ""), 4),
                paper,
            ),
        )[: min(max(limit, 1), 500)]
        results = [
            {
                "rank": index,
                "paper_id": paper,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "relevance_group": relevance.get(paper, "UNKNOWN"),
                "seed_coverage": coverage.get(paper, 0) / max(1, len(seeds)),
                "direct_citations": len(incoming.get(paper, set())),
                "quartile": quartiles.get(paper),
                "full_text_verified": self._has_verified_pdf(paper),
            }
            for index, paper in enumerate(ranked, 1)
        ]
        graph_digest = digest(
            {"members": sorted(members), "seeds": sorted(seeds), "edges": sorted(edges),
             "scope_version": collection["scope_version"], "scope": collection["scope"],
             "relevance": relevance, "quartiles": quartiles}
        )
        with transaction(self.db_path) as conn:
            timestamp = utc_now()
            for item in results:
                explanation = {
                    "order": ["relevance_group", "seed_coverage", "direct_citations", "quartile"],
                    "full_text_verified": item["full_text_verified"],
                    "content_status": (
                        "FULL_TEXT_VERIFIED" if item["full_text_verified"] else "NETWORK_ONLY"
                    ),
                }
                conn.execute(
                    """INSERT OR IGNORE INTO core_rankings VALUES(
                       ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        stable_id(
                            "core", collection_id, item["paper_id"], scope_kind,
                            scope_id, graph_digest, "core-v1",
                        ),
                        collection_id,
                        item["paper_id"],
                        scope_kind,
                        scope_id,
                        item["rank"],
                        item["relevance_group"],
                        item["seed_coverage"],
                        item["direct_citations"],
                        item["quartile"],
                        json.dumps([], ensure_ascii=False),
                        json.dumps(explanation, ensure_ascii=False, sort_keys=True),
                        graph_digest,
                        "core-v1",
                        timestamp,
                    ),
                )
        return results

    def get_citation_neighborhood(
        self, paper_id: str, *, collection_id: str | None = None
    ) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            params: list[Any] = [paper_id, paper_id]
            condition = ""
            if collection_id:
                condition = (
                    " AND c.citing_paper_id IN (SELECT paper_id FROM collection_memberships "
                    "WHERE collection_id=?)"
                )
                params.append(collection_id)
            rows = conn.execute(
                """SELECT c.* FROM citation_observations c
                   WHERE (c.citing_paper_id=? OR c.cited_paper_id=?)""" + condition,
                params,
            ).fetchall()
        return {"paper_id": paper_id, "edges": [dict(row) for row in rows]}

    def add_processed_papers_to_fieldkg_build(
        self, build_id: str, paper_ids: Iterable[str]
    ) -> dict[str, Any]:
        added: list[str] = []
        with transaction(self.db_path) as conn:
            build = conn.execute(
                "SELECT * FROM fieldkg_builds WHERE build_id=?", (build_id,)
            ).fetchone()
            if build is None:
                raise ValueError(f"Unknown FieldKG build: {build_id}")
            for paper_id in paper_ids:
                row = conn.execute(
                    """SELECT pv.paper_version_id,ps.skeleton_id FROM paper_versions pv
                       JOIN paper_skeletons ps ON ps.paper_version_id=pv.paper_version_id
                       WHERE pv.paper_id=? ORDER BY ps.version DESC LIMIT 1""",
                    (paper_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Paper has no completed canonical Skeleton: {paper_id}")
                conn.execute(
                    """INSERT OR IGNORE INTO fieldkg_build_papers
                       VALUES(?,?,?,'IMPORTED',NULL)""",
                    (build_id, row["paper_version_id"], row["skeleton_id"]),
                )
                added.append(paper_id)
            conn.execute(
                """UPDATE fieldkg_builds SET status='EXTRACTING_EVIDENCE',
                   revision=revision+1,updated_at=? WHERE build_id=?""",
                (utc_now(), build_id),
            )
        return {"build_id": build_id, "paper_ids": added, "added": len(added)}

    def claim_job(
        self,
        worker_id: str,
        queue_classes: list[str],
        *,
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        if not queue_classes:
            return None
        now = datetime.now(UTC)
        expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            ordered_queues = list(queue_classes)
            if len(ordered_queues) > 1:
                placeholders = ",".join("?" for _ in ordered_queues)
                last = conn.execute(
                    f"""SELECT j.queue_class FROM acquisition_attempts a
                        JOIN acquisition_jobs j ON j.job_id=a.job_id
                        WHERE j.queue_class IN ({placeholders})
                        ORDER BY a.started_at DESC LIMIT 1""",
                    ordered_queues,
                ).fetchone()
                if last and last["queue_class"] in ordered_queues:
                    index = ordered_queues.index(last["queue_class"]) + 1
                    ordered_queues = ordered_queues[index:] + ordered_queues[:index]
            recent_priorities = [
                item["priority"]
                for item in conn.execute(
                    """SELECT j.priority FROM acquisition_attempts a
                       JOIN acquisition_jobs j ON j.job_id=a.job_id
                       ORDER BY a.started_at DESC LIMIT 3"""
                )
            ]
            yield_to_normal = len(recent_priorities) == 3 and all(
                priority >= 200 for priority in recent_priorities
            )
            row = None
            from . import collection_runtime

            for queue_class in ordered_queues:
                while True:
                    row = conn.execute(
                        """SELECT j.* FROM acquisition_jobs j JOIN collections c
                           ON c.collection_id=j.collection_id
                           WHERE c.status='ACTIVE' AND j.queue_class=?
                           AND (j.status='READY'
                                OR (j.status IN ('RETRY_WAIT','RESOURCE_WAIT') AND j.available_at<=?)
                                OR (j.status='RUNNING' AND j.lease_expires_at<?))
                           ORDER BY CASE WHEN ? AND j.priority>=200 THEN 1 ELSE 0 END,
                                    j.priority DESC,j.available_at,j.created_at LIMIT 1""",
                        (queue_class, now.isoformat(), now.isoformat(), yield_to_normal),
                    ).fetchone()
                    if row is None:
                        break
                    if row["job_type"] == "RESOLVE_SEED":
                        seed_input = json.loads(row["input_json"])
                        seed_doi = normalize_doi(seed_input.get("identity", {}).get("doi"))
                        existing_paper = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (seed_doi,)).fetchone() if seed_doi else None
                        if not collection_runtime.can_add_paper(conn, row["collection_id"], existing_paper[0] if existing_paper else None):
                            row = None
                            continue
                    stopped = collection_runtime.dispatch_stop(conn, row["collection_id"])
                    if stopped:
                        collection_runtime.pause_for_budget(conn, row["collection_id"], stopped)
                        row = None
                        continue
                    break
                if row is not None:
                    break
            if row is None:
                return None
            token = int(row["fencing_token"]) + 1
            conn.execute(
                """UPDATE acquisition_jobs SET status='RUNNING',lease_owner=?,lease_expires_at=?,
                   fencing_token=?,attempts=attempts+1,updated_at=? WHERE job_id=?""",
                (worker_id, expires, token, now.isoformat(), row["job_id"]),
            )
            attempt_id = new_id("attempt")
            conn.execute(
                "INSERT INTO acquisition_attempts VALUES(?,?,?,?,?,?,?,?)",
                (
                    attempt_id, row["job_id"], token, worker_id, "RUNNING",
                    now.isoformat(), None, "{}",
                ),
            )
            claimed = conn.execute(
                "SELECT * FROM acquisition_jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
        return dict(claimed)

    def renew_lease(
        self, job_id: str, worker_id: str, fencing_token: int, *, lease_seconds: int = 120
    ) -> bool:
        expires = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE acquisition_jobs SET lease_expires_at=?,updated_at=?
                   WHERE job_id=? AND status='RUNNING' AND lease_owner=? AND fencing_token=?""",
                (expires, utc_now(), job_id, worker_id, fencing_token),
            )
        return cursor.rowcount == 1

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        result: dict[str, Any],
        next_jobs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                """SELECT * FROM acquisition_jobs WHERE job_id=? AND status='RUNNING'
                   AND lease_owner=? AND fencing_token=?""",
                (job_id, worker_id, fencing_token),
            ).fetchone()
            if row is None:
                raise ValueError("Job lease is stale")
            timestamp = utc_now()
            conn.execute(
                """UPDATE acquisition_jobs SET status='SUCCEEDED',result_json=?,lease_owner=NULL,
                   lease_expires_at=NULL,updated_at=? WHERE job_id=?""",
                (json.dumps(result, ensure_ascii=False, sort_keys=True), timestamp, job_id),
            )
            conn.execute(
                """UPDATE acquisition_attempts SET status='SUCCEEDED',completed_at=?,detail_json=?
                   WHERE job_id=? AND fencing_token=?""",
                (timestamp, json.dumps(result, ensure_ascii=False), job_id, fencing_token),
            )
            for item in next_jobs or []:
                self._enqueue(
                    conn,
                    collection_id=row["collection_id"],
                    paper_id=item.get("paper_id", row["paper_id"]),
                    job_type=item["job_type"],
                    queue_class=item["queue_class"],
                    payload=item.get("payload", {}),
                    rule_version=item.get("rule_version", "v1"),
                    priority=item.get("priority", 0),
                )
        return self.get_job(job_id)

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        error_code: str,
        detail: str,
        retry_after_seconds: int | None = None,
        terminal: bool = False,
    ) -> dict[str, Any]:
        status = "FAILED_TERMINAL" if terminal else "RETRY_WAIT"
        delay = retry_after_seconds if retry_after_seconds is not None else 30
        available = (datetime.now(UTC) + timedelta(seconds=max(0, delay))).isoformat()
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE acquisition_jobs SET status=?,available_at=?,lease_owner=NULL,
                   lease_expires_at=NULL,last_error_code=?,last_error_detail=?,updated_at=?
                   WHERE job_id=? AND status='RUNNING' AND lease_owner=? AND fencing_token=?""",
                (
                    status,
                    available,
                    error_code,
                    detail[:8000],
                    utc_now(),
                    job_id,
                    worker_id,
                    fencing_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Job lease is stale")
            conn.execute(
                """UPDATE acquisition_attempts SET status=?,completed_at=?,detail_json=?
                   WHERE job_id=? AND fencing_token=?""",
                (
                    status,
                    utc_now(),
                    json.dumps({"error_code": error_code, "detail": detail}, ensure_ascii=False),
                    job_id,
                    fencing_token,
                ),
            )
        return self.get_job(job_id)

    def defer_job(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        status: str,
        error_code: str,
        detail: str,
        retry_after_seconds: int,
        review_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"RESOURCE_WAIT", "NEEDS_HUMAN"}:
            raise ValueError("Deferred status must be RESOURCE_WAIT or NEEDS_HUMAN")
        available = (
            datetime.now(UTC) + timedelta(seconds=max(0, retry_after_seconds))
        ).isoformat()
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE acquisition_jobs SET status=?,available_at=?,lease_owner=NULL,
                    lease_expires_at=NULL,last_error_code=?,last_error_detail=?,updated_at=?,
                    result_json=CASE WHEN ? IS NULL THEN result_json ELSE ? END
                   WHERE job_id=? AND status='RUNNING' AND lease_owner=? AND fencing_token=?""",
                (
                    status,
                    available,
                    error_code,
                    detail[:8000],
                    utc_now(),
                    1 if review_context else None,
                    json.dumps({"review": review_context}, ensure_ascii=False) if review_context else None,
                    job_id,
                    worker_id,
                    fencing_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Job lease is stale")
            conn.execute(
                """UPDATE acquisition_attempts SET status=?,completed_at=?,detail_json=?
                   WHERE job_id=? AND fencing_token=?""",
                (
                    status,
                    utc_now(),
                    json.dumps({"error_code": error_code, "detail": detail,
                                "review": review_context}, ensure_ascii=False),
                    job_id,
                    fencing_token,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM acquisition_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown job: {job_id}")
        return dict(row)

    def _enqueue(
        self,
        conn: sqlite3.Connection,
        *,
        collection_id: str,
        paper_id: str | None,
        job_type: str,
        queue_class: str,
        payload: dict[str, Any],
        rule_version: str,
        priority: int,
        idempotency_key: str | None = None,
    ) -> str:
        input_digest = digest(payload)
        key = idempotency_key or digest(
            [collection_id, paper_id, job_type, input_digest, rule_version]
        )
        job_id = stable_id("job", key)
        timestamp = utc_now()
        conn.execute(
            """INSERT OR IGNORE INTO acquisition_jobs(
               job_id,collection_id,paper_id,job_type,queue_class,status,priority,
               idempotency_key,input_json,input_digest,rule_version,attempts,available_at,
               lease_owner,lease_expires_at,fencing_token,last_error_code,last_error_detail,
               result_json,created_at,updated_at)
               VALUES(?,?,?,?,?,'READY',?,?,?,?,?,0,?,NULL,NULL,0,NULL,NULL,NULL,?,?)""",
            (
                job_id,
                collection_id,
                paper_id,
                job_type,
                queue_class,
                priority,
                key,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                input_digest,
                rule_version,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        return job_id

    @staticmethod
    def _require_membership(
        conn: sqlite3.Connection, collection_id: str, paper_id: str
    ) -> None:
        row = conn.execute(
            """SELECT 1 FROM collection_memberships
               WHERE collection_id=? AND paper_id=?""",
            (collection_id, paper_id),
        ).fetchone()
        if row is None:
            raise ValueError("Paper is not a member of this collection")

    def _has_verified_pdf(self, paper_id: str) -> bool:
        with transaction(self.db_path) as conn:
            if conn.execute(
                "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (paper_id,)
            ).fetchone():
                return False
            return conn.execute(
                """SELECT 1 FROM source_file_versions
                   WHERE paper_id=? AND identity_status='VERIFIED' LIMIT 1""",
                (paper_id,),
            ).fetchone() is not None

    @staticmethod
    def _file_digest(path: Path) -> str:
        value = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(block)
        return value.hexdigest()


def parse_bibtex_seeds(text: str) -> list[dict[str, str]]:
    return _bibtex_entries(text)
