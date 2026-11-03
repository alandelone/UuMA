"""Recovery key lifecycle; caller supplies a private user-owned storage directory."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import librarian_dpapi


def _fingerprint(public: rsa.RSAPublicKey) -> str:
    return hashlib.sha256(public.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )).hexdigest()


def initialize(directory: Path) -> str:
    """Create one current-user-protected key; never overwrite an existing directory.

    The caller must ensure the parent directory is accessible only to the owner.
    Interrupted initialization leaves its directory in place for explicit inspection.
    """
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    password = os.urandom(32)
    protected = librarian_dpapi.protect(password)
    encoded_private = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    for name, content in (("password.dpapi", protected), ("private.pem", encoded_private),
                          ("public.pem", public)):
        with (directory / name).open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    loaded = _load(directory)
    if _fingerprint(loaded.public_key()) != _fingerprint(private.public_key()):
        raise ValueError("Created recovery key failed its round-trip check")
    return _fingerprint(private.public_key())


def _load(directory: Path) -> rsa.RSAPrivateKey:
    directory = Path(directory)
    password = librarian_dpapi.unprotect((directory / "password.dpapi").read_bytes())
    private = serialization.load_pem_private_key((directory / "private.pem").read_bytes(), password)
    public = serialization.load_pem_public_key((directory / "public.pem").read_bytes())
    if not isinstance(private, rsa.RSAPrivateKey) or not isinstance(public, rsa.RSAPublicKey):
        raise TypeError("Invalid recovery key type")
    if private.key_size < 3072 or _fingerprint(private.public_key()) != _fingerprint(public):
        raise ValueError("Recovery private and public keys do not match")
    return private


def export_offline(directory: Path, destination: Path, password: bytes) -> str:
    """Export the same key with a user-supplied independent password, never overwrite."""
    if len(password) < 12:
        raise ValueError("Offline recovery password must contain at least 12 bytes")
    private = _load(directory)
    encoded = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    with Path(destination).open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    check = serialization.load_pem_private_key(Path(destination).read_bytes(), password)
    if not isinstance(check, rsa.RSAPrivateKey):
        raise TypeError("Exported recovery key is invalid")
    if _fingerprint(check.public_key()) != _fingerprint(private.public_key()):
        raise ValueError("Exported recovery key does not match")
    return _fingerprint(check.public_key())
