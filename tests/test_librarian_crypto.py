import hashlib

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_crypto import recover, seal


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    secret = b"fixture-password-only"
    return (
        private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(secret),
        ),
        secret,
    )


@pytest.mark.parametrize("size", [0, 1, 2 * 1024 * 1024 + 53])
def test_capsule_roundtrip_and_no_overwrite(tmp_path, keys, size):
    public, private, secret = keys
    original = tmp_path / "original"
    payload = (b"private-source\x00" * (size // 15 + 1))[:size]
    original.write_bytes(payload)
    capsule = tmp_path / "encrypted"
    receipt = seal(original, capsule, public)
    assert receipt["sha256"] == hashlib.sha256(capsule.read_bytes()).hexdigest()
    restored = tmp_path / "restored"
    recover(capsule, restored, private, secret)
    assert restored.read_bytes() == payload
    with pytest.raises(FileExistsError):
        seal(original, capsule, public)
    with pytest.raises(FileExistsError):
        recover(capsule, restored, private, secret)
    assert restored.read_bytes() == payload


@pytest.mark.parametrize("damage", ["tag", "header", "truncate"])
def test_damage_never_publishes_plaintext(tmp_path, keys, damage):
    public, private, secret = keys
    original = tmp_path / "original"
    original.write_bytes(b"retained secret")
    capsule = tmp_path / "capsule"
    seal(original, capsule, public)
    raw = bytearray(capsule.read_bytes())
    if damage == "tag":
        raw[-1] ^= 1
    elif damage == "header":
        raw[0] ^= 1
    else:
        raw = raw[:12]
    capsule.write_bytes(raw)
    with pytest.raises((ValueError, InvalidTag)):
        recover(capsule, tmp_path / "restored", private, secret)
    assert not (tmp_path / "restored").exists()
    assert not list(tmp_path.glob(".librarian-recover-*"))


def test_wrong_password_cannot_restore(tmp_path, keys):
    public, private, _ = keys
    original = tmp_path / "original"
    original.write_bytes(b"secret")
    capsule = tmp_path / "capsule"
    seal(original, capsule, public)
    with pytest.raises(ValueError):
        recover(capsule, tmp_path / "restored", private, b"wrong")
    assert not (tmp_path / "restored").exists()


def test_invalid_capture_bandwidth_is_rejected_before_writing(tmp_path, keys):
    public, _, _ = keys
    source = tmp_path / "source"
    source.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="bandwidth"):
        seal(source, tmp_path / "capsule", public, bytes_per_second=0)
    assert not (tmp_path / "capsule").exists()
