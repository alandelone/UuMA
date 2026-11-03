import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import uuma.librarian_packed_recovery as packed
from uuma.librarian_crypto import recover
from uuma.librarian_intake import DeviceGrant, receive_granted_object
from uuma.librarian_manifest_intake import receive_manifest
from uuma.librarian_queue import capture_recovery_batch, retry_partial_batch


def _setup(tmp_path):
    queue, intake, archive = tmp_path / "queue", tmp_path / "intake", tmp_path / "packed"
    intake.mkdir()
    archive.mkdir()
    files = []
    for number in range(3):
        path = tmp_path / f"source-{number}"
        path.write_bytes(f"original {number}".encode())
        files.append(path)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    private_pem = private.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.PKCS8,
                                        serialization.BestAvailableEncryption(b"fixture-password"))
    batch = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", files, public)
    grant = DeviceGrant("pc1", frozenset({"codex"}))
    for item in batch["entries"]:
        with (queue / item["object_ref"]).open("rb") as stream:
            receive_granted_object(stream, intake, grant, "codex", item["bytes"], item["sha256"])
    raw = json.dumps(batch, sort_keys=True).encode()
    receive_manifest(intake, grant, "codex", raw)
    return intake, archive, batch, private_pem


def test_packed_archive_restores_original_and_preserves_v1_ledger(tmp_path, monkeypatch):
    intake, archive, batch, private = _setup(tmp_path)
    monkeypatch.setattr(packed, "PACK_FILES", 2)
    receipt = packed.publish_packed_batch(intake, archive, batch["batch_id"])
    assert receipt["coverage"] == "COMPLETE" and receipt["objects"] == 3
    assert not (intake / "recovery-publication.sqlite").exists()
    directory = archive / "pc1" / "codex" / "2026-10-29"
    assert len(list(directory.glob("pack-*.zip"))) == 2
    pointer = packed.read_packed_receipt(directory, receipt["manifest_sha256"])
    assert pointer["map_sha256"] == receipt["map_sha256"] and pointer["batch_id"] == batch["batch_id"]
    capsule, plain = tmp_path / "restored.capsule", tmp_path / "restored.txt"
    packed.extract_packed_capsule(directory, manifest_sha256=receipt["manifest_sha256"],
                                  map_sha256=receipt["map_sha256"],
                                  object_sha256=batch["entries"][1]["sha256"], destination=capsule)
    recover(capsule, plain, private, b"fixture-password")
    assert plain.read_bytes() == b"original 1"
    assert packed.publish_packed_batch(intake, archive, batch["batch_id"]) == receipt
    with pytest.raises(FileExistsError):
        packed.extract_packed_capsule(directory, manifest_sha256=receipt["manifest_sha256"],
                                      map_sha256=receipt["map_sha256"],
                                      object_sha256=batch["entries"][1]["sha256"], destination=capsule)


def test_interrupted_pack_has_no_manifest_and_retries_without_losing_first_pack(tmp_path, monkeypatch):
    intake, archive, batch, _private = _setup(tmp_path)
    monkeypatch.setattr(packed, "PACK_FILES", 1)
    original = packed._write_pack
    calls = []

    def stop_after_first(directory, objects):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("fixture interrupt")
        return original(directory, objects)

    monkeypatch.setattr(packed, "_write_pack", stop_after_first)
    with pytest.raises(OSError, match="fixture interrupt"):
        packed.publish_packed_batch(intake, archive, batch["batch_id"])
    directory = archive / "pc1" / "codex" / "2026-10-29"
    original_pack = next(directory.glob("pack-*.zip"))
    original_bytes = original_pack.read_bytes()
    assert not list(directory.glob("manifest-*.json"))
    (intake / "pc1" / "codex" / batch["entries"][0]["sha256"]).unlink()
    monkeypatch.setattr(packed, "_write_pack", original)
    result = packed.publish_packed_batch(intake, archive, batch["batch_id"])
    assert result["objects"] == 3 and original_pack.read_bytes() == original_bytes
    assert len(list(directory.glob("pack-*.zip"))) == 3


def test_restore_rejects_tampered_pack_or_unlisted_object(tmp_path):
    intake, archive, batch, _private = _setup(tmp_path)
    receipt = packed.publish_packed_batch(intake, archive, batch["batch_id"])
    directory = archive / "pc1" / "codex" / "2026-10-29"
    mapping = json.loads((directory / f"pack-map-{receipt['map_sha256']}.json").read_bytes())
    item = batch["entries"][0]
    pack = directory / f"pack-{mapping['objects'][item['sha256']]['pack_sha256']}.zip"
    pack.write_bytes(pack.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="pack failed"):
        packed.extract_packed_capsule(directory, manifest_sha256=receipt["manifest_sha256"],
                                      map_sha256=receipt["map_sha256"], object_sha256=item["sha256"],
                                      destination=tmp_path / "bad")
    with pytest.raises(ValueError, match="not in"):
        packed.extract_packed_capsule(directory, manifest_sha256=receipt["manifest_sha256"],
                                      map_sha256=receipt["map_sha256"], object_sha256="a" * 64,
                                      destination=tmp_path / "missing")
    assert not (tmp_path / "bad").exists() and not (tmp_path / "missing").exists()


def test_partial_and_later_revision_remain_independently_recoverable(tmp_path):
    queue, intake, archive = tmp_path / "queue", tmp_path / "intake", tmp_path / "packed"
    intake.mkdir()
    archive.mkdir()
    first, missing = tmp_path / "first", tmp_path / "missing"
    first.write_bytes(b"first original")
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    batch = capture_recovery_batch(queue, "pc1", "codex", "2026-10-29", [first, missing], public)
    grant = DeviceGrant("pc1", frozenset({"codex"}))

    def receive(value):
        for item in value["entries"]:
            if item["status"] == "CAPTURED":
                with (queue / item["object_ref"]).open("rb") as stream:
                    receive_granted_object(stream, intake, grant, "codex", item["bytes"], item["sha256"])
        return receive_manifest(intake, grant, "codex", json.dumps(value, sort_keys=True).encode())

    first_receipt = receive(batch)
    partial = packed.publish_packed_batch(intake, archive, batch["batch_id"])
    assert partial["coverage"] == "PARTIAL" and partial["revision"] == 1
    missing.write_bytes(b"arrived later")
    final = retry_partial_batch(queue, batch["batch_id"], public)
    receive(final)
    complete = packed.publish_packed_batch(intake, archive, batch["batch_id"])
    assert complete["coverage"] == "COMPLETE" and complete["revision"] == 2
    directory = archive / "pc1" / "codex" / "2026-10-29"
    assert len(list(directory.glob("manifest-*.json"))) == 2
    destination = tmp_path / "prior-capsule"
    packed.extract_packed_capsule(directory, manifest_sha256=first_receipt["sha256"],
                                  map_sha256=partial["map_sha256"], object_sha256=batch["entries"][0]["sha256"],
                                  destination=destination)
    assert destination.read_bytes() == (queue / batch["entries"][0]["object_ref"]).read_bytes()
