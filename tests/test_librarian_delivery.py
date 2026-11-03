import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_delivery import deliver_queued_batch
from uuma.librarian_queue import capture_recovery_batch, retry_partial_batch


def _public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_queue_change_during_delivery_never_marks_latest_revision_delivered(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "queue"
    source.write_bytes(b"fixture")
    batch = capture_recovery_batch(root, "pc1", "codex", "2026-10-29", [source], _public())
    monkeypatch.setattr("uuma.librarian_delivery.send_over_ssh", lambda *a, **kw: {})

    def mutate(raw, **kwargs):
        with closing(sqlite3.connect(root / "queue.sqlite")) as db:
            db.execute("UPDATE batches SET manifest_json=? WHERE batch_id=?", (raw.decode() + " ", batch["batch_id"]))
            db.commit()
        return {"status": "MANIFEST_RECEIVED"}

    monkeypatch.setattr("uuma.librarian_delivery.send_manifest_over_ssh", mutate)
    with pytest.raises(ValueError, match="changed during delivery"):
        deliver_queued_batch(root, batch["batch_id"], host="fixture", identity_file=tmp_path / "unused")
    with closing(sqlite3.connect(root / "queue.sqlite")) as db:
        assert db.execute("SELECT delivery_state FROM batches").fetchone()[0] == "PENDING"


@pytest.mark.skipif(os.name != "posix", reason="Server forced-command fixture uses POSIX policy")
@pytest.mark.parametrize("use_sessions", [False, True])
def test_real_stdio_delivers_partial_then_completed_revisions_in_order(tmp_path, monkeypatch, use_sessions):
    root, server = tmp_path / "queue", tmp_path / "server"
    server.mkdir(mode=0o700)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": 1, "intake_root": str(server),
                                  "devices": {"pc1": ["codex"]}}))
    policy.chmod(0o600)
    identity = tmp_path / "fake-key"
    identity.write_bytes(b"fixture")
    first, later = tmp_path / "first", tmp_path / "later"
    first.write_bytes(b"first original")
    public = _public()
    batch = capture_recovery_batch(root, "pc1", "codex", "2026-10-29", [first, later], public)
    later.write_bytes(b"arrived later")
    final = retry_partial_batch(root, batch["batch_id"], public)
    actual_popen = subprocess.Popen
    calls = []

    def launcher(command, **kwargs):
        assert command[0] == "ssh" and "StrictHostKeyChecking=yes" in command
        calls.append(command)
        return actual_popen([sys.executable, "-m", "uuma.librarian_ssh", "--policy", str(policy),
                             "--device", "pc1"], **kwargs)

    monkeypatch.setattr("uuma.librarian_transfer.subprocess.Popen", launcher)
    receipt = deliver_queued_batch(root, batch["batch_id"], host="fixture", identity_file=identity,
                                   timeout_seconds=15, bytes_per_second=1024 * 1024 * 1024,
                                   use_sessions=use_sessions)
    assert receipt["coverage"] == "COMPLETE" and receipt["revision"] == 2
    assert len(calls) == 4  # Two object transfers, two manifests; no repeated old object.
    with closing(sqlite3.connect(server / "recovery-intake.sqlite")) as db:
        assert db.execute("SELECT revision FROM manifest_revisions ORDER BY revision").fetchall() == [(1,), (2,)]
    with closing(sqlite3.connect(root / "queue.sqlite")) as db:
        assert db.execute("SELECT delivery_state FROM batches").fetchone()[0] == "DELIVERED"
    for entry in final["entries"]:
        assert (server / "pc1" / "codex" / entry["sha256"]).is_file()


@pytest.mark.skipif(os.name != "posix", reason="Server forced-command fixture uses POSIX policy")
def test_bounded_session_delivers_multiple_objects_without_losing_legacy_manifest(tmp_path, monkeypatch):
    root, server = tmp_path / "queue", tmp_path / "server"
    server.mkdir(mode=0o700)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": 1, "intake_root": str(server),
                                  "devices": {"pc1": ["codex"]}}))
    policy.chmod(0o600)
    identity = tmp_path / "fake-key"
    identity.write_bytes(b"fixture")
    files = []
    for index in range(3):
        path = tmp_path / f"source-{index}"
        path.write_text(f"fixture {index}")
        files.append(path)
    batch = capture_recovery_batch(root, "pc1", "codex", "2026-10-30", files, _public())
    actual_popen = subprocess.Popen
    calls = []

    def launcher(command, **kwargs):
        calls.append(command)
        return actual_popen([sys.executable, "-m", "uuma.librarian_ssh", "--policy", str(policy),
                             "--device", "pc1"], **kwargs)

    monkeypatch.setattr("uuma.librarian_transfer.subprocess.Popen", launcher)
    receipt = deliver_queued_batch(root, batch["batch_id"], host="fixture", identity_file=identity,
                                   timeout_seconds=15, bytes_per_second=1024 * 1024 * 1024,
                                   use_sessions=True)
    assert receipt["coverage"] == "COMPLETE"
    assert len(calls) == 2  # One negotiated object session and one legacy manifest frame.
    assert all((server / "pc1" / "codex" / entry["sha256"]).is_file() for entry in batch["entries"])
    with closing(sqlite3.connect(root / "queue.sqlite")) as db:
        assert db.execute("SELECT delivery_state FROM batches").fetchone()[0] == "DELIVERED"
