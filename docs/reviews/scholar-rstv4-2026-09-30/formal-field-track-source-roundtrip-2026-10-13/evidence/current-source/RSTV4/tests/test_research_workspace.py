from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rstv4.catalog_web import create_app
from rstv4.database import initialize_catalog


@pytest.fixture
def catalog(tmp_path: Path) -> tuple[TestClient, Path]:
    db = tmp_path / "data" / "catalog.db"
    initialize_catalog(db)
    return TestClient(create_app(tmp_path)), db


def action(client: TestClient, operation: str, request_id: str, **values):
    return client.post("/api/catalog/research-actions", json={
        "operation": operation, "request_id": request_id, **values,
    })


def create_structure(client: TestClient) -> tuple[dict, dict, dict]:
    field = action(client, "CREATE_FIELD", "field", name="Energy", description="Long term").json()
    topic = action(client, "CREATE_TOPIC", "topic", name="Trading", field_id=field["object_id"]).json()
    track = action(client, "CREATE_TRACK", "track", title="Off grid",
                   field_id=field["object_id"], primary_topic_id=topic["object_id"],
                   scope="Fixed scientific scope", research_type="conceptual_framework").json()
    return field, topic, track


def test_retries_return_original_receipt_without_duplicate_track(catalog):
    client, db = catalog
    field, topic, track = create_structure(client)
    retry = action(client, "CREATE_TRACK", "track", title="Off grid", field_id=field["object_id"],
                   primary_topic_id=topic["object_id"], scope="Fixed scientific scope",
                   research_type="conceptual_framework")
    assert retry.json() == track
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_tracks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM research_workspace_actions").fetchone()[0] == 3


def test_same_request_id_cannot_be_repurposed(catalog):
    client, _ = catalog
    assert action(client, "CREATE_FIELD", "one", name="Original").status_code == 200
    assert action(client, "CREATE_FIELD", "one", name="Different").status_code == 409
    assert client.get("/api/catalog/research-overview").json()["fields"][0]["name"] == "Original"


def test_duplicate_names_require_explicit_topic_link(catalog):
    client, db = catalog
    field, topic, _ = create_structure(client)
    assert action(client, "CREATE_FIELD", "duplicate-field", name="  ENERGY ").status_code == 409
    second = action(client, "CREATE_FIELD", "second", name="Justice").json()
    duplicate = action(client, "CREATE_TOPIC", "duplicate-topic", field_id=second["object_id"],
                       name=" TRADING ", description="Must not overwrite")
    assert duplicate.status_code == 409
    assert "Explicitly link" in duplicate.json()["detail"]
    linked = action(client, "LINK_TOPIC", "link", field_id=second["object_id"], topic_id=topic["object_id"])
    assert linked.status_code == 200
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM field_topics").fetchone()[0] == 2
        assert conn.execute("SELECT field_id FROM research_tracks").fetchone()[0] == field["object_id"]


def test_shared_topic_edit_changes_one_record_and_no_track_scope(catalog):
    client, db = catalog
    field, topic, track = create_structure(client)
    second = action(client, "CREATE_FIELD", "second", name="Justice").json()
    action(client, "LINK_TOPIC", "link", field_id=second["object_id"], topic_id=topic["object_id"])
    data = client.get("/api/catalog/research-overview").json()
    saved = action(client, "EDIT_TOPIC", "edit", field_id=second["object_id"], topic_id=topic["object_id"],
                   name="Energy trading", description="Shared definition",
                   expected_digest=data["topics"][0]["metadata_digest"])
    assert saved.status_code == 200
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name,description FROM topics").fetchone() == (
            "Energy trading", "Shared definition",
        )
        assert conn.execute("SELECT * FROM research_tracks").fetchone() == tuple(track["object"].values())
        assert conn.execute("SELECT COUNT(*) FROM field_topics").fetchone()[0] == 2
    assert field["object_id"] != second["object_id"]


def test_stale_edit_and_identical_name_restoration_do_not_revive_old_draft(catalog):
    client, _ = catalog
    field, _, _ = create_structure(client)
    original = field["metadata_digest"]
    first = action(client, "EDIT_FIELD", "edit-one", field_id=field["object_id"], name="Changed",
                   description="Long term", expected_digest=original).json()
    restored = action(client, "EDIT_FIELD", "restore", field_id=field["object_id"], name="Energy",
                      description="Long term", expected_digest=first["metadata_digest"])
    assert restored.status_code == 200
    assert action(client, "EDIT_FIELD", "stale", field_id=field["object_id"], name="Stale overwrite",
                  expected_digest=original).status_code == 409
    assert action(client, "EDIT_FIELD", "edit-one", field_id=field["object_id"], name="Changed",
                  description="Long term", expected_digest=original).json() == first
    assert client.get("/api/catalog/research-overview").json()["fields"][0]["name"] == "Energy"


def test_two_concurrent_editors_have_one_winner(catalog):
    client, _ = catalog
    field, _, _ = create_structure(client)
    def edit(index):
        return action(client, "EDIT_FIELD", f"concurrent-{index}", field_id=field["object_id"],
                      name=f"Name {index}", expected_digest=field["metadata_digest"]).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, [1, 2])) == [200, 409]


def test_receipt_failure_rolls_back_the_track_and_its_links(catalog):
    client, db = catalog
    field, topic, _ = create_structure(client)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON research_workspace_actions "
                     "BEGIN SELECT RAISE(ABORT,'simulated receipt failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="simulated receipt failure"):
        action(client, "CREATE_TRACK", "crash", title="Should not exist", field_id=field["object_id"],
               primary_topic_id=topic["object_id"], research_type="case_study")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_tracks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM track_topics").fetchone()[0] == 1
        conn.execute("DROP TRIGGER reject_receipt")
    assert action(client, "CREATE_TRACK", "crash", title="Should not exist", field_id=field["object_id"],
                  primary_topic_id=topic["object_id"], research_type="case_study").status_code == 200


def test_missing_and_wrong_field_topic_ownership_reject_without_action(catalog):
    client, db = catalog
    field, topic, track = create_structure(client)
    second = action(client, "CREATE_FIELD", "second", name="Other").json()
    assert action(client, "CREATE_TOPIC", "bad-parent", name="Unknown", field_id="missing").status_code == 404
    assert action(client, "CREATE_TRACK", "bad-topic", title="Wrong parent", field_id=second["object_id"],
                  primary_topic_id=topic["object_id"], research_type="experimental").status_code == 409
    assert action(client, "EDIT_TOPIC", "foreign-topic", name="Wrong field", field_id=second["object_id"],
                  topic_id=topic["object_id"], expected_digest=topic["metadata_digest"]).status_code == 409
    assert action(client, "EDIT_TRACK", "foreign-track", title="Wrong field", field_id=second["object_id"],
                  track_id=track["object_id"], expected_digest=track["metadata_digest"]).status_code == 404
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_workspace_actions").fetchone()[0] == 4
        assert conn.execute("SELECT field_id FROM research_tracks").fetchone()[0] == field["object_id"]


@pytest.mark.parametrize("extra", [
    {"scope": "Changed scope"}, {"status": "APPROVED"}, {"research_type": "experimental"},
    {"revision": 2}, {"primary_topic_id": "elsewhere"},
])
def test_track_title_editor_cannot_alter_scientific_state(catalog, extra):
    client, db = catalog
    field, _, track = create_structure(client)
    rejected = action(client, "EDIT_TRACK", "forbidden", title="New title", field_id=field["object_id"],
                      track_id=track["object_id"], expected_digest=track["metadata_digest"], **extra)
    assert rejected.status_code == 422
    saved = action(client, "EDIT_TRACK", "rename", title="New title", field_id=field["object_id"],
                   track_id=track["object_id"], expected_digest=track["metadata_digest"])
    assert saved.status_code == 200
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        actual = dict(conn.execute("SELECT * FROM research_tracks").fetchone())
        assert actual["title"] == "New title"
        for name in actual.keys() - {"title", "updated_at"}:
            assert actual[name] == track["object"][name]
        assert conn.execute("SELECT COUNT(*) FROM research_nodes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM track_snapshot_adoptions").fetchone()[0] == 0


def test_reading_legacy_overview_installs_no_schema_and_exposes_no_local_path(catalog):
    client, db = catalog
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE research_workspace_actions")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    payload = client.get("/api/catalog/research-overview").json()
    assert len(payload["workspace_id"]) == 64
    assert str(db) not in str(payload)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='research_workspace_actions'").fetchone() is None
    assert action(client, "CREATE_FIELD", "explicit-write", name="First").status_code == 200


def test_overview_digest_matches_current_receipt_and_external_edit_invalidates_it(catalog):
    client, db = catalog
    field, _, _ = create_structure(client)
    data = client.get("/api/catalog/research-overview").json()
    assert data["fields"][0]["metadata_digest"] == field["metadata_digest"]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_fields SET description='External change'")
    assert action(client, "EDIT_FIELD", "external-stale", name="Overwrite", field_id=field["object_id"],
                  expected_digest=field["metadata_digest"]).status_code == 409


def test_unknown_research_type_and_extra_field_rejected(catalog):
    client, _ = catalog
    field, topic, _ = create_structure(client)
    assert action(client, "CREATE_TRACK", "unknown", title="Unknown", field_id=field["object_id"],
                  primary_topic_id=topic["object_id"], research_type="magic").status_code == 422
    assert action(client, "CREATE_FIELD", "approval", name="New", approved=True).status_code == 422
