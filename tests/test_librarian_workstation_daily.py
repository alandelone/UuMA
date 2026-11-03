import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_workstation_daily import run_sources


@pytest.fixture(scope="module")
def public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_tree_capture_is_reused_without_reopening_the_source(tmp_path, public, monkeypatch):
    queue, tree = tmp_path / "queue", tmp_path / "tree"
    queue.mkdir()
    tree.mkdir()
    (tree / "history.jsonl").write_text("original fixture")
    spec = {"source_id": "history", "kind": "tree", "path": str(tree)}
    calls = []

    def delivered(root, batch_id, **kwargs):
        calls.append(batch_id)
        with closing(sqlite3.connect(root / "queue.sqlite")) as db:
            row = db.execute("SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            db.execute("UPDATE batches SET delivery_state='DELIVERED' WHERE batch_id=?", (batch_id,))
            db.commit()
        return {"sha256": hashlib.sha256(row[0].encode()).hexdigest()}

    monkeypatch.setattr("uuma.librarian_workstation_daily.deliver_queued_batch", delivered)
    kwargs = {"queue": queue, "public_pem": public, "device": "pc1", "host": "fixture",
              "ssh_identity": tmp_path / "unused", "now": datetime(2026, 10, 30, 0, tzinfo=UTC)}
    first = run_sources([spec], **kwargs)
    assert first["incomplete"] == 0 and first["sources"][0]["intake_checked_live"]
    retained = {p: p.read_bytes() for p in queue.rglob("*.capsule")}
    (tree / "history.jsonl").write_text("later change")
    second = run_sources([spec], **kwargs)
    assert second["incomplete"] == 0 and not second["sources"][0]["intake_checked_live"]
    assert len(calls) == 1
    assert retained == {p: p.read_bytes() for p in queue.rglob("*.capsule")}


def test_offline_batch_stays_pending_and_old_batch_is_retried(tmp_path, public, monkeypatch):
    queue = tmp_path / "queue"
    queue.mkdir()
    file = tmp_path / "history"
    file.write_bytes(b"fixture")
    spec = {"source_id": "history", "kind": "file", "path": str(file)}
    calls = []

    def offline(root, batch_id, **kwargs):
        calls.append(batch_id)
        raise OSError("fixture offline")

    monkeypatch.setattr("uuma.librarian_workstation_daily.deliver_queued_batch", offline)
    kwargs = {"queue": queue, "public_pem": public, "device": "pc1", "host": "fixture",
              "ssh_identity": tmp_path / "unused"}
    first = run_sources([spec], **kwargs, now=datetime(2026, 10, 29, 0, tzinfo=UTC))
    assert first["incomplete"] == 1 and first["sources"][0]["server_intake"] == "PENDING"
    second = run_sources([spec], **kwargs, now=datetime(2026, 10, 30, 0, tzinfo=UTC))
    assert second["older_pending_before_retry"] == 1 and second["older_batches_delivered"] == 0
    assert calls[-1].endswith("2026-10-29")
    with closing(sqlite3.connect(queue / "queue.sqlite")) as db:
        assert db.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 2


def test_bad_identity_is_rejected_before_queue_writes(tmp_path, public):
    queue = tmp_path / "queue"
    queue.mkdir()
    spec = {"source_id": "../bad", "kind": "file", "path": str(tmp_path / "file")}
    with pytest.raises(ValueError):
        run_sources([spec], queue=queue, public_pem=public, device="pc1", host="fixture",
                    ssh_identity=tmp_path / "unused")
    assert list(queue.iterdir()) == []
