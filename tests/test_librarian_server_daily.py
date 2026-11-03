import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_server_daily import _tree, owner_matches, run_sources


@pytest.fixture(scope="module")
def public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_sqlite_and_tree_are_encrypted_once_and_intake_is_idempotent(tmp_path, public):
    queue, intake, tree = tmp_path / "queue", tmp_path / "intake", tmp_path / "tree"
    for path in (queue, intake, tree):
        path.mkdir(mode=0o700)
    database = tmp_path / "owner.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records(value TEXT)")
        db.execute("INSERT INTO records VALUES ('original')")
        db.commit()
        (tree / "state.json").write_text("original fixture")
        specs = [{"source_id": "owner-db", "kind": "sqlite", "path": str(database)},
                 {"source_id": "owner-tree", "kind": "tree", "path": str(tree)}]
        kwargs = {"queue": queue, "intake": intake, "public_pem": public,
                  "now": datetime(2026, 10, 29, 0, tzinfo=UTC), "verify_owner": lambda spec: True}
        first = run_sources(specs, **kwargs)
        assert first["incomplete"] == 0
        assert all(x["server_intake"] == "DELIVERED" and x["nas_publication"] == "NOT_CHECKED"
                   for x in first["sources"])
        retained = {p: p.read_bytes() for p in queue.rglob("*.capsule")}
        (tree / "state.json").write_text("changed after capture")
        second = run_sources(specs, **kwargs)
        assert second == first
        assert retained == {p: p.read_bytes() for p in queue.rglob("*.capsule")}
        assert db.execute("SELECT value FROM records").fetchall() == [("original",)]
    with closing(sqlite3.connect(intake / "recovery-intake.sqlite")) as db:
        assert db.execute("SELECT COUNT(*) FROM manifest_revisions").fetchone()[0] == 2


def test_unverified_owner_cannot_trigger_capture(tmp_path, public):
    queue, intake = tmp_path / "queue", tmp_path / "intake"
    queue.mkdir(mode=0o700)
    intake.mkdir(mode=0o700)
    spec = {"source_id": "owner", "kind": "sqlite", "path": str(tmp_path / "missing")}
    result = run_sources([spec], queue=queue, intake=intake, public_pem=public,
                         verify_owner=lambda spec: False)
    assert result["incomplete"] == 1 and result["sources"][0]["status"] == "OWNER_UNVERIFIED"
    assert list(queue.iterdir()) == [] and list(intake.iterdir()) == []


def test_missing_sqlite_is_partial_and_does_not_create_source(tmp_path, public):
    queue, intake = tmp_path / "queue", tmp_path / "intake"
    queue.mkdir(mode=0o700)
    intake.mkdir(mode=0o700)
    missing = tmp_path / "missing.sqlite"
    spec = {"source_id": "owner", "kind": "sqlite", "path": str(missing)}
    result = run_sources([spec], queue=queue, intake=intake, public_pem=public,
                         verify_owner=lambda spec: True)
    assert result["incomplete"] == 1
    assert result["sources"][0]["coverage"] == "PARTIAL"
    assert not missing.exists()


def test_duplicate_or_untrusted_source_names_fail_before_writes(tmp_path, public):
    queue, intake = tmp_path / "queue", tmp_path / "intake"
    queue.mkdir(mode=0o700)
    intake.mkdir(mode=0o700)
    spec = {"source_id": "../escape", "kind": "sqlite", "path": str(tmp_path / "file")}
    with pytest.raises(ValueError):
        run_sources([spec], queue=queue, intake=intake, public_pem=public,
                    verify_owner=lambda spec: True)
    assert list(queue.iterdir()) == [] and list(intake.iterdir()) == []


def test_tree_sqlite_uses_online_snapshot_instead_of_copying_wal(tmp_path, public):
    queue, intake, tree = tmp_path / "queue", tmp_path / "intake", tmp_path / "tree"
    for path in (queue, intake, tree):
        path.mkdir(mode=0o700)
    database = tree / "owner.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records(value TEXT)")
        db.execute("INSERT INTO records VALUES ('fixture')")
        db.commit()
        assert (tree / "owner.sqlite-wal").exists()
        spec = {"source_id": "owner-tree", "kind": "tree", "path": str(tree)}
        result = run_sources([spec], queue=queue, intake=intake, public_pem=public,
                             verify_owner=lambda spec: True)
        assert result["sources"][0]["coverage"] == "COMPLETE"
        with closing(sqlite3.connect(queue / "queue.sqlite")) as queued:
            import json

            manifest = json.loads(queued.execute("SELECT manifest_json FROM batches").fetchone()[0])
        assert [entry["capture_method"] for entry in manifest["entries"]] == ["sqlite_online"]
        assert manifest["entries"][0]["source_path"] == str(database)


def test_empty_registered_directory_is_explicitly_reported(tmp_path, public):
    queue, intake, tree = tmp_path / "queue", tmp_path / "intake", tmp_path / "empty"
    for path in (queue, intake, tree):
        path.mkdir(mode=0o700)
    spec = {"source_id": "empty", "kind": "tree", "path": str(tree)}
    result = run_sources([spec], queue=queue, intake=intake, public_pem=public,
                         verify_owner=lambda spec: True)
    assert result["incomplete"] == 0
    assert result["sources"][0]["coverage"] == "EMPTY"
    assert result["sources"][0]["server_intake"] == "NOT_APPLICABLE"


def test_individual_config_file_is_encrypted_as_a_separate_source(tmp_path, public):
    queue, intake = tmp_path / "queue", tmp_path / "intake"
    queue.mkdir(mode=0o700)
    intake.mkdir(mode=0o700)
    config = tmp_path / ".env"
    config.write_bytes(b"fixture credentials")
    spec = {"source_id": "owner-config", "kind": "file", "path": str(config)}
    result = run_sources([spec], queue=queue, intake=intake, public_pem=public,
                         verify_owner=lambda spec: True)
    assert result["incomplete"] == 0
    assert result["sources"][0]["server_intake"] == "DELIVERED"
    assert b"fixture credentials" not in next(queue.rglob("*.capsule")).read_bytes()


def test_existing_batch_is_not_reinterpreted_under_a_different_key(tmp_path, public):
    queue, intake = tmp_path / "queue", tmp_path / "intake"
    queue.mkdir(mode=0o700)
    intake.mkdir(mode=0o700)
    database = tmp_path / "owner.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE records(value TEXT)")
    spec = {"source_id": "owner", "kind": "sqlite", "path": str(database)}
    kwargs = {"queue": queue, "intake": intake, "verify_owner": lambda spec: True}
    assert run_sources([spec], public_pem=public, **kwargs)["incomplete"] == 0
    other = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    result = run_sources([spec], public_pem=other, **kwargs)
    assert result["incomplete"] == 1 and result["sources"][0]["status"] == "FAILED"


def test_locked_file_is_kept_in_tree_and_reported_unavailable(tmp_path, public, monkeypatch):
    tree = tmp_path / "source"
    tree.mkdir()
    available, locked = tree / "available.txt", tree / "locked.txt"
    available.write_text("available", encoding="utf-8")
    locked.write_text("locked", encoding="utf-8")
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path == locked:
            raise PermissionError("simulated exclusive lock")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    files, sqlite_paths = _tree(tree)
    assert set(files) == {available, locked} and not sqlite_paths
    from uuma.librarian_queue import capture_recovery_batch

    batch = capture_recovery_batch(tmp_path / "queue", "pc", "source", "2026-10-30", files, public)
    assert batch["coverage"] == "PARTIAL"
    assert {Path(e["source_path"]).name: e["status"] for e in batch["entries"]} == {
        "available.txt": "CAPTURED", "locked.txt": "UNAVAILABLE",
    }


def test_semantic_archive_owner_check_binds_exact_unit_and_path(monkeypatch):
    from types import SimpleNamespace

    from uuma import librarian_server_daily

    expected = "/home/fixture/librarian/semantic-archive"
    spec = {"path": expected, "owner_unit": "uuma-librarian-semantic.service",
            "owner_env": "UUMA_LIBRARIAN_ARCHIVE_ROOT", "owner_value": expected}
    monkeypatch.setattr(librarian_server_daily.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="MainPID=123\nActiveState=active\n"))
    original = Path.read_bytes

    def fake_environ(path):
        if path.name == "environ" and path.parent.name == "123":
            return ("UUMA_LIBRARIAN_ARCHIVE_ROOT=" + expected).encode() + b"\0"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fake_environ)
    assert owner_matches(spec)
    assert not owner_matches(spec | {"path": expected + "/other"})
    assert not owner_matches(spec | {"owner_unit": "uuma-other.service"})
