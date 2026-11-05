"""Tests for ChatGPT bridge semantic index adapter."""

import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from uuma.librarian_chatgpt_index import (
    chatgpt_bridge_summary_index,
    chatgpt_thread_indices,
)
from uuma.librarian_read import ArchiveRecord, LibrarianReader


@pytest.fixture
def sample_chatgpt_db_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute(
            "CREATE TABLE chatgpt_accounts ("
            "alias TEXT, identity TEXT, workspace TEXT, enabled INTEGER, "
            "status TEXT, capabilities TEXT, verified_at REAL, action TEXT, "
            "error TEXT, chrome_profile TEXT, confirmed_capabilities TEXT)"
        )
        conn.execute(
            "CREATE TABLE chatgpt_routes (agent TEXT, account TEXT)"
        )
        conn.execute(
            "CREATE TABLE chatgpt_threads (account TEXT, agent TEXT, project TEXT, thread TEXT, url TEXT)"
        )
        conn.execute(
            "CREATE TABLE chatgpt_requests ("
            "id TEXT, agent TEXT, account TEXT, run_id TEXT, project TEXT, "
            "thread TEXT, mode TEXT, payload TEXT, digest TEXT, idem TEXT, "
            "status TEXT, url TEXT, result TEXT, error TEXT, created REAL, "
            "updated REAL, submitted REAL)"
        )
        conn.execute(
            "CREATE TABLE chatgpt_events (sequence INTEGER, subject TEXT, actor TEXT, kind TEXT, at REAL, detail TEXT)"
        )

        # Insert fixtures including sensitive strings
        conn.execute(
            "INSERT INTO chatgpt_accounts VALUES ("
            "'account-alpha', 'user@example.com', 'default', 1, 'READY', "
            "'text-gen', 1730000000.0, 'none', NULL, 'profile-1', 'text-gen')"
        )
        conn.execute("INSERT INTO chatgpt_routes VALUES ('orchestrator', 'account-alpha')")
        conn.execute("INSERT INTO chatgpt_routes VALUES ('brainstormer', 'account-alpha')")

        conn.execute(
            "INSERT INTO chatgpt_threads VALUES ("
            "'account-alpha', 'orchestrator', 'project-apollo', 'thread-001', "
            "'https://chatgpt.com/c/thread-001-SECRET-URL')"
        )
        conn.execute(
            "INSERT INTO chatgpt_threads VALUES ("
            "'account-alpha', 'brainstormer', 'project-gemini', 'thread-002', "
            "'https://chatgpt.com/c/thread-002-SECRET-URL')"
        )

        conn.execute(
            "INSERT INTO chatgpt_requests VALUES ("
            "'req-1', 'orchestrator', 'account-alpha', 'run-1', 'project-apollo', "
            "'thread-001', 'chat', 'SECRET_PROMPT_PAYLOAD_HERE', 'sha1', 'idem1', "
            "'SUCCEEDED', 'url1', 'SECRET_MODEL_RESULT_HERE', NULL, 1.0, 2.0, 1.5)"
        )
        conn.execute(
            "INSERT INTO chatgpt_requests VALUES ("
            "'req-2', 'orchestrator', 'account-alpha', 'run-2', 'project-apollo', "
            "'thread-001', 'chat', 'ANOTHER_SECRET_PROMPT', 'sha2', 'idem2', "
            "'FAILED', 'url2', NULL, 'timeout error', 3.0, 4.0, 3.5)"
        )
        conn.execute(
            "INSERT INTO chatgpt_requests VALUES ("
            "'req-3', 'brainstormer', 'account-alpha', 'run-3', 'project-gemini', "
            "'thread-002', 'chat', 'THIRD_SECRET_PROMPT', 'sha3', 'idem3', "
            "'SUCCEEDED', 'url3', 'MODEL_OUTPUT_SECRET', NULL, 5.0, 6.0, 5.5)"
        )
        conn.commit()
        conn.close()
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def test_chatgpt_summary_index_excludes_private_payloads_and_tokens(sample_chatgpt_db_bytes: bytes):
    captured_at = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    readers = ["orchestrator", "librarian"]

    result = chatgpt_bridge_summary_index(
        sample_chatgpt_db_bytes, readers=readers, captured_at=captured_at
    )

    content_bytes = result["content"]
    assert b"SECRET_PROMPT_PAYLOAD" not in content_bytes
    assert b"SECRET_MODEL_RESULT" not in content_bytes
    assert b"user@example.com" not in content_bytes

    body = json.loads(content_bytes.decode("utf-8"))
    assert body["record_type"] == "chatgpt-bridge-structural-index"
    assert body["accounts_by_status"] == {"READY": 1}
    assert body["routes_count"] == 2
    assert body["threads_count"] == 2
    assert body["requests_by_status"] == {"SUCCEEDED": 2, "FAILED": 1}

    # Verify conforming to ArchiveRecord
    record = ArchiveRecord.model_validate(result["record"])
    assert record.record_id == "chatgpt-bridge-summary"
    assert record.source_id == "chatgpt-bridge-state"
    assert record.readers == readers
    assert record.is_summary is True
    assert record.original_status == "ACTIVE"


def test_chatgpt_thread_indices_generates_thread_records(sample_chatgpt_db_bytes: bytes):
    captured_at = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    readers = ["orchestrator", "librarian"]

    results = chatgpt_thread_indices(
        sample_chatgpt_db_bytes, readers=readers, captured_at=captured_at
    )
    assert len(results) == 2

    thread_1 = next(r for r in results if json.loads(r["content"])["thread_id"] == "thread-001")
    body_1 = json.loads(thread_1["content"].decode("utf-8"))
    assert body_1["thread_id"] == "thread-001"
    assert body_1["agent"] == "orchestrator"
    assert body_1["project"] == "project-apollo"
    assert body_1["request_counts"] == {"SUCCEEDED": 1, "FAILED": 1}
    assert body_1["total_requests"] == 2
    assert b"SECRET_PROMPT" not in thread_1["content"]

    # Validate against ArchiveRecord
    rec_1 = ArchiveRecord.model_validate(thread_1["record"])
    assert rec_1.kind == "thread-index"
    assert rec_1.project_ids == ["project-apollo"]
    assert rec_1.readers == readers


@pytest.mark.parametrize("different_field,different_value", [
    ("account", "account-beta"),
    ("agent", "brainstormer"),
    ("project", "project-gemini"),
])
def test_default_thread_bindings_keep_identity_and_requests_separate(
    sample_chatgpt_db_bytes, tmp_path, different_field, different_value,
):
    database = tmp_path / "bridge.db"
    database.write_bytes(sample_chatgpt_db_bytes)
    first = {"account": "account-alpha", "agent": "orchestrator", "project": "project-apollo"}
    second = first | {different_field: different_value}
    with closing(sqlite3.connect(database)) as conn:
        for old_thread, binding in [("thread-001", first), ("thread-002", second)]:
            values = (binding["account"], binding["agent"], binding["project"], "main", old_thread)
            for table in ["chatgpt_threads", "chatgpt_requests"]:
                conn.execute(
                    f"UPDATE {table} SET account=?,agent=?,project=?,thread=? WHERE thread=?",
                    values,
                )
        conn.commit()

    captured_at = datetime(2026, 11, 5, tzinfo=UTC)
    results = chatgpt_thread_indices(
        database.read_bytes(), readers=["librarian"], captured_at=captured_at,
    )
    keys = {(r["record"]["record_id"], r["record"]["version_id"]) for r in results}
    assert len(keys) == 2
    for result, expected_count, binding in zip(results, [2, 1], [first, second], strict=True):
        body = json.loads(result["content"])
        assert body["account_alias"] == binding["account"]
        assert body["agent"] == binding["agent"]
        assert body["project"] == binding["project"]
        assert body["total_requests"] == expected_count
        assert sum(body["request_counts"].values()) == expected_count

    archive = tmp_path / "archive"
    archive.mkdir()
    for result in results:
        digest = result["record"]["content_sha256"]
        path = archive / "objects" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result["content"])
    (archive / "catalog.json").write_text(json.dumps({
        "schema_version": 1, "snapshot_id": "fixture-scoped-bindings",
        "published_at": captured_at.isoformat(),
        "sources": [{"source_id": "chatgpt-bridge-state", "owner_agent": "orchestrator",
                     "readers": ["librarian"], "capture_status": "PARTIAL"}],
        "records": [r["record"] for r in results],
    }), encoding="utf-8")
    reader = LibrarianReader(archive, "librarian")
    assert reader.search_records(source_id="chatgpt-bridge-state")["total"] == 2
    for result in results:
        record = result["record"]
        read = reader.read_record(record["record_id"], record["version_id"])
        assert read["content_verified"] is True
        assert json.loads(read["text"]) == json.loads(result["content"])

    with closing(sqlite3.connect(database)) as conn:
        conn.execute("UPDATE chatgpt_requests SET status='COMPLETED'")
        conn.commit()
    revised = chatgpt_thread_indices(
        database.read_bytes(), readers=["librarian"], captured_at=captured_at,
    )
    assert [r["record"]["record_id"] for r in revised] == [r["record"]["record_id"] for r in results]
    assert all(new["record"]["version_id"] != old["record"]["version_id"]
               for new, old in zip(revised, results, strict=True))


@pytest.mark.parametrize("thread_names", [("a/b", "a?b"), ("a" * 99 + "x", "a" * 99 + "y")])
def test_thread_identity_preserves_punctuation_and_long_names(
    sample_chatgpt_db_bytes, tmp_path, thread_names,
):
    database = tmp_path / "bridge.db"
    database.write_bytes(sample_chatgpt_db_bytes)
    with closing(sqlite3.connect(database)) as conn:
        for old_thread, name in zip(["thread-001", "thread-002"], thread_names, strict=True):
            conn.execute("UPDATE chatgpt_threads SET account='a',agent='orchestrator',"
                         "project='p',thread=? WHERE thread=?", (name, old_thread))
        conn.commit()
    results = chatgpt_thread_indices(
        database.read_bytes(), readers=["librarian"], captured_at=datetime(2026, 11, 5, tzinfo=UTC),
    )
    assert len({r["record"]["record_id"] for r in results}) == 2
    assert len({r["record"]["original_ref"] for r in results}) == 2
    assert all(len(r["record"]["record_id"]) <= 160
               and len(r["record"]["version_id"]) <= 160 for r in results)


def test_invalid_inputs_and_missing_tables_fail_closed():
    captured_at = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    readers = ["orchestrator", "librarian"]

    # 1. Non-sqlite bytes
    with pytest.raises(ValueError, match="not a valid SQLite format 3"):
        chatgpt_bridge_summary_index(b"arbitrary invalid bytes", readers=readers, captured_at=captured_at)

    # 2. Naive datetime (missing tzinfo)
    naive_dt = datetime(2026, 11, 4, 12, 0, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="explicit timezone"):
        chatgpt_bridge_summary_index(
            b"SQLite format 3\x00" + b"\x00" * 84, readers=readers, captured_at=naive_dt
        )

    # 3. Invalid readers
    with pytest.raises(ValueError, match="Invalid explicit reader identities"):
        chatgpt_bridge_summary_index(
            b"SQLite format 3\x00" + b"\x00" * 84, readers=["invalid reader!"], captured_at=captured_at
        )
