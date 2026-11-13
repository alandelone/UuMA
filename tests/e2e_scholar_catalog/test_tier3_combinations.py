"""Tier 3: Cross-Feature Combinations E2E Tests (PW01–PW07).

Pairwise interactions across architectural seams:
- Semantic search + Theme candidates
- Human theme corrections + Candidate relations
- L1–L4 skeleton views + Evidence archive export
- Relocated sources + Target adoption rollback
- Freshness invalidation + Night window batch re-indexing
- FastMCP tools + Candidate relation streaming
- Decoupled purpose judgments + Target adoption
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import rstv4.catalog_content_retrieval as retrieval
import rstv4.catalog_content_tools as tools
import rstv4.catalog_history_adoption as adoption
import rstv4.catalog_theme_corrections as corrections
import rstv4.reading_policy as policy
from .conftest import (
    MockEmbeddings,
    create_sealed_evidence_archive,
    default_card,
    make_paper_source,
    populate_skeleton_l1_to_l4,
)
from rstv4.catalog_content_retrieval import CatalogContentRetrieval
from rstv4.catalog_mcp_views import MAX_RESPONSE_CHARACTERS, encoded
from rstv4.catalog_understanding import CatalogUnderstanding
from rstv4.database import initialize_catalog, transaction
from rstv4.paper_sources import require_pdf_source


# PW01: Semantic Search + Theme Filtering & Distinct Paper Counts
def test_pw01_semantic_search_and_theme_filtering(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # Search for term present in both p1 and p2 themes
    result = index.search("decentralized governance")
    assert result["mode"] == "HYBRID"
    assert result["paper_count"] >= 1

    # Check distinct paper counts in theme aggregation
    theme_counts = result.get("theme_counts", [])
    assert theme_counts, "Hybrid search must aggregate theme occurrences"
    assert any(t["paper_count"] >= 1 for t in theme_counts)
    assert all(t["paper_count"] <= result["paper_count"] for t in theme_counts)
    assert all("group_id" in t for t in theme_counts)


# PW02: Human Theme Corrections + Candidate Semantic Relations
def test_pw02_human_theme_corrections_and_candidate_relations(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    embedder = catalog_sandbox["embedder"]
    store = CatalogUnderstanding(root)
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # 1. Capture initial candidate relations
    initial_proposals = index.candidate_relations(min_similarity=0.0)
    assert initial_proposals["applied_merges"] == 0

    # 2. Perform human correction on a theme observation
    with transaction(db_path) as conn:
        obs = conn.execute("SELECT * FROM catalog_theme_observations LIMIT 1").fetchone()
        obs_id = obs["observation_id"]
        evidence = json.loads(obs["evidence_json"])

    corrected = {
        "label": "Decentralized Energy Governance (Peer Review v2)",
        "definition": "Refined taxonomy of decision authority in microgrid settlements.",
        "role": "CENTRAL",
        "evidence": evidence,
    }
    applied = corrections.replace(
        store,
        observation_id=obs_id,
        expected_revision=0,
        expected_review_revision=0,
        request_id="human-review-pw02",
        reason="Peer review taxonomy refinement",
        actor="lead-researcher",
        theme=corrected,
    )
    assert applied["revision"] == 1

    # 3. Candidate proposals re-queried: candidate status preserved, applied_merges stays 0
    updated_proposals = index.candidate_relations(min_similarity=0.0)
    assert updated_proposals["applied_merges"] == 0
    # Verified: human correction preserves candidate proposal fence
    for item in updated_proposals["items"]:
        assert item["status"] == "CANDIDATE"
        assert item["relation"] == "UNRESOLVED_SIMILARITY"


# PW03: L1–L4 Skeleton Views + Evidence Archive Export
def test_pw03_l1_to_l4_skeleton_views_and_evidence_archive(catalog_sandbox, tmp_path):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    paper_id = "paper_dd83af8026e3"

    # 1. Populate genuine L1–L4 skeleton units
    skel = populate_skeleton_l1_to_l4(
        root,
        paper_id=paper_id,
        propositions=[
            {"atom_id": f"{paper_id}-a1", "statement": "Settlement throughput reaches 2500 tps.", "quote": "2500 tps", "source_span": [5, 13]},
        ],
        relations=[{"source_atom": f"{paper_id}-a1", "target_atom": f"{paper_id}-a1", "relation_type": "SELF_REINFORCING"}],
        intents=[{"atom_id": f"{paper_id}-a1", "primary": "Objective_Finding", "secondary": [], "rationale": "Throughput benchmark."}],
        macro_role="Result_Performance",
    )

    # 2. Package into evidence archive
    archive_path = tmp_path / "archives" / "archive_with_skeleton.zip"
    archive_res = create_sealed_evidence_archive(root, archive_path)
    assert archive_res["archive_path"].exists()

    # 3. Read back archive in isolated directory and verify L1-L4 integrity
    extract_dir = tmp_path / "extracted_verify"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(extract_dir)

    extracted_db = extract_dir / "catalog.db"
    assert extracted_db.exists()
    with transaction(extracted_db) as conn:
        row = conn.execute("SELECT * FROM skeleton_units WHERE unit_id=?", (skel["unit_id"],)).fetchone()
        assert row is not None
        assert json.loads(row["layer1_json"]) == skel["layer1"]
        assert json.loads(row["layer2_json"]) == skel["layer2"]
        assert json.loads(row["layer3_json"]) == skel["layer3"]
        assert row["layer4"] == "Result_Performance"


# PW04: Relocated Sources + Target Adoption Rollback
def test_pw04_relocated_sources_and_target_adoption_rollback(catalog_sandbox, tmp_path):
    source_db = catalog_sandbox["db_path"]
    paper_id = "paper_dd83af8026e3"

    # 1. Relocate PDF file
    relocated_dir = tmp_path / "relocated_vault"
    relocated_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = catalog_sandbox["p1"]["pdf_path"]
    relocated_pdf = relocated_dir / orig_pdf.name
    relocated_pdf.write_bytes(orig_pdf.read_bytes())

    with transaction(source_db) as conn:
        conn.execute("UPDATE source_file_versions SET storage_path=? WHERE paper_id=?", (str(relocated_pdf), paper_id))
        verified = require_pdf_source(conn, f"{paper_id}-file", paper_id)
        assert verified["storage_path"] == str(relocated_pdf)

    # 2. Target database with pre-existing records
    target_dir = tmp_path / "target_reloc_owner" / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "catalog.db"
    initialize_catalog(target_db)

    with transaction(target_db) as conn:
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, title, normalized_title, authors_json, created_at, updated_at)
               VALUES ('target-pre1', 'target-pre1', 'Target Pre Paper', 'target pre paper', '[]', '2026-11-04', '2026-11-04')"""
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES ('intent-pw04', 'target-pre1', 'v1', 'ACTIVE', 0, 1, '2026-11-04', '2026-11-04')"""
        )

    # 3. Adopt history
    record = {
        "operation": adoption.ADOPT,
        "request_id": "adopt-pw04",
        "reason": "Relocated source adoption test",
        "authority": "CONTROLLER",
        "target_database": str(target_db.resolve()),
        "source_database": str(source_db.resolve()),
        "intent_id": "intent-pw04",
        "packet_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    def target_conn():
        c = sqlite3.connect(target_db)
        c.row_factory = sqlite3.Row
        return c

    with closing(target_conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        adoption.record_adoption(t_conn, admission)
        t_conn.commit()

    # 4. Rollback via compensating reversal
    with closing(target_conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        rev = adoption.reverse_adoption(t_conn, "adopt-pw04", request_id="rev-pw04", reason="Compensating rollback")
        t_conn.commit()
        assert "catalog_reading_requests" in rev

    # Verify target's native records survived completely
    with closing(target_conn()) as t_conn:
        native = t_conn.execute("SELECT * FROM papers WHERE paper_id='target-pre1'").fetchone()
        assert native is not None


# PW05: Freshness Invalidation + Night Window Batch Reindexing
def test_pw05_source_freshness_invalidation_and_night_window_reindexing(catalog_sandbox, monkeypatch):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # Invalidate by changing source generation
    embedder.generation = "gen-pw05-new"

    # Daytime simulation: automatic batch yields / waits for night window
    monkeypatch.setattr(retrieval, "night_window_open", lambda: False)
    day_status = index.refresh_batch(manual_requested=False)
    assert day_status["status"] == "WAITING_FOR_NIGHT_OR_FOREGROUND"

    # Night window opens: automatic batch executes and updates index
    monkeypatch.setattr(retrieval, "night_window_open", lambda: True)
    night_status = index.refresh_batch(manual_requested=False)
    assert night_status["status"] == "CURRENT"
    assert night_status["embedded"] > 0


# PW06: FastMCP Tools + Candidate Relation Streaming
def test_pw06_fastmcp_tools_and_candidate_relation_streaming(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # Query relations via candidate index
    candidates = index.candidate_relations(min_similarity=0.0)
    assert "items" in candidates

    # Pass through tool bounds
    bounded_candidates = tools.bounded_result(candidates, candidates=True)
    assert len(encoded(bounded_candidates)) <= MAX_RESPONSE_CHARACTERS
    assert bounded_candidates.get("applied_merges", 0) == 0


# PW07: Decoupled Purpose Judgments + Target Adoption
def test_pw07_decoupled_purpose_judgments_and_target_adoption(catalog_sandbox, tmp_path):
    root = catalog_sandbox["root"]
    source_db = catalog_sandbox["db_path"]
    store = CatalogUnderstanding(root)
    paper_id = "paper_dd83af8026e3"

    # Purpose 1: Overview
    card1 = default_card()
    for t in card1["themes"]:
        t["evidence"][0]["block_id"] = f"{paper_id}-b1"
    card1["disposition_rationale"] = "Initial overview of microgrid literature."
    store.publish_initial(
        paper_id=paper_id,
        parse_run_id=f"{paper_id}-parse",
        card=card1,
        contract={"prompt_version": "quick-read-v2-paperskeleton", "actual_model": "software-fixture"},
        publication_key=f"{paper_id}-purp-pw07-1",
        purpose={"kind": "OVERVIEW"},
    )

    # Purpose 2: Protocol Security
    card2 = default_card()
    for t in card2["themes"]:
        t["evidence"][0]["block_id"] = f"{paper_id}-b1"
    card2["disposition_rationale"] = "Protocol security assessment of consensus mechanism."
    store.publish_initial(
        paper_id=paper_id,
        parse_run_id=f"{paper_id}-parse",
        card=card2,
        contract={"prompt_version": "quick-read-v2-paperskeleton", "actual_model": "software-fixture"},
        publication_key=f"{paper_id}-purp-pw07-2",
        purpose={"kind": "SECURITY_AUDIT"},
    )

    paper = store.paper(paper_id)
    assert len(paper["judgments"]) >= 2

    # Target database adopting this state
    target_dir = tmp_path / "target_pw07" / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "catalog.db"
    initialize_catalog(target_db)

    with transaction(target_db) as conn:
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, title, normalized_title, authors_json, created_at, updated_at)
               VALUES ('target-pw07', 'target-pw07', 'Target Paper', 'target paper', '[]', '2026-11-04', '2026-11-04')"""
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES ('intent-pw07', 'target-pw07', 'v1', 'ACTIVE', 0, 1, '2026-11-04', '2026-11-04')"""
        )

    record = {
        "operation": adoption.ADOPT,
        "request_id": "adopt-pw07",
        "reason": "Adoption with multiple decoupled judgments",
        "authority": "CONTROLLER",
        "target_database": str(target_db.resolve()),
        "source_database": str(source_db.resolve()),
        "intent_id": "intent-pw07",
        "packet_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    with closing(sqlite3.connect(target_db)) as t_conn:
        t_conn.row_factory = sqlite3.Row
        t_conn.execute("BEGIN IMMEDIATE")
        adoption.record_adoption(t_conn, admission)
        t_conn.commit()

        # Target paper and intents preserved
        native = t_conn.execute("SELECT * FROM papers WHERE paper_id='target-pw07'").fetchone()
        assert native is not None
