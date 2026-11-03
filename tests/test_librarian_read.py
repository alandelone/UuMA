import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from uuma import mcp_librarian
from uuma.librarian_read import LibrarianReader


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    sources = [
        {"source_id": "brainstormer-state", "owner_agent": "brainstormer",
         "readers": ["orchestrator", "yonc"], "capture_status": "PARTIAL",
         "captured_at": "2026-10-28T00:00:00+08:00", "source_as_of": "2026-10-27",
         "verification": "HASH_VERIFIED"},
        {"source_id": "honc-private", "owner_agent": "honc", "readers": ["honc"],
         "capture_status": "COMPLETE", "verification": "UNVERIFIED"},
    ]
    records = []

    def add(record_id, version_id, text, *, project="farm", status="OPEN", kind="question",
            source="brainstormer-state", day="28", media_type="text/plain"):
        raw = text.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        path = root / "objects" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        records.append({
            "record_id": record_id, "version_id": version_id, "source_id": source,
            "readers": sources[1 if source == "honc-private" else 0]["readers"],
            "project_ids": [project], "kind": kind, "title": record_id,
            "original_status": status, "original_ref": f"native:{record_id}:{version_id}",
            "captured_at": f"2026-10-{day}T00:00:00+08:00", "is_summary": False,
            "content_sha256": digest, "content_bytes": len(raw), "media_type": media_type,
        })

    add("farm-question", "v1", "Earlier open question", day="27")
    add("farm-question", "v2", "尚未决定🌱\nOriginal question")
    add("farm-checkpoint", "v1", "Alternatives remain unresolved", kind="checkpoint", status="DRAFT")
    add("failed-run", "v1", "Original failure and output", kind="execution", status="FAILED")
    add("moved-record", "v1", "Old project association", day="27")
    add("moved-record", "v2", "New project association", project="other")
    add("private-body", "v1", "Private observation", source="honc-private", kind="body")
    catalog = {"schema_version": 1, "snapshot_id": "daily-20261028",
               "published_at": "2026-10-28T00:05:00+08:00", "sources": sources, "records": records}
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return root, catalog


def publish(root, catalog):
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")


def tree_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_history_original_status_and_project_reassignment_are_preserved(archive):
    root, _ = archive
    reader = LibrarianReader(root, "yonc")
    history = reader.search_records(query="farm-question")
    assert {row["version_id"] for row in history["records"]} == {"v1", "v2"}
    context = reader.project_context("farm")
    assert {(row["record_id"], row["version_id"]) for row in context["records"]} == {
        ("farm-question", "v2"), ("farm-checkpoint", "v1"), ("failed-run", "v1"),
    }
    assert {row["original_status"] for row in context["records"]} == {"OPEN", "DRAFT", "FAILED"}
    assert all(not row["is_summary"] and not row["content_verified"] for row in context["records"])


def test_scope_filters_search_context_record_and_source_status(archive):
    root, _ = archive
    reader = LibrarianReader(root, "yonc")
    assert reader.search_records(query="private")["records"] == []
    assert reader.project_context("farm")["total"] == 3
    assert {source["source_id"] for source in reader.list_sources()["sources"]} == {
        "brainstormer-state",
    }
    with pytest.raises(KeyError, match="unavailable"):
        reader.get_record("private-body", "v1")
    with pytest.raises(KeyError, match="unavailable"):
        reader.read_record("private-body", "v1")
    assert LibrarianReader(root, "honc").search_records()["total"] == 1
    assert LibrarianReader(root, "unregistered").list_sources()["sources"] == []


def test_unicode_chunks_and_content_hash_are_verified_without_any_write(archive):
    root, _ = archive
    before = tree_bytes(root)
    reader = LibrarianReader(root, "yonc")
    first = reader.read_record("farm-question", "v2", limit=5)
    rest = reader.read_record("farm-question", "v2", offset=first["next_offset"])
    assert first["text"] + rest["text"] == "尚未决定🌱\nOriginal question"
    assert first["content_verified"] and rest["next_offset"] is None
    reader.search_records()
    reader.project_context("farm")
    status = reader.backup_status()
    assert status["sources"][0]["capture_status"] == "PARTIAL"
    assert status["sources"][0]["verification"] == "HASH_VERIFIED"
    assert not status["fresh_live_sources_checked"] and not status["schedule_installed_by_reader"]
    assert tree_bytes(root) == before


def test_pagination_is_snapshot_bound_and_does_not_hide_remaining_versions(archive):
    root, _ = archive
    reader = LibrarianReader(root, "yonc")
    first = reader.search_records(limit=2)
    second = reader.search_records(limit=2, offset=first["next_offset"],
                                   expected_snapshot_id=first["snapshot_id"])
    assert len(first["records"]) == len(second["records"]) == 2
    assert {(row["record_id"], row["version_id"]) for row in first["records"]}.isdisjoint(
        {(row["record_id"], row["version_id"]) for row in second["records"]}
    )
    with pytest.raises(ValueError, match="snapshot changed"):
        reader.search_records(expected_snapshot_id="a-different-snapshot")


def test_tampered_object_is_not_returned_as_valid_content(archive):
    root, catalog = archive
    record = catalog["records"][1]
    digest = record["content_sha256"]
    path = root / "objects" / digest[:2] / digest
    original = path.read_bytes()
    path.write_bytes(b"X" + original[1:])
    with pytest.raises(ValueError, match="digest check"):
        LibrarianReader(root, "yonc").read_record("farm-question", "v2")


@pytest.mark.parametrize("mutation", ["duplicate-source", "duplicate-version", "escalated-reader",
                                      "changed-source", "untraced-summary", "unproven-restore"])
def test_malformed_scope_provenance_and_identity_fail_closed(archive, mutation):
    root, catalog = archive
    if mutation == "duplicate-source":
        catalog["sources"].append(catalog["sources"][0])
    elif mutation == "duplicate-version":
        catalog["records"].append(catalog["records"][0])
    elif mutation == "escalated-reader":
        catalog["records"][0]["readers"] = ["scholar"]
    elif mutation == "changed-source":
        catalog["records"][1]["source_id"] = "honc-private"
        catalog["records"][1]["readers"] = ["honc"]
    elif mutation == "untraced-summary":
        catalog["records"][0]["is_summary"] = True
    else:
        catalog["sources"][0]["verification"] = "RESTORE_VERIFIED"
    publish(root, catalog)
    with pytest.raises(ValueError):
        LibrarianReader(root, "yonc")


def test_missing_archive_and_identity_do_not_initialize_a_store(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        LibrarianReader(missing, "yonc")
    with pytest.raises(PermissionError):
        LibrarianReader(missing, "")
    assert not missing.exists()


def test_catalog_duplicate_keys_and_traversal_digest_are_rejected(archive):
    root, catalog = archive
    path = root / "catalog.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        LibrarianReader(root, "yonc")
    catalog["records"][0]["content_sha256"] = "../outside"
    publish(root, catalog)
    with pytest.raises(ValueError):
        LibrarianReader(root, "yonc")


def test_symlinked_archive_object_is_rejected(archive, tmp_path):
    root, catalog = archive
    digest = catalog["records"][0]["content_sha256"]
    path = root / "objects" / digest[:2] / digest
    outside = tmp_path / "outside.txt"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Fixture symlinks unavailable on this platform: {exc}")
    with pytest.raises(ValueError, match="symlinks"):
        LibrarianReader(root, "yonc").read_record("farm-question", "v1")


@pytest.mark.parametrize("change", ["binary", "large"])
def test_unsupported_inline_content_stays_explicitly_metadata_only(archive, change):
    root, catalog = archive
    if change == "binary":
        catalog["records"][0]["media_type"] = "application/pdf"
    else:
        catalog["records"][0]["content_bytes"] = 8 * 1024 * 1024 + 1
    publish(root, catalog)
    reader = LibrarianReader(root, "yonc")
    assert reader.get_record("farm-question", "v1")["content_verified"] is False
    with pytest.raises(ValueError):
        reader.read_record("farm-question", "v1")


def test_mcp_surface_has_only_semantic_reads_and_no_caller_identity_argument(archive, monkeypatch):
    root, _ = archive
    monkeypatch.setenv("UUMA_AGENT_ID", "yonc")
    monkeypatch.setenv("UUMA_LIBRARIAN_ARCHIVE_ROOT", str(root))
    tools = asyncio.run(mcp_librarian.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "librarian_list_sources", "librarian_search_records", "librarian_get_record",
        "librarian_read_record", "librarian_read_binary_chunk", "librarian_get_project_context",
        "librarian_get_backup_status",
    }
    for tool in tools:
        assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
        assert not {"actor_id", "root", "path", "sql", "database_path"}.intersection(
            tool.inputSchema["properties"])
    response = asyncio.run(mcp_librarian.mcp.call_tool(
        "librarian_get_project_context", {"project_id": "farm"},
    ))[1]
    assert response["total"] == 3 and response["context_kind"] == "source_record_index"


def test_mcp_rejects_missing_host_binding(archive, monkeypatch):
    monkeypatch.delenv("UUMA_AGENT_ID", raising=False)
    monkeypatch.delenv("UUMA_LIBRARIAN_ARCHIVE_ROOT", raising=False)
    with pytest.raises(PermissionError):
        mcp_librarian.librarian_list_sources()


def test_actual_stdio_protocol_reads_only_fixture_archive(archive):
    root, _ = archive
    before = tree_bytes(root)
    environment = os.environ.copy()
    environment.update({
        "UUMA_AGENT_ID": "yonc", "UUMA_LIBRARIAN_ARCHIVE_ROOT": str(root),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    })

    async def probe():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "uuma.mcp_librarian"], env=environment,
        )
        async with (
            stdio_client(parameters) as (incoming, outgoing),
            ClientSession(incoming, outgoing) as client,
        ):
            await client.initialize()
            tools = await client.list_tools()
            assert len(tools.tools) == 7
            result = await client.call_tool("librarian_read_record", {
                "record_id": "farm-question", "version_id": "v2", "limit": 5,
            })
            assert not result.isError
            assert result.structuredContent["text"] == "尚未决定🌱"
            assert result.structuredContent["original_status"] == "OPEN"
            denied = await client.call_tool("librarian_get_record", {
                "record_id": "private-body", "version_id": "v1",
            })
            assert denied.isError

    asyncio.run(probe())
    assert tree_bytes(root) == before


def test_binary_chunks_preserve_acl_and_verify_entire_object(archive):
    import base64

    root, catalog = archive
    catalog["records"][0]["media_type"] = "application/pdf"
    publish(root, catalog)
    reader = LibrarianReader(root, "yonc")
    first = reader.read_binary_chunk("farm-question", "v1", limit=5)
    second = reader.read_binary_chunk("farm-question", "v1", offset=first["next_offset"])
    assert base64.b64decode(first["content_base64"]) + base64.b64decode(
        second["content_base64"]
    ) == b"Earlier open question"
    assert first["content_verified"] and second["next_offset"] is None
    with pytest.raises(KeyError):
        reader.read_binary_chunk("private-body", "v1")
    digest = catalog["records"][0]["content_sha256"]
    (root / "objects" / digest[:2] / digest).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest check"):
        reader.read_binary_chunk("farm-question", "v1", limit=1)
