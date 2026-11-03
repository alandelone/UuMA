import hashlib
import io
import json

import pytest

from uuma.librarian_crypto import MAGIC
from uuma.librarian_intake import DeviceGrant, receive_granted_object, serve_connection
from uuma.librarian_manifest_intake import MAX_MANIFEST_BYTES, receive_manifest
from uuma.librarian_publish import publish_batch


def _setup(tmp_path):
    grant = DeviceGrant("pc1", frozenset({"codex"}))
    payload = MAGIC + b"encrypted-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    receive_granted_object(io.BytesIO(payload), tmp_path, grant, "codex", len(payload), digest)
    manifest = {"schema_version": 1, "batch_id": "librarian:pc1:codex:2026-10-29",
                "device": "pc1", "source": "codex", "scheduled_date": "2026-10-29",
                "capture_kind": "encrypted_recovery_files", "revision": 1,
                "previous_manifest_sha256": None, "coverage": "COMPLETE",
                "entries": [{"status": "CAPTURED", "sha256": digest, "bytes": len(payload),
                             "encrypted": True, "source_path": "../../not-a-server-path"}]}
    return grant, manifest


def test_manifest_revision_chain_and_idempotent_replay(tmp_path):
    grant, manifest = _setup(tmp_path)
    raw = json.dumps(manifest, sort_keys=True).encode()
    first = receive_manifest(tmp_path, grant, "codex", raw)
    assert first["coverage"] == "COMPLETE" and not first["reused"]
    assert receive_manifest(tmp_path, grant, "codex", raw)["reused"]
    second = dict(manifest, revision=2, previous_manifest_sha256=hashlib.sha256(raw).hexdigest())
    assert receive_manifest(tmp_path, grant, "codex", json.dumps(second).encode())["revision"] == 2
    with pytest.raises(ValueError, match="Conflicting"):
        receive_manifest(tmp_path, grant, "codex", json.dumps(dict(manifest, extra=1)).encode())


def test_missing_object_or_false_coverage_cannot_commit(tmp_path):
    grant, manifest = _setup(tmp_path)
    manifest["entries"][0]["sha256"] = "a" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        receive_manifest(tmp_path, grant, "codex", json.dumps(manifest).encode())
    assert not (tmp_path / "recovery-intake.sqlite").exists()
    manifest["entries"] = [{"status": "UNAVAILABLE"}]
    with pytest.raises(ValueError, match="coverage"):
        receive_manifest(tmp_path, grant, "codex", json.dumps(manifest).encode())


def test_device_source_cannot_be_spoofed_and_history_cannot_skip(tmp_path):
    grant, manifest = _setup(tmp_path)
    other = dict(manifest, device="pc2")
    with pytest.raises(PermissionError):
        receive_manifest(tmp_path, grant, "codex", json.dumps(other).encode())
    later = dict(manifest, revision=2, previous_manifest_sha256="a" * 64)
    with pytest.raises(ValueError, match="history"):
        receive_manifest(tmp_path, grant, "codex", json.dumps(later).encode())


def test_revision_cannot_replace_original_captured_record(tmp_path):
    grant, manifest = _setup(tmp_path)
    raw = json.dumps(manifest).encode()
    receive_manifest(tmp_path, grant, "codex", raw)
    changed_entry = dict(manifest["entries"][0], source_path="a-different-original")
    revised = dict(manifest, revision=2, previous_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                   entries=[changed_entry])
    with pytest.raises(ValueError, match="source identity"):
        receive_manifest(tmp_path, grant, "codex", json.dumps(revised).encode())


def test_large_manifest_crosses_protocol_and_is_retained_by_publisher(tmp_path):
    intake, archive = tmp_path / "intake", tmp_path / "archive"
    intake.mkdir()
    archive.mkdir()
    grant, manifest = _setup(intake)
    manifest["coverage"] = "PARTIAL"
    manifest["entries"].extend(
        {"status": "UNAVAILABLE", "source_path": f"{i}/" + "x" * 900}
        for i in range(19000)
    )
    raw = json.dumps(manifest, sort_keys=True).encode()
    assert 16 * 1024 * 1024 < len(raw) < MAX_MANIFEST_BYTES
    digest = hashlib.sha256(raw).hexdigest()
    header = json.dumps({"action": "manifest", "source": "codex", "bytes": len(raw),
                         "sha256": digest}).encode() + b"\n"
    output = io.BytesIO()
    serve_connection(io.BytesIO(header + raw), output, intake, grant)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0] == {"status": "READY"}
    assert responses[1]["sha256"] == digest and responses[1]["coverage"] == "PARTIAL"
    result = publish_batch(intake, archive, manifest["batch_id"])
    assert result["sha256"] == digest and result["coverage"] == "PARTIAL"
    saved = list(archive.rglob("manifest-*.json"))
    assert len(saved) == 1 and saved[0].read_bytes() == raw


def test_oversized_manifest_is_rejected_before_body(tmp_path):
    grant, _ = _setup(tmp_path)
    header = json.dumps({"action": "manifest", "source": "codex",
                         "bytes": MAX_MANIFEST_BYTES + 1, "sha256": "a" * 64}).encode() + b"\n"
    output = io.BytesIO()
    serve_connection(io.BytesIO(header), output, tmp_path, grant)
    assert json.loads(output.getvalue()) == {"status": "REJECTED"}


def test_session_rejects_ungranted_source_and_stops(tmp_path):
    grant, _ = _setup(tmp_path)
    request = json.dumps({"source": "other", "bytes": 20, "sha256": "a" * 64}).encode() + b"\n"
    output = io.BytesIO()
    serve_connection(io.BytesIO(b'{"action":"session","version":1}\n' + request + request),
                     output, tmp_path, grant)
    assert [json.loads(line) for line in output.getvalue().splitlines()] == [
        {"status": "SESSION_READY", "version": 1}, {"status": "REJECTED"},
    ]
