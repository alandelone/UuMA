import json
import os
from datetime import UTC, datetime

import pytest

from uuma.librarian_brainstormer_index import topic_index


def snapshot():
    return json.dumps({
        "project_id": "project-one", "revision": 4, "updated_at": "2026-10-30T01:00:00+00:00",
        "objects": {
            "topic-one": {"id": "topic-one", "kind": "topic", "status": "ACTIVE",
                          "title": "private source text SECRET-FIXTURE"},
            "q1": {"id": "q1", "kind": "question", "topic_id": "topic-one", "status": "OPEN"},
            "c1": {"id": "c1", "kind": "checkpoint", "topic_id": "topic-one"},
            "other": {"id": "other", "kind": "decision", "topic_id": "different-topic"},
        },
    }).encode()


def test_topic_index_is_derived_provenance_without_private_text_or_invented_decisions():
    result = topic_index(snapshot(), project_id="project-one", topic_id="topic-one",
                         captured_at=datetime(2026, 10, 30, tzinfo=UTC),
                         readers=["orchestrator", "brainstormer"])
    body = json.loads(result["content"])
    assert body["source_revision"] == 4 and body["topic_status"] == "ACTIVE"
    assert body["object_counts"]["question"] == 1 and body["object_counts"]["checkpoint"] == 1
    assert body["object_counts"]["decision"] == 0
    assert b"SECRET-FIXTURE" not in result["content"]
    assert result["record"]["is_summary"] is True and result["record"]["derived_from"]
    assert result["record"]["original_status"] == "ACTIVE"


def test_missing_topic_unrecognized_status_and_ambiguous_json_fail_closed():
    kwargs = {"project_id": "project-one", "topic_id": "topic-one",
              "captured_at": datetime(2026, 10, 30, tzinfo=UTC), "readers": ["orchestrator"]}
    with pytest.raises(ValueError, match="not present"):
        topic_index(snapshot(), **(kwargs | {"topic_id": "missing"}))
    state = json.loads(snapshot())
    state["objects"]["topic-one"]["status"] = "ARBITRARY_SECRET"
    with pytest.raises(ValueError, match="not recognized"):
        topic_index(json.dumps(state).encode(), **kwargs)
    with pytest.raises(ValueError, match="Duplicate"):
        topic_index(b'{"project_id":"project-one","project_id":"forged"}', **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="Catalog publication requires POSIX")
def test_safe_index_can_be_published_without_claiming_full_source_coverage(tmp_path):
    from uuma.librarian_catalog_publish import publish_catalog
    from uuma.librarian_read import LibrarianReader

    result = topic_index(snapshot(), project_id="project-one", topic_id="topic-one",
                         captured_at=datetime(2026, 10, 30, tzinfo=UTC),
                         readers=["orchestrator", "brainstormer"])
    source = {"source_id": "brainstormer-index", "owner_agent": "brainstormer",
              "readers": ["orchestrator", "brainstormer"], "capture_status": "PARTIAL",
              "captured_at": "2026-10-30T00:00:00+00:00", "source_as_of": result["source_updated_at"],
              "verification": "UNVERIFIED", "evidence_refs": []}
    catalog = {"schema_version": 1, "snapshot_id": "fixture-index-1",
               "published_at": "2026-10-30T00:00:00+00:00", "sources": [source],
               "records": [result["record"]]}
    content = tmp_path / "index.json"
    content.write_bytes(result["content"])
    root = tmp_path / "archive"
    root.mkdir(mode=0o700)
    record = result["record"]
    publish_catalog(root, catalog,
                    approved_versions=frozenset({(record["record_id"], record["version_id"])}),
                    object_sources={record["content_sha256"]: content}, expected_current_sha256=None)
    value = LibrarianReader(root, "brainstormer").read_record(record["record_id"], record["version_id"])
    assert json.loads(value["text"])["object_counts"]["decision"] == 0
    assert LibrarianReader(root, "honc").search_records()["total"] == 0
    assert LibrarianReader(root, "brainstormer").list_sources()["sources"][0]["capture_status"] == "PARTIAL"
