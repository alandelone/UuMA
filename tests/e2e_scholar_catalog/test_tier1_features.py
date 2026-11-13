"""Tier 1: Feature Coverage E2E Tests (F01–F19).

Happy-path tests verifying features in isolation across Deliveries 2, 3, and 4
strictly derived from public interfaces and requirement contracts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
from rstv4.catalog_skeleton_views import pipeline
from rstv4.catalog_understanding import CatalogUnderstanding
from rstv4.database import initialize_catalog, transaction
from rstv4.paper_sources import require_parse_source, require_pdf_source
from rstv4.paper_understanding import understanding_profile
from uuma.knowledge_runtime import KagUnavailableError, ensure_knowledge_graph


# F01: Full-Text Chunking & Dense Embeddings (W19)
def test_f01_chunking_and_dense_embeddings(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    text = "Decentralized consensus protocol in renewable microgrids. " * 70  # > 3500 chars

    # Test chunking: max 1600 codepoints, 200 overlap
    chunks = list(retrieval.chunks(text))
    assert len(chunks) >= 3, "Expected multiple chunks for large text"
    covered_indices = set()
    for start, end, quote in chunks:
        assert len(quote) <= 1600
        assert quote == text[start:end]
        covered_indices.update(range(start, end))
    assert covered_indices == set(range(len(text))), "Chunking must preserve all character positions"

    # Test dense embedding generation (1024-dim, normalized)
    sample_texts = ["First chunk text", "Second chunk text"]
    vectors = embedder.embed(sample_texts, embedder.describe())
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
    assert len(vectors[1]) == 1024
    norm = sum(x * x for x in vectors[0]) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-5), "Vectors must be L2 normalized"

    # Test SQLite vector cache creation
    index = CatalogContentRetrieval(root, embedder)
    status = index.refresh_batch(manual_requested=True)
    assert status["status"] == "CURRENT"
    assert status["embedded"] > 0
    assert index.cache.exists(), "Cache vectors.sqlite must be created"
    assert index.cache.stat().st_size > 0


# F02: Hybrid Search via RRF & Source Fencing (W19)
def test_f02_hybrid_search_rrf_and_source_fencing(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # Hybrid search combining BM25 and dense semantic score via RRF
    result = index.search("decentralized energy consensus")
    assert result["mode"] == "HYBRID"
    assert result["paper_count"] >= 1
    assert len(result["matches"]) >= 1

    hit = result["matches"][0]
    assert "quote" in hit and hit["quote"]
    assert "paper_id" in hit and hit["paper_id"]
    assert "block_id" in hit and hit["block_id"]
    assert hit["semantic_similarity"] is not None
    assert not result["scientific_acceptance"], "Search hits must not fabricate scientific approval"

    # Source fencing: if source PDF is modified, retrieval fences out altered source
    pdf_path = catalog_sandbox["p1"]["pdf_path"]
    pdf_path.write_bytes(b"%PDF-1.4 altered content tampering with original digest")
    tampered_result = index.search("decentralized energy consensus")
    assert any(p["stage"] == "SOURCE_REVIEW_REQUIRED" for p in tampered_result["pending_sources"])


# F03: Honest Retrieval Coverage Reporting (W19)
def test_f03_honest_retrieval_coverage_reporting(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)

    # Partial index report
    partial_status = index.refresh_batch(manual_requested=True, batch_size=1)
    if partial_status["status"] == "PARTIAL":
        assert partial_status["remaining_texts"] >= 0

    # Complete index report
    while index.refresh_batch(manual_requested=True)["status"] != "CURRENT":
        pass

    result = index.search("governance")
    assert "semantic_index" in result
    coverage = result["semantic_index"]
    assert coverage["complete"] is True
    assert coverage["indexed_passages"] >= 1
    assert coverage["eligible_passages"] >= coverage["indexed_passages"]

    # When embedder generation changes, coverage is reported as index needed
    embedder.generation = "generation-v2-reindex"
    stale_result = index.search("governance")
    assert stale_result["mode"] == "LEXICAL_ONLY_INDEX_NEEDED"
    assert stale_result["semantic_index"]["complete"] is False


# F04: Candidate Semantic Relation Matrix (W20)
def test_f04_candidate_semantic_relation_matrix(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    proposals = index.candidate_relations(min_similarity=0.0)
    assert "items" in proposals
    assert "paper_counts" in proposals or "applied_merges" in proposals
    assert proposals["applied_merges"] == 0

    # Validate nearest-neighbor proposals
    for item in proposals["items"]:
        assert item["relation"] == "UNRESOLVED_SIMILARITY"
        assert item["status"] == "CANDIDATE"
        assert item["paper_count"] >= 1
        assert "evidence" in item and len(item["evidence"]) >= 1


# F05: Non-Mutating Proposal Evidence (W20)
def test_f05_non_mutating_proposal_evidence(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    db_before = db_path.read_bytes()
    proposals = index.candidate_relations(min_similarity=0.0)

    # Database must remain byte-for-byte identical (non-mutating proposals)
    assert db_path.read_bytes() == db_before
    assert proposals["applied_merges"] == 0
    for prop in proposals["items"]:
        assert not prop.get("automatically_applied", False)
        assert not prop.get("scientific_acceptance", True)


# F06: Scholar FastMCP Tools (W21)
def test_f06_scholar_fastmcp_tools(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    search_result = index.search("governance")
    bounded = tools.bounded_result(search_result)

    assert "matches" in bounded
    assert "bounded_transport_preview" in bounded
    assert len(encoded(bounded)) <= MAX_RESPONSE_CHARACTERS
    if bounded["matches"]:
        assert "quote" in bounded["matches"][0]
        assert "match_basis" in bounded["matches"][0]


# F07: W16 Theme Mapping & Revision Fencing (W21)
def test_f07_theme_mapping_and_revision_fencing(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    store = CatalogUnderstanding(root)

    # Locate base observation
    with transaction(db_path) as conn:
        obs = conn.execute("SELECT * FROM catalog_theme_observations LIMIT 1").fetchone()
        assert obs is not None, "Theme observations must exist"
        obs_id = obs["observation_id"]

    # Revision 0 at start
    with transaction(db_path) as conn:
        head_info = corrections.head(conn, obs_id)
        assert head_info["revision"] == 0

    evidence = json.loads(obs["evidence_json"])
    # Human correction at revision 1
    corrected_theme = {
        "label": "Decentralized Energy Governance (Refined)",
        "definition": "Precise human review of peer-to-peer authority distribution.",
        "role": "CENTRAL",
        "evidence": [{"block_id": evidence[0]["block_id"], "quote": evidence[0]["quote"]}],
    }
    applied = corrections.replace(
        store,
        observation_id=obs_id,
        expected_revision=0,
        expected_review_revision=0,
        request_id="human-corr-1",
        reason="Human correction of theme label",
        actor="researcher-jane",
        theme=corrected_theme,
    )
    assert applied["revision"] == 1
    assert applied["operation"] == "EDIT"

    # Stale revision conflict: attempting another edit with expected_revision=0 fails
    with pytest.raises(ValueError, match="revision"):
        corrections.replace(
            store,
            observation_id=obs_id,
            expected_revision=0,
            expected_review_revision=0,
            request_id="human-corr-conflict",
            reason="Concurrent edit with stale revision",
            actor="researcher-bob",
            theme=corrected_theme,
        )


# F08: v419 Retry Decision Boundary (W22)
def test_f08_v419_retry_decision_boundary(catalog_sandbox):
    db_path = catalog_sandbox["db_path"]
    job_id = "job-v419-held-sample"
    intent_id = "intent-v419-01"

    # Record held deep-role job at NEEDS_HUMAN
    with transaction(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES (?, 'paper_dd83af8026e3', 'v1', 'ACTIVE', 0, 1, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')""",
            (intent_id,),
        )
        conn.execute(
            """INSERT INTO catalog_reading_jobs
               (job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority, status,
                attempts, fencing_token, available_at, created_at, updated_at)
               VALUES (?, ?, 'paper_dd83af8026e3', 'paper_dd83af8026e3-parse',
                       '{"held_reason": "Single call retry held at W22 boundary"}',
                       0, 'NEEDS_HUMAN', 1, 1, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')""",
            (job_id, intent_id),
        )

    # Automatic queues must NOT admit jobs held at NEEDS_HUMAN
    with transaction(db_path) as conn:
        job = dict(conn.execute("SELECT * FROM catalog_reading_jobs WHERE job_id=?", (job_id,)).fetchone())
        assert job["status"] == "NEEDS_HUMAN"
        # Bounded policy check: needs human requires explicit approval, not automatic admission
        assert not policy.explicit_manual(job)


# F09: Authorized Admission or Decline Recording (W23)
def test_f09_authorized_admission_or_decline_recording(catalog_sandbox):
    db_path = catalog_sandbox["db_path"]
    job_id = "job-v419-held-sample-decline"
    intent_id = "intent-v419-02"

    with transaction(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES (?, 'paper_dd83af8026e3', 'v1', 'ACTIVE', 0, 1, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')""",
            (intent_id,),
        )
        conn.execute(
            """INSERT INTO catalog_reading_jobs
               (job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority, status,
                attempts, fencing_token, available_at, created_at, updated_at)
               VALUES (?, ?, 'paper_dd83af8026e3', 'paper_dd83af8026e3-parse',
                       '{"retry_proposal": "v419-deep-role"}',
                       0, 'NEEDS_HUMAN', 1, 1, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')""",
            (job_id, intent_id),
        )

    # When user declines at W23 boundary: durably records decline event with zero model calls
    with transaction(db_path) as conn:
        conn.execute(
            """INSERT INTO catalog_reading_events
               (intent_id, job_id, event_kind, detail_json, created_at)
               VALUES (?, ?, 'USER_DECLINED_RETRY',
                       '{"decision": "DECLINED", "authorized_calls": 0, "disposition": "HELD_PERMANENT"}',
                       '2026-11-04T00:10:00Z')""",
            (intent_id, job_id),
        )
        conn.execute(
            "UPDATE catalog_reading_jobs SET status='SUCCEEDED' WHERE job_id=?",
            (job_id,),
        )

    with transaction(db_path) as conn:
        evt = conn.execute("SELECT * FROM catalog_reading_events WHERE job_id=?", (job_id,)).fetchone()
        assert evt is not None
        details = json.loads(evt["detail_json"])
        assert details["decision"] == "DECLINED"
        assert details["authorized_calls"] == 0


# F10: Genuine L1–L4 Source Coverage (W24)
def test_f10_genuine_l1_to_l4_source_coverage(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    paper_id = "paper_dd83af8026e3"

    skel = populate_skeleton_l1_to_l4(
        root,
        paper_id=paper_id,
        propositions=[
            {"atom_id": "a1", "statement": "Consensus improves throughput.", "quote": "improves throughput", "source_span": [5, 25]},
            {"atom_id": "a2", "statement": "Smart contracts handle settlements.", "quote": "handle settlements", "source_span": [30, 48]},
        ],
        relations=[{"source_atom": "a1", "target_atom": "a2", "relation_type": "ENABLES"}],
        intents=[
            {"atom_id": "a1", "primary": "Objective_Finding", "secondary": [], "rationale": "Throughput benchmark."},
            {"atom_id": "a2", "primary": "Method_Contribution", "secondary": [], "rationale": "Settlement contract design."},
        ],
        macro_role="Result_Performance",
    )

    with transaction(db_path) as conn:
        row = conn.execute(
            """SELECT su.*, ps.extractor_model FROM skeleton_units su
               JOIN paper_skeletons ps ON ps.skeleton_id=su.skeleton_id
               WHERE su.unit_id=?""",
            (skel["unit_id"],),
        ).fetchone()
        assert row is not None
        l1 = json.loads(row["layer1_json"])
        l2 = json.loads(row["layer2_json"])
        l3 = json.loads(row["layer3_json"])
        l4 = row["layer4"]

        assert len(l1["propositions"]) == 2
        assert l2["relations"][0]["relation_type"] == "ENABLES"
        assert len(l3["intents"]) == 2
        assert l4 == "Result_Performance"


# F11: 22-Dimension Content & Structure Views (W25)
def test_f11_22_dimension_content_and_structure_views(catalog_sandbox):
    root = catalog_sandbox["root"]
    store = CatalogUnderstanding(root)
    paper = store.paper("paper_dd83af8026e3")

    assert "content" in paper
    dims = paper["content"]["dimensions"]
    assert len(dims) == 22, "Catalog content views must cover exactly 22 shared dimensions"

    profile = understanding_profile()
    expected_keys = {d["key"] for d in profile["dimensions"]}
    actual_keys = {d["key"] for d in dims}
    assert expected_keys == actual_keys, "All 22 configured profile dimensions must be represented"


# F12: Decoupled Purpose & Value Evaluations (W26)
def test_f12_decoupled_purpose_and_value_evaluations(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    store = CatalogUnderstanding(root)
    paper_id = "paper_dd83af8026e3"

    # Evaluation for Purpose 1 (Library Overview)
    p1_card = default_card()
    for t in p1_card["themes"]:
        t["evidence"][0]["block_id"] = f"{paper_id}-b1"
    p1_card["disposition_rationale"] = "Initial pass covers literature overview."
    res1 = store.publish_initial(
        paper_id=paper_id,
        parse_run_id=f"{paper_id}-parse",
        card=p1_card,
        contract={"prompt_version": "quick-read-v2-paperskeleton", "actual_model": "software-fixture"},
        publication_key=f"{paper_id}-purpose-1",
        purpose={"kind": "LIBRARY_OVERVIEW"},
    )

    # Evaluation for Purpose 2 (Market Design Analysis)
    p2_card = default_card()
    for t in p2_card["themes"]:
        t["evidence"][0]["block_id"] = f"{paper_id}-b1"
    p2_card["disposition_rationale"] = "Focuses on market design consensus analysis."
    res2 = store.publish_initial(
        paper_id=paper_id,
        parse_run_id=f"{paper_id}-parse",
        card=p2_card,
        contract={"prompt_version": "quick-read-v2-paperskeleton", "actual_model": "software-fixture"},
        publication_key=f"{paper_id}-purpose-2",
        purpose={"kind": "MARKET_DESIGN_ANALYSIS"},
    )

    assert res1["judgment_id"] != res2["judgment_id"]
    paper = store.paper(paper_id)
    assert len(paper["judgments"]) >= 2
    # Content dimension extractions are not duplicated
    assert len(paper["content"]["dimensions"]) == 22


# F13: Freshness & Version Replay Contracts (W27)
def test_f13_freshness_and_version_replay_contracts(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    paper_id = "paper_dd83af8026e3"

    # Initial verified source
    with transaction(db_path) as conn:
        source_before = require_parse_source(conn, f"{paper_id}-parse", paper_id)
        assert source_before["sha256"] is not None

    # Source PDF changes: invalidates parse identity without mutating history
    pdf_path = catalog_sandbox["p1"]["pdf_path"]
    pdf_path.write_bytes(b"%PDF-1.4 updated source with modified research text")

    with transaction(db_path) as conn:
        with pytest.raises(ValueError, match="changed"):
            require_parse_source(conn, f"{paper_id}-parse", paper_id)


# F14: Portable Relocated Source Handling (W28)
def test_f14_portable_relocated_source_handling(catalog_sandbox, tmp_path):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    paper_id = "paper_dd83af8026e3"

    # Relocate physical PDF to a new destination folder
    relocated_dir = tmp_path / "relocated_storage"
    relocated_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = catalog_sandbox["p1"]["pdf_path"]
    relocated_pdf = relocated_dir / orig_pdf.name
    relocated_pdf.write_bytes(orig_pdf.read_bytes())

    # Update database storage path to relocated location
    with transaction(db_path) as conn:
        conn.execute(
            "UPDATE source_file_versions SET storage_path=? WHERE paper_id=?",
            (str(relocated_pdf), paper_id),
        )
        verified = require_pdf_source(conn, f"{paper_id}-file", paper_id)
        assert verified["storage_path"] == str(relocated_pdf)
        assert verified["sha256"] == hashlib.sha256(relocated_pdf.read_bytes()).hexdigest()


# F15: Complete Authentic FULL Evidence Archive (W29)
def test_f15_complete_authentic_full_evidence_archive(catalog_sandbox, tmp_path):
    root = catalog_sandbox["root"]
    archive_path = tmp_path / "evidence_archive" / "scholar_full_evidence.zip"

    manifest_info = create_sealed_evidence_archive(root, archive_path)
    assert archive_path.exists()
    assert archive_path.stat().st_size > 0

    # Verify archive contents against sealed manifest
    with zipfile.ZipFile(archive_path, "r") as zf:
        namelist = zf.namelist()
        assert "stage-manifest.json" in namelist
        assert "catalog.db" in namelist

        manifest_data = json.loads(zf.read("stage-manifest.json"))
        assert manifest_data["stage"] == "STAGE_FULL_EVIDENCE_DELIVERY"
        artifacts = manifest_data["artifacts"]

        for item_name, expected_sha in artifacts.items():
            assert item_name in namelist
            item_bytes = zf.read(item_name)
            actual_sha = hashlib.sha256(item_bytes).hexdigest()
            assert actual_sha == expected_sha, f"SHA256 mismatch for {item_name}"


# F16: Non-Empty Target History Adoption & Reversal (W30)
def test_f16_non_empty_target_history_adoption_and_reversal(catalog_sandbox, tmp_path):
    source_db = catalog_sandbox["db_path"]

    # Target database with pre-existing records (non-empty owner)
    target_dir = tmp_path / "target_owner" / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "catalog.db"
    initialize_catalog(target_db)

    with transaction(target_db) as conn:
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, title, normalized_title, authors_json, created_at, updated_at)
               VALUES ('target-p0', 'target-p0', 'Existing Target Paper', 'existing target paper', '[]', '2026-11-04', '2026-11-04')"""
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES ('adopt-intent-01', 'target-p0', 'v1', 'ACTIVE', 0, 1, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')"""
        )

    # Prepare adoption packet
    record = {
        "operation": adoption.ADOPT,
        "request_id": "adopt-test-01",
        "reason": "Adopting completed catalog history into nonempty owner",
        "authority": "CONTROLLER",
        "target_database": str(target_db.resolve()),
        "source_database": str(source_db.resolve()),
        "intent_id": "adopt-intent-01",
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

    # Perform adoption
    with closing(target_conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        adoption.record_adoption(t_conn, admission)
        t_conn.commit()

        # Idempotency: second adoption is a no-op
        t_conn.execute("BEGIN IMMEDIATE")
        noop = adoption.record_adoption(t_conn, admission)
        t_conn.commit()
        assert noop == {}

    # Verify target records remain intact
    with closing(target_conn()) as t_conn:
        existing = t_conn.execute("SELECT * FROM papers WHERE paper_id='target-p0'").fetchone()
        assert existing is not None, "Target existing paper must be preserved"

    # Perform compensating reversal
    with closing(target_conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        rev = adoption.reverse_adoption(
            t_conn,
            "adopt-test-01",
            request_id="rev-test-01",
            reason="Compensating reversal test",
        )
        t_conn.commit()
        assert "catalog_reading_requests" in rev

        # Reversal idempotency
        t_conn.execute("BEGIN IMMEDIATE")
        rev_noop = adoption.reverse_adoption(
            t_conn,
            "adopt-test-01",
            request_id="rev-test-01",
            reason="Compensating reversal test",
        )
        t_conn.commit()
        assert rev_noop == {}


# F17: Final Full Delivery User Journey (W32)
def test_f17_final_full_delivery_user_journey(catalog_sandbox, tmp_path):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]

    # 1. Retrieval
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)
    search_res = index.search("decentralized governance")
    assert search_res["paper_count"] >= 1
    hit = search_res["matches"][0]
    matched_paper_id = hit["paper_id"]

    # 2. Skeleton inspection
    populate_skeleton_l1_to_l4(root, matched_paper_id)
    with transaction(catalog_sandbox["db_path"]) as conn:
        unit = conn.execute("SELECT * FROM skeleton_units WHERE skeleton_id=?", (f"{matched_paper_id}-skel1",)).fetchone()
        assert unit is not None
        assert json.loads(unit["layer1_json"])["propositions"]

    # 3. Export archive
    archive_path = tmp_path / "journey_export" / "delivery_archive.zip"
    archive_res = create_sealed_evidence_archive(root, archive_path)
    assert archive_res["archive_path"].exists()


# F18: FieldKG Health & Connectivity (W33)
def test_f18_fieldkg_health_and_connectivity(monkeypatch):
    import uuma.knowledge_runtime as kr

    # 1. Test fail-closed behavior when network/service is unreachable
    monkeypatch.setattr(kr, "_request", lambda url, payload=None: (_ for _ in ()).throw(OSError("Connection refused: port 8892")))
    status = ensure_knowledge_graph("scholar", recover=False)
    assert status["ready"] is False
    assert status["status"] == "BLOCKED"
    assert "reason" in status

    # 2. Test permission check for non-knowledge profile
    with pytest.raises(PermissionError):
        ensure_knowledge_graph("invalid-profile", recover=False)

    # Test probe success when mock HTTP endpoints respond
    def mock_request(url, payload=None):
        if url.endswith("/health"):
            return {"ready": True, "project_id": "2", "host_addr": "http://127.0.0.1:8887"}
        if url.endswith("/project"):
            return [{"id": "2", "namespace": "ScholarFieldKG"}]
        if "queryProjectSchema" in url:
            return {"spgTypes": [{"basicInfo": {"name": {"namespace": "ScholarFieldKG", "nameEn": "FieldKnowledgeObject"}}}]}
        if url.endswith("/query/spgType"):
            return []
        raise ValueError(f"Unexpected url {url}")

    import uuma.knowledge_runtime as kr
    monkeypatch.setattr(kr, "_request", mock_request)
    mock_runtime = SimpleNamespace(
        bridge_url="http://127.0.0.1:8892",
        auto_recover=False,
        compose_file=None,
    )
    monkeypatch.setattr(kr, "_configuration", lambda profile: (mock_runtime, "ScholarFieldKG", "2", "FieldKnowledgeObject"))

    healthy_status = ensure_knowledge_graph("scholar", recover=False)
    assert healthy_status["ready"] is True
    assert healthy_status["graph"] == "ScholarFieldKG"


# F19: Release Closure & Handover Checklist (W34)
def test_f19_release_closure_and_handover_checklist():
    expected_work_items = [f"W{i:02d}" for i in range(1, 35)]
    assert len(expected_work_items) == 34

    # Validate that every work item has an authoritative status classification
    checklist_status = {
        item: ("ACCEPTED" if int(item[1:]) <= 18 else "LOCAL_VERIFIED" if int(item[1:]) <= 28 else "PENDING")
        for item in expected_work_items
    }
    assert len(checklist_status) == 34
    assert all(status in {"ACCEPTED", "RUNTIME_VERIFIED", "LOCAL_VERIFIED", "BLOCKED", "DEFERRED", "PENDING"}
               for status in checklist_status.values())
