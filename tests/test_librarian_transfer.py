import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_crypto import MAGIC
from uuma.librarian_intake import DeviceGrant, serve_once
from uuma.librarian_queue import capture_recovery_batch
from uuma.librarian_transfer import send_manifest, send_object, send_over_ssh


def _fixture(tmp_path):
    file = tmp_path / "capsule"
    data = MAGIC + b"fake ciphertext"
    file.write_bytes(data)
    return file, data, hashlib.sha256(data).hexdigest()


def test_client_sends_scoped_frame_and_verifies_receipt(tmp_path):
    file, data, digest = _fixture(tmp_path)
    response = {"status": "RECEIVED", "device": "pc1", "source": "codex", "sha256": digest,
                "bytes": len(data), "reused": False}
    incoming = io.BytesIO(b'{"status":"READY"}\n' + json.dumps(response).encode() + b"\n")
    outgoing = io.BytesIO()
    receipt = send_object(incoming, outgoing, file, device="pc1", source="codex",
                          expected_digest=digest, bytes_per_second=1024 * 1024 * 1024)
    header, sent = outgoing.getvalue().split(b"\n", 1)
    assert json.loads(header) == {"source": "codex", "bytes": len(data), "sha256": digest}
    assert sent == data and not receipt["reused"]
    assert b"pc1" not in header and str(file).encode() not in header


def test_server_existing_receipt_prevents_retransmission(tmp_path):
    file, data, digest = _fixture(tmp_path)
    incoming = io.BytesIO(json.dumps({"status": "ALREADY_PRESENT", "sha256": digest,
                                     "bytes": len(data)}).encode() + b"\n")
    outgoing = io.BytesIO()
    assert send_object(incoming, outgoing, file, device="pc1", source="codex",
                       expected_digest=digest)["reused"]
    assert outgoing.getvalue().endswith(b"\n") and data not in outgoing.getvalue()


def test_mismatched_server_receipt_is_rejected(tmp_path):
    file, data, digest = _fixture(tmp_path)
    response = {"status": "RECEIVED", "device": "other", "source": "codex", "sha256": digest,
                "bytes": len(data), "reused": False}
    incoming = io.BytesIO(b'{"status":"READY"}\n' + json.dumps(response).encode() + b"\n")
    with pytest.raises(ValueError, match="receipt"):
        send_object(incoming, io.BytesIO(), file, device="pc1", source="codex", expected_digest=digest)


def test_rejects_unencrypted_and_untrusted_identity_before_writing(tmp_path):
    file = tmp_path / "source"
    file.write_bytes(b"plain original data")
    outgoing = io.BytesIO()
    with pytest.raises(ValueError):
        send_object(io.BytesIO(), outgoing, file, device="../escape", source="codex", expected_digest="a"*64)
    with pytest.raises(ValueError):
        send_object(io.BytesIO(), outgoing, file, device="pc1", source="codex", expected_digest="a"*64)
    assert outgoing.getvalue() == b""


def test_changed_capsule_is_rejected_before_sending_any_frame(tmp_path):
    file, _, _ = _fixture(tmp_path)
    outgoing = io.BytesIO()
    with pytest.raises(ValueError, match="frozen batch digest"):
        send_object(io.BytesIO(), outgoing, file, device="pc1", source="codex", expected_digest="a"*64)
    assert outgoing.getvalue() == b""


def test_real_duplex_protocol_retries_without_sending_data_twice(tmp_path):
    file, data, digest = _fixture(tmp_path)
    root = tmp_path / "server"
    root.mkdir()

    def exchange():
        client, server = socket.socketpair()
        client.settimeout(5)
        server.settimeout(5)

        def serve():
            with server, server.makefile("rb") as incoming, server.makefile("wb") as outgoing:
                serve_once(incoming, outgoing, root, DeviceGrant("pc1", frozenset({"codex"})))

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            with client, client.makefile("rb") as incoming, client.makefile("wb") as outgoing:
                receipt = send_object(incoming, outgoing, file, device="pc1", source="codex",
                                      expected_digest=digest, bytes_per_second=1024 * 1024 * 1024)
        finally:
            worker.join(timeout=5)
        assert not worker.is_alive()
        return receipt

    assert not exchange()["reused"]
    assert exchange()["reused"]
    assert (root / "pc1" / "codex" / digest).read_bytes() == data


def test_timed_out_owned_ssh_process_is_stopped(tmp_path, monkeypatch):
    file, _, digest = _fixture(tmp_path)
    key = tmp_path / "fake-ssh-key"
    key.write_bytes(b"fixture")
    actual_popen = subprocess.Popen
    launched = []

    def launcher(command, **kwargs):
        assert command[0] == "ssh" and "StrictHostKeyChecking=yes" in command
        process = actual_popen([sys.executable, "-c", "import time;time.sleep(30)"], **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr("uuma.librarian_transfer.subprocess.Popen", launcher)
    with pytest.raises(TimeoutError):
        send_over_ssh(file, device="pc1", source="codex", expected_digest=digest,
                      host="test-server", identity_file=key, timeout_seconds=0.3)
    assert len(launched) == 1 and launched[0].poll() is not None


@pytest.mark.skipif(os.name != "posix", reason="Server forced-command fixture uses POSIX policy")
def test_ssh_process_roundtrip_reuses_a_verified_object(tmp_path, monkeypatch):
    file, data, digest = _fixture(tmp_path)
    key = tmp_path / "fake-ssh-key"
    key.write_bytes(b"fixture")
    root = tmp_path / "intake"
    root.mkdir(mode=0o700)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": 1, "intake_root": str(root),
                                  "devices": {"pc1": ["codex"]}}))
    policy.chmod(0o600)
    actual_popen = subprocess.Popen

    def launcher(command, **kwargs):
        assert command[0] == "ssh" and "IdentitiesOnly=yes" in command
        return actual_popen([sys.executable, "-m", "uuma.librarian_ssh", "--policy", str(policy),
                             "--device", "pc1"], **kwargs)

    monkeypatch.setattr("uuma.librarian_transfer.subprocess.Popen", launcher)
    kwargs = {"device": "pc1", "source": "codex", "expected_digest": digest,
              "host": "test-server", "identity_file": key, "timeout_seconds": 15,
              "bytes_per_second": 1024 * 1024 * 1024}
    assert not send_over_ssh(file, **kwargs)["reused"]
    assert send_over_ssh(file, **kwargs)["reused"]
    assert (root / "pc1" / "codex" / digest).read_bytes() == data


def test_complete_batch_moves_objects_before_private_manifest(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    source = tmp_path / "source"
    source.write_bytes(b"fixture secret")
    queue, root = tmp_path / "queue", tmp_path / "server"
    root.mkdir()
    manifest = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", [source], public)
    with closing(sqlite3.connect(queue / "queue.sqlite")) as db:
        raw = db.execute("SELECT manifest_json FROM batches WHERE batch_id=?",
                         (manifest["batch_id"],)).fetchone()[0].encode()

    def exchange(operation):
        client, server = socket.socketpair()
        client.settimeout(5)
        server.settimeout(5)

        def serve():
            with server, server.makefile("rb") as incoming, server.makefile("wb") as outgoing:
                serve_once(incoming, outgoing, root, DeviceGrant("pc1", frozenset({"codex"})))

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            with client, client.makefile("rb") as incoming, client.makefile("wb") as outgoing:
                return operation(incoming, outgoing)
        finally:
            worker.join(timeout=5)
            assert not worker.is_alive()

    with pytest.raises(ValueError, match="receipt"):
        exchange(lambda incoming, outgoing: send_manifest(incoming, outgoing, raw,
                                                           device="pc1", source="codex"))
    assert not (root / "recovery-intake.sqlite").exists()
    entry = manifest["entries"][0]
    receipt = exchange(lambda incoming, outgoing: send_object(
        incoming, outgoing, queue / entry["object_ref"], device="pc1", source="codex",
        expected_digest=entry["sha256"], bytes_per_second=1024 * 1024 * 1024,
    ))
    assert not receipt["reused"]
    accepted = exchange(lambda incoming, outgoing: send_manifest(incoming, outgoing, raw,
                                                                 device="pc1", source="codex"))
    assert accepted["coverage"] == "COMPLETE" and accepted["revision"] == 1
    assert exchange(lambda incoming, outgoing: send_manifest(incoming, outgoing, raw,
                                                               device="pc1", source="codex"))["reused"]
