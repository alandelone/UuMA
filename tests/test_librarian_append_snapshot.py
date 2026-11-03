import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma import librarian_append_snapshot as snapshots
from uuma.librarian_crypto import recover
from uuma.librarian_queue import capture_recovery_batch, retry_partial_batch


def test_active_jsonl_append_preserves_verified_prefix_and_restores(tmp_path, monkeypatch):
    source = tmp_path / "history.jsonl"
    original = b'{"message":"first"}\n'
    source.write_bytes(original)
    verify = snapshots._prefix_hash

    def append_before_verify(stream, size, throttle):
        with source.open("ab") as out:
            out.write(b'{"message":"later"}\n')
        return verify(stream, size, throttle)

    monkeypatch.setattr(snapshots, "_prefix_hash", append_before_verify)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    password = b"fixture-recovery-password"
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.BestAvailableEncryption(password))
    root = tmp_path / "queue"
    batch = capture_recovery_batch(root, "pc", "codex", "2026-10-30", [source], public,
                                   append_only_paths=frozenset({source}))
    entry = batch["entries"][0]
    assert batch["coverage"] == "COMPLETE"
    assert entry["snapshot_bytes"] == len(original)
    assert entry["snapshot_cutoff_observed_at"] <= entry["actual_captured_at"]
    assert entry["snapshot_semantics"] == "verified-complete-jsonl-prefix"
    restored = tmp_path / "restored.jsonl"
    recover(root / entry["object_ref"], restored, pem, password)
    assert restored.read_bytes() == original
    assert source.read_bytes() == original + b'{"message":"later"}\n'


def test_prefix_change_or_incomplete_line_never_passes(tmp_path, monkeypatch):
    source = tmp_path / "history.jsonl"
    source.write_bytes(b'{"old":1}\n')
    verify = snapshots._prefix_hash

    def rewrite_before_verify(stream, size, throttle):
        source.write_bytes(b'{"new":2}\n')
        return verify(stream, size, throttle)

    monkeypatch.setattr(snapshots, "_prefix_hash", rewrite_before_verify)
    with pytest.raises(ValueError, match="prefix changed"):
        snapshots.snapshot_append_only_jsonl(source, tmp_path / "snapshot.jsonl")
    monkeypatch.setattr(snapshots, "_prefix_hash", verify)
    source.write_bytes(b'{"incomplete":')
    with pytest.raises(ValueError, match="incomplete"):
        snapshots.snapshot_append_only_jsonl(source, tmp_path / "incomplete.jsonl")


def test_partial_retry_can_change_only_unavailable_jsonl_method(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    existing, later = tmp_path / "existing.txt", tmp_path / "later.jsonl"
    existing.write_text("keep", encoding="utf-8")
    root = tmp_path / "queue"
    first = capture_recovery_batch(root, "pc", "codex", "2026-10-30", [existing, later], public)
    later.write_text('{"arrived":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unavailable JSONL"):
        retry_partial_batch(root, first["batch_id"], public, append_only_paths=frozenset({existing}))
    second = retry_partial_batch(root, first["batch_id"], public, append_only_paths=frozenset({later}))
    assert second["coverage"] == "COMPLETE" and second["revision"] == 2
    assert second["entries"][0] == first["entries"][0]
    assert second["entries"][1]["capture_method"] == "append_only_jsonl"
    assert not list(root.glob(".jsonl-snapshot-*"))
