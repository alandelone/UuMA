"""Tests for Canonical Semantic Database (librarian_semantic.db)."""

import sqlite3
from pathlib import Path

import pytest

from uuma.librarian_semantic_db import (
    get_evidence_for_record,
    get_record,
    init_semantic_db,
    insert_entity,
    insert_episode,
    insert_evidence,
    insert_record,
    insert_relation,
    insert_source,
    insert_source_object,
    search_records,
)


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_semantic.db"
    conn = init_semantic_db(db_file)
    # Register test sources
    insert_source(
        conn,
        source_id="test-source",
        device="server",
        category_default="Knowledge",
        privacy_tier="internal",
    )
    insert_source(
        conn,
        source_id="yonc-graph",
        device="server",
        category_default="Decision",
        privacy_tier="internal",
    )
    return conn


def test_init_and_tables_exist(db_conn: sqlite3.Connection) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    expected_tables = {
        "sources",
        "source_objects",
        "episodes",
        "records",
        "evidence_links",
        "entities",
        "relations",
        "extraction_runs",
        "fts_records",
    }
    assert expected_tables.issubset(tables)


def test_foreign_key_enforcement(db_conn: sqlite3.Connection) -> None:
    # Inserting record with nonexistent source_id should fail
    with pytest.raises(sqlite3.IntegrityError):
        insert_record(
            db_conn,
            record_id="rec_invalid",
            source_id="nonexistent-source",
            category="Knowledge",
            title="Invalid",
            summary="Invalid",
            full_content="Invalid",
        )


def test_category_and_status_constraints(db_conn: sqlite3.Connection) -> None:
    # Invalid category
    with pytest.raises(sqlite3.IntegrityError):
        insert_record(
            db_conn,
            record_id="rec_bad_cat",
            source_id="test-source",
            category="NonexistentCategory",
            title="Bad",
            summary="Bad",
            full_content="Bad",
        )

    # Invalid assertion status
    with pytest.raises(sqlite3.IntegrityError):
        insert_record(
            db_conn,
            record_id="rec_bad_status",
            source_id="test-source",
            category="Knowledge",
            title="Bad",
            summary="Bad",
            full_content="Bad",
            assertion_status="invented_status",
        )


def test_record_lifecycle_and_evidence(db_conn: sqlite3.Connection) -> None:
    insert_source_object(
        db_conn,
        object_id="obj_001",
        source_id="test-source",
        object_uri="transcripts/turn_1.jsonl",
        content_hash="abc123sha256",
        byte_size=1024,
    )
    insert_episode(
        db_conn,
        episode_id="ep_001",
        source_id="test-source",
        object_id="obj_001",
        title="Episode 1",
    )
    insert_record(
        db_conn,
        record_id="rec_001",
        source_id="test-source",
        category="Decision",
        project="UuMA",
        title="Architecture Decision",
        summary="Adopted LSIP for Librarian",
        full_content="We decided to adopt LSIP architecture for unified semantic catalog.",
        episode_id="ep_001",
        assertion_status="confirmed",
    )
    insert_evidence(
        db_conn,
        evidence_id="evi_001",
        record_id="rec_001",
        object_id="obj_001",
        locator_type="jsonl_line",
        locator_value="line:42",
        exact_quote="We decided to adopt LSIP architecture for unified semantic catalog.",
    )

    rec = get_record(db_conn, "rec_001")
    assert rec is not None
    assert rec["record_id"] == "rec_001"
    assert rec["project"] == "UuMA"
    assert rec["assertion_status"] == "confirmed"

    evidence = get_evidence_for_record(db_conn, "rec_001")
    assert len(evidence) == 1
    assert evidence[0]["evidence_id"] == "evi_001"
    assert evidence[0]["locator_value"] == "line:42"
    assert evidence[0]["verified"] is True

    # Cascade delete verification
    db_conn.execute("DELETE FROM records WHERE record_id = 'rec_001'")
    db_conn.commit()
    assert get_record(db_conn, "rec_001") is None
    assert len(get_evidence_for_record(db_conn, "rec_001")) == 0


def test_fts5_search(db_conn: sqlite3.Connection) -> None:
    insert_record(
        db_conn,
        record_id="rec_fts_1",
        source_id="yonc-graph",
        category="Decision",
        project="yonc-graph",
        title="Quantum Storage Engine",
        summary="Switched graph backend to SQLite WAL mode",
        full_content="The graph store migrated to WAL mode for concurrent multi-agent access.",
    )
    insert_record(
        db_conn,
        record_id="rec_fts_2",
        source_id="test-source",
        category="Knowledge",
        project="UuMA",
        title="Agent Collaboration Protocol",
        summary="A2A message format definition",
        full_content="A2A protocol uses governed token authentication.",
    )

    # Search for WAL
    results = search_records(db_conn, "WAL")
    assert len(results) == 1
    assert results[0]["record_id"] == "rec_fts_1"

    # Search with project filter
    results_uuma = search_records(db_conn, "protocol", project="UuMA")
    assert len(results_uuma) == 1
    assert results_uuma[0]["record_id"] == "rec_fts_2"

    # Search without results
    results_empty = search_records(db_conn, "NonexistentSearchTermXYZ")
    assert len(results_empty) == 0


def test_entities_and_relations(db_conn: sqlite3.Connection) -> None:
    insert_entity(
        db_conn,
        entity_id="agent:librarian",
        entity_type="agent",
        name="Librarian",
        description="Knowledge and archive keeper",
    )
    insert_entity(
        db_conn,
        entity_id="project:uuma",
        entity_type="project",
        name="UuMA",
    )
    insert_relation(
        db_conn,
        relation_id="rel_001",
        subject_id="agent:librarian",
        subject_type="entity",
        predicate="manages",
        object_id="project:uuma",
        object_type="entity",
    )

    cursor = db_conn.cursor()
    cursor.execute("SELECT predicate FROM relations WHERE relation_id = 'rel_001'")
    assert cursor.fetchone()[0] == "manages"


def test_migrate_from_catalog(db_conn: sqlite3.Connection) -> None:
    from uuma.librarian_semantic_db import migrate_from_catalog

    fake_catalog = {
        "schema_version": 1,
        "snapshot_id": "snap-20261112",
        "published_at": "2026-11-12T00:00:00+08:00",
        "sources": [
            {
                "source_id": "yonc-graph",
                "owner_agent": "yonc",
                "readers": ["yonc", "librarian"],
                "capture_status": "COMPLETE",
            },
            {
                "source_id": "brainstormer-index",
                "owner_agent": "brainstormer",
                "readers": ["brainstormer", "librarian"],
                "capture_status": "COMPLETE",
            },
        ],
        "records": [
            {
                "record_id": "yonc-project-index:p_001",
                "version_id": "v1",
                "source_id": "yonc-graph",
                "readers": ["yonc", "librarian"],
                "project_ids": ["project_alpha"],
                "kind": "structural-index",
                "title": "Yonc project structural index: Alpha",
                "original_status": "DONE",
                "original_ref": "sqlite:yonc_graph:p_001",
                "captured_at": "2026-11-12T00:00:00+08:00",
                "content_sha256": "1" * 64,
                "content_bytes": 512,
            },
            {
                "record_id": "brainstormer-topic-index:topic_onion",
                "version_id": "v1",
                "source_id": "brainstormer-index",
                "readers": ["brainstormer", "librarian"],
                "project_ids": ["onion_project"],
                "kind": "structural-index",
                "title": "Brainstormer topic structural index: Onion",
                "original_status": "ACTIVE",
                "original_ref": "state:topic_onion",
                "captured_at": "2026-11-12T00:00:00+08:00",
                "content_sha256": "2" * 64,
                "content_bytes": 1024,
            },
        ],
    }

    count = migrate_from_catalog(db_conn, fake_catalog)
    assert count == 2

    # Verify migrated records
    rec1 = get_record(db_conn, "yonc-project-index:p_001")
    assert rec1 is not None
    assert rec1["category"] == "Decision"
    assert rec1["project"] == "project_alpha"
    assert rec1["assertion_status"] == "confirmed"

    evi1 = get_evidence_for_record(db_conn, "yonc-project-index:p_001")
    assert len(evi1) == 1
    assert evi1[0]["object_uri"] == "sqlite:yonc_graph:p_001"

    rec2 = get_record(db_conn, "brainstormer-topic-index:topic_onion")
    assert rec2 is not None
    assert rec2["category"] == "Decision"
    assert rec2["project"] == "onion_project"

    # Search works across migrated records
    results = search_records(db_conn, "Alpha")
    assert len(results) == 1
    assert results[0]["record_id"] == "yonc-project-index:p_001"

