"""Streaming, authenticated recovery capsules; private keys never belong on the NAS."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"UUMA-LIBRARIAN-1\n"
CHUNK = 1024 * 1024


def _oaep() -> padding.OAEP:
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def _read_exact(stream: BinaryIO, count: int) -> bytes:
    result = stream.read(count)
    if len(result) != count:
        raise ValueError("Truncated recovery capsule")
    return result


def seal(
    source: Path, destination: Path, public_pem: bytes, *, bytes_per_second: int | None = None,
) -> dict[str, object]:
    """Encrypt a file with AES-256-GCM and RSA-OAEP; publish without overwriting."""
    if bytes_per_second is not None and (
        type(bytes_per_second) is not int or not 1 <= bytes_per_second <= 1024 * 1024 * 1024
    ):
        raise ValueError("Invalid capture bandwidth")
    started = time.monotonic()
    processed = 0

    def throttle(count: int) -> None:
        nonlocal processed
        processed += count
        if bytes_per_second is not None:
            remaining = processed / bytes_per_second - (time.monotonic() - started)
            while remaining > 0:
                time.sleep(min(remaining, 1.0))
                remaining = processed / bytes_per_second - (time.monotonic() - started)

    public = serialization.load_pem_public_key(public_pem)
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise ValueError("Recovery public key must be RSA with at least 3072 bits")
    key, nonce = os.urandom(32), os.urandom(12)
    header = json.dumps({
        "algorithm": "AES-256-GCM+RSA-OAEP-SHA256",
        "key": base64.b64encode(public.encrypt(key, _oaep())).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "key_fingerprint": hashlib.sha256(public.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
        )).hexdigest(),
    }, sort_keys=True).encode("ascii")
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    # The destination is a pending object; only a returned receipt makes it deliverable.
    # Failed ciphertext stays uncommitted for diagnosis, without a success receipt.
    with Path(source).open("rb") as inp, destination.open("xb") as out:
        out.write(prefix)
        for chunk in iter(lambda: inp.read(CHUNK), b""):
            out.write(encryptor.update(chunk))
            throttle(len(chunk))
        out.write(encryptor.finalize())
        out.write(encryptor.tag)
        out.flush()
        os.fsync(out.fileno())
    digest = hashlib.sha256()
    with destination.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
            throttle(len(chunk))
    return {"sha256": digest.hexdigest(), "bytes": destination.stat().st_size,
            "encrypted": True, "key_fingerprint": json.loads(header)["key_fingerprint"]}


def recover(capsule: Path, destination: Path, private_pem: bytes, password: bytes) -> None:
    """Publish plaintext only after authentication. Never replace an existing destination."""
    private = serialization.load_pem_private_key(private_pem, password=password)
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 3072:
        raise ValueError("Invalid recovery private key")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    fd, name = tempfile.mkstemp(prefix=".librarian-recover-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as out, Path(capsule).open("rb") as inp:
            magic = _read_exact(inp, len(MAGIC))
            if magic != MAGIC:
                raise ValueError("Unsupported recovery capsule")
            encoded_size = _read_exact(inp, 4)
            header_size = struct.unpack(">I", encoded_size)[0]
            if not 1 <= header_size <= 8192:
                raise ValueError("Invalid capsule header size")
            header = _read_exact(inp, header_size)
            metadata = json.loads(header)
            if set(metadata) != {"algorithm", "key", "nonce", "key_fingerprint"} or (
                metadata["algorithm"] != "AES-256-GCM+RSA-OAEP-SHA256"
            ):
                raise ValueError("Unsupported capsule header")
            fingerprint = hashlib.sha256(private.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
            )).hexdigest()
            if metadata["key_fingerprint"] != fingerprint:
                raise ValueError("Recovery key fingerprint mismatch")
            key = private.decrypt(base64.b64decode(metadata["key"], validate=True), _oaep())
            nonce = base64.b64decode(metadata["nonce"], validate=True)
            if len(key) != 32 or len(nonce) != 12:
                raise ValueError("Invalid capsule encryption parameters")
            start = inp.tell()
            end = inp.seek(0, os.SEEK_END)
            remaining = end - start - 16
            if remaining < 0:
                raise ValueError("Missing capsule authentication tag")
            inp.seek(end - 16)
            tag = _read_exact(inp, 16)
            inp.seek(start)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(magic + encoded_size + header)
            while remaining:
                chunk = _read_exact(inp, min(CHUNK, remaining))
                out.write(decryptor.update(chunk))
                remaining -= len(chunk)
            out.write(decryptor.finalize())
            out.flush()
            os.fsync(out.fileno())
        # Exclusive hard-link publication is local-only, never used on the NAS/SMB path.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
