import sqlite3
from contextlib import closing

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_crypto import recover
from uuma.librarian_queue import capture_recovery_batch, deliver_recovery_batch, retry_partial_batch


@pytest.fixture(scope="module")
def public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_repeated_daily_batch_reuses_exact_original_after_source_change(tmp_path, public):
    file = tmp_path / "source"
    file.write_bytes(b"original")
    root = tmp_path / "queue"
    first = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [file], public)
    objects = {p: p.read_bytes() for p in root.rglob("*.capsule")}
    file.write_bytes(b"changed")
    second = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [file], public)
    assert second == first
    assert objects == {p: p.read_bytes() for p in root.rglob("*.capsule")}
    assert first["coverage"] == "COMPLETE"
    assert file.read_bytes() == b"changed"


def test_unavailable_source_retains_partial_and_other_files(tmp_path, public):
    file = tmp_path / "source"
    file.write_bytes(b"original")
    manifest = capture_recovery_batch(
        tmp_path / "queue", "pc1", "source", "2026-10-29",
        [file, tmp_path / "missing"], public,
    )
    assert manifest["coverage"] == "PARTIAL"
    assert [item["status"] for item in manifest["entries"]] == ["CAPTURED", "UNAVAILABLE"]


def test_invalid_identity_fails_before_creating_queue(tmp_path, public):
    with pytest.raises(ValueError):
        capture_recovery_batch(
            tmp_path / "queue", "../bad", "source", "2026-10-29", [], public,
        )
    assert not (tmp_path / "queue").exists()


def test_delivery_reuses_objects_and_preserves_coverage(tmp_path, public):
    root, archive = tmp_path / "queue", tmp_path / "recovery-only"
    archive.mkdir()
    file = tmp_path / "source"
    file.write_bytes(b"secret")
    batch = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [file], public)
    first = deliver_recovery_batch(root, batch["batch_id"], archive)
    retained = {p: p.read_bytes() for p in archive.rglob("*") if p.is_file()}
    assert first == deliver_recovery_batch(root, batch["batch_id"], archive)
    assert retained == {p: p.read_bytes() for p in archive.rglob("*") if p.is_file()}
    assert first["coverage"] == "COMPLETE"


def test_tampered_object_never_publishes_success_manifest(tmp_path, public):
    root, archive = tmp_path / "queue", tmp_path / "recovery-only"
    archive.mkdir()
    file = tmp_path / "source"
    file.write_bytes(b"secret")
    batch = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [file], public)
    capsule = next(root.rglob("*.capsule"))
    capsule.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="verification"):
        deliver_recovery_batch(root, batch["batch_id"], archive)
    assert not list(archive.rglob("manifest.json"))


def test_partial_batch_retry_preserves_previous_capture_and_published_history(tmp_path, public):
    root, archive = tmp_path / "queue", tmp_path / "recovery-only"
    archive.mkdir()
    first, later = tmp_path / "first", tmp_path / "later"
    first.write_bytes(b"original")
    initial = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [first, later], public)
    assert initial["coverage"] == "PARTIAL"
    deliver_recovery_batch(root, initial["batch_id"], archive)
    original_manifest = next(archive.rglob("manifest.json"))
    original_bytes = original_manifest.read_bytes()
    first.write_bytes(b"changed after original capture")
    later.write_bytes(b"arrived after original capture")
    final = retry_partial_batch(root, initial["batch_id"], public)
    assert final["batch_id"] == initial["batch_id"] and final["revision"] == 2
    assert final["coverage"] == "COMPLETE"
    assert final["entries"][0] == initial["entries"][0]
    assert "retried_at" in final["entries"][1]
    assert retry_partial_batch(root, initial["batch_id"], public) == final
    assert deliver_recovery_batch(root, initial["batch_id"], archive)["coverage"] == "COMPLETE"
    assert original_manifest.read_bytes() == original_bytes
    assert len(list(archive.rglob("manifest-*.json"))) == 1


def test_partial_retry_rejects_different_key_without_modifying_history(tmp_path, public):
    root = tmp_path / "queue"
    first = tmp_path / "first"
    first.write_bytes(b"original")
    later = tmp_path / "later"
    initial = capture_recovery_batch(root, "pc1", "source", "2026-10-29", [first, later], public)
    later.write_bytes(b"later")
    other = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with pytest.raises(ValueError, match="cannot change"):
        retry_partial_batch(root, initial["batch_id"], other)
    assert capture_recovery_batch(root, "pc1", "source", "2026-10-29", [first], public) == initial


def test_live_sqlite_wal_is_snapshotted_encrypted_and_restorable(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    password = b"fixture-only-password"
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.BestAvailableEncryption(password))
    source, root = tmp_path / "live.sqlite", tmp_path / "queue"
    with closing(sqlite3.connect(source)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records (value TEXT)")
        db.execute("INSERT INTO records VALUES ('original')")
        db.commit()
        batch = capture_recovery_batch(root, "pc1", "sqlite", "2026-10-29", [source], public,
                                       sqlite_paths=frozenset({source}))
        entry = batch["entries"][0]
        assert batch["coverage"] == "COMPLETE" and entry["capture_method"] == "sqlite_online"
        assert entry["source_path"] == str(source.absolute())
        restored = tmp_path / "recovered.sqlite"
        recover(root / entry["object_ref"], restored, pem, password)
        with closing(sqlite3.connect(restored)) as copy:
            assert copy.execute("SELECT value FROM records").fetchall() == [("original",)]
        assert db.execute("SELECT value FROM records").fetchall() == [("original",)]
    assert not list(root.glob(".sqlite-snapshot-*"))


def test_sqlite_is_never_copied_as_an_unverified_regular_file(tmp_path, public):
    source = tmp_path / "live.sqlite"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE records (value TEXT)")
    batch = capture_recovery_batch(tmp_path / "queue", "pc1", "sqlite", "2026-10-29",
                                   [source], public)
    assert batch["coverage"] == "PARTIAL"
    assert batch["entries"][0]["status"] == "UNAVAILABLE"


def test_retry_newly_available_sqlite_uses_online_snapshot(tmp_path, public):
    source, root = tmp_path / "later.sqlite", tmp_path / "queue"
    first = capture_recovery_batch(root, "pc", "source", "2026-10-30", [source], public)
    assert first["coverage"] == "PARTIAL"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE records(value TEXT)")
        db.execute("INSERT INTO records VALUES ('preserved')")
        db.commit()
        second = retry_partial_batch(root, first["batch_id"], public)
    assert second["coverage"] == "COMPLETE"
    assert second["entries"][0]["capture_method"] == "sqlite_online"
