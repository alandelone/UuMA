import json
import sqlite3
import sys
from contextlib import closing

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import uuma.librarian_publish as publisher
from uuma.librarian_intake import DeviceGrant, receive_granted_object
from uuma.librarian_manifest_intake import receive_manifest
from uuma.librarian_publish import _check_io_pressure, publish_batch
from uuma.librarian_publish_runner import publish_pending
from uuma.librarian_queue import capture_recovery_batch, retry_partial_batch


def _receive(root, intake, manifest):
    grant = DeviceGrant("pc1", frozenset({"codex"}))
    for entry in manifest["entries"]:
        if entry["status"] == "CAPTURED":
            with (root / entry["object_ref"]).open("rb") as data:
                receive_granted_object(data, intake, grant, "codex", entry["bytes"], entry["sha256"])
    raw = json.dumps(manifest, sort_keys=True).encode()
    return receive_manifest(intake, grant, "codex", raw)


def test_publisher_retains_every_revision_and_reuses_verified_objects(tmp_path):
    queue, intake, archive = tmp_path / "queue", tmp_path / "intake", tmp_path / "recovery"
    intake.mkdir()
    archive.mkdir()
    first, missing = tmp_path / "first", tmp_path / "missing"
    first.write_bytes(b"first fixture")
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    batch = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", [first, missing], public)
    _receive(queue, intake, batch)
    partial = publish_batch(intake, archive, batch["batch_id"])
    assert partial["coverage"] == "PARTIAL" and partial["revision"] == 1
    initial_files = {p: p.read_bytes() for p in archive.rglob("*") if p.is_file()}
    assert publish_pending(intake, archive)["attempted"] == 0
    missing.write_bytes(b"late fixture")
    final = retry_partial_batch(queue, batch["batch_id"], public)
    _receive(queue, intake, final)
    pending = publish_pending(intake, archive)
    assert pending["attempted"] == 1 and pending["failed"] == 0
    complete = pending["results"][0]
    assert complete["coverage"] == "COMPLETE" and complete["revision"] == 2
    assert all(path.read_bytes() == content for path, content in initial_files.items())
    assert len(list(archive.rglob("manifest-*.json"))) == 2
    assert publish_batch(intake, archive, batch["batch_id"]) == complete
    with closing(sqlite3.connect(intake / "recovery-publication.sqlite")) as db:
        assert db.execute("SELECT revision FROM publications ORDER BY revision").fetchall() == [(1,), (2,)]


def test_invalid_batch_does_not_write_archive(tmp_path):
    intake, archive = tmp_path / "intake", tmp_path / "recovery"
    intake.mkdir()
    archive.mkdir()
    with pytest.raises(ValueError):
        publish_batch(intake, archive, "librarian:../escape:codex:2026-10-29")
    assert list(archive.iterdir()) == []


def test_pending_scan_does_not_initialize_missing_intake(tmp_path):
    intake, archive = tmp_path / "intake", tmp_path / "archive"
    intake.mkdir()
    archive.mkdir()
    with pytest.raises(FileNotFoundError):
        publish_pending(intake, archive)
    assert list(intake.iterdir()) == [] and list(archive.iterdir()) == []


def test_pressure_deferral_preserves_first_group_and_resumes_without_manifest(tmp_path, monkeypatch):
    queue, intake, archive = tmp_path / "queue", tmp_path / "intake", tmp_path / "archive"
    intake.mkdir()
    archive.mkdir()
    files = []
    for index in range(3):
        file = tmp_path / f"source-{index}"
        file.write_text(f"fixture {index}")
        files.append(file)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    batch = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", files, public)
    _receive(queue, intake, batch)
    monkeypatch.setattr("uuma.librarian_publish.GROUP_FILES", 1)
    checks = []

    def pressure():
        checks.append(1)
        if len(checks) == 2:
            raise BlockingIOError("fixture I/O pressure")

    monkeypatch.setattr("uuma.librarian_publish._check_io_pressure", pressure)
    with pytest.raises(BlockingIOError):
        publish_batch(intake, archive, batch["batch_id"])
    objects = archive / "pc1" / "codex" / "2026-10-29" / "objects"
    retained = {p.name: p.read_bytes() for p in objects.iterdir()}
    assert len(retained) == 1 and not list(archive.rglob("manifest-*.json"))
    monkeypatch.setattr("uuma.librarian_publish._check_io_pressure", lambda: None)
    assert publish_batch(intake, archive, batch["batch_id"])["coverage"] == "COMPLETE"
    assert all((objects / name).read_bytes() == value for name, value in retained.items())
    assert len(list(archive.rglob("manifest-*.json"))) == 1


def test_configured_io_pressure_limit_defers_publication(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("UUMA_LIBRARIAN_IO_PRESSURE_LIMIT", "20")
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs:
                        "some avg10=21.50 avg60=7.00 avg300=2.00 total=1\n")
    with pytest.raises(BlockingIOError):
        _check_io_pressure()
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs:
                        "some avg10=1.50 avg60=7.00 avg300=2.00 total=1\n")
    _check_io_pressure()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux syncfs is required")
def test_linux_syncs_bounded_groups_before_manifest_and_survives_sync_failure(tmp_path, monkeypatch):
    queue, intake, archive = tmp_path / "queue", tmp_path / "intake", tmp_path / "archive"
    intake.mkdir()
    archive.mkdir()
    files = []
    for index in range(5):
        file = tmp_path / f"file-{index}"
        file.write_text(f"fixture {index}")
        files.append(file)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    batch = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", files, public)
    _receive(queue, intake, batch)
    monkeypatch.setattr(publisher, "GROUP_FILES", 2)
    original_sync = publisher._sync_filesystem
    calls = []

    def failing_sync(path):
        calls.append(path)
        raise OSError("fixture flush failure")

    monkeypatch.setattr(publisher, "_sync_filesystem", failing_sync)
    with pytest.raises(OSError, match="flush failure"):
        publish_batch(intake, archive, batch["batch_id"])
    assert not list(archive.rglob("manifest-*.json"))
    assert len(list(archive.rglob(".pending-*"))) == 2
    calls.clear()

    def tracked_sync(path):
        calls.append(path)
        original_sync(path)

    monkeypatch.setattr(publisher, "_sync_filesystem", tracked_sync)
    assert publish_batch(intake, archive, batch["batch_id"])["coverage"] == "COMPLETE"
    assert len(calls) == 3  # Five objects flush in groups of two, two and one.
    assert len(list(archive.rglob("manifest-*.json"))) == 1
