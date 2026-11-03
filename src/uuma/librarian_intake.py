"""Verified immutable encrypted-object intake for a trusted server-side caller.

This module is not an SSH endpoint, identity registry, or production publisher.
The transport must bind the device identity and destination before invoking it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .librarian_crypto import MAGIC

MAX_OBJECT_BYTES = 64 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
MAX_HEADER_BYTES = 4096
MAX_SESSION_REQUESTS = 256


@dataclass(frozen=True)
class DeviceGrant:
    """A grant selected by the authenticated server launcher, never by a peer."""

    device: str
    sources: frozenset[str]


def receive_granted_object(
    stream: BinaryIO, intake_root: Path, grant: DeviceGrant, source: str,
    expected_size: int, expected_digest: str,
) -> dict[str, object]:
    """Bind an encrypted transfer to a server-selected device and source grant.

    This does not authenticate a network peer: the future SSH launcher must select
    `grant` from server-owned configuration for the already authenticated key.
    """
    if (not IDENTITY.fullmatch(grant.device) or not IDENTITY.fullmatch(source)
            or source not in grant.sources or any(not IDENTITY.fullmatch(s) for s in grant.sources)):
        raise PermissionError("Device is not granted this source")
    root = Path(intake_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Intake root must be an existing private directory")
    directory = root
    for component in (grant.device, source):
        directory = directory / component
        if directory.is_symlink():
            raise ValueError("Intake scope cannot be a symbolic link")
        directory.mkdir(exist_ok=True)
        if not directory.resolve(strict=True).is_relative_to(root):
            raise ValueError("Intake scope escaped its configured root")
    return receive_object(stream, directory, expected_size, expected_digest) | {
        "device": grant.device, "source": source,
    }


def serve_once(
    incoming: BinaryIO, outgoing: BinaryIO, intake_root: Path, grant: DeviceGrant,
    *, first_header: bytes | None = None,
) -> bool:
    """Serve one bounded transfer using a device grant supplied by a trusted launcher.

    A READY/ALREADY_PRESENT handshake lets clients avoid resending retained objects.
    The transport must enforce connection and transfer deadlines outside this function.
    """
    def reply(value: dict[str, object]) -> None:
        outgoing.write(json.dumps(value, sort_keys=True).encode("utf-8") + b"\n")
        outgoing.flush()

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate request key")
            result[key] = value
        return result

    try:
        raw = first_header if first_header is not None else incoming.readline(MAX_HEADER_BYTES + 1)
        if len(raw) > MAX_HEADER_BYTES or not raw.endswith(b"\n"):
            raise ValueError("Invalid request frame")
        request = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(request, dict):
            raise TypeError("Invalid request fields")
        action = request.get("action", "object")
        expected_fields = {"source", "bytes", "sha256"}
        if action == "manifest":
            expected_fields.add("action")
        elif action != "object":
            raise ValueError("Invalid request action")
        if set(request) != expected_fields:
            raise ValueError("Invalid request fields")
        source, size, digest = request["source"], request["bytes"], request["sha256"]
        if (not isinstance(source, str) or not IDENTITY.fullmatch(source)
                or not IDENTITY.fullmatch(grant.device) or source not in grant.sources
                or any(not IDENTITY.fullmatch(item) for item in grant.sources)):
            raise PermissionError("Device is not granted this source")
        if type(size) is not int or not 1 <= size <= MAX_OBJECT_BYTES:
            raise ValueError("Invalid encrypted object size")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid encrypted object digest")
        root = Path(intake_root).resolve(strict=True)
        directory = root
        for component in (grant.device, source):
            directory = directory / component
            if directory.is_symlink():
                raise ValueError("Intake scope cannot be a symbolic link")
            directory.mkdir(exist_ok=True)
            if not directory.resolve(strict=True).is_relative_to(root):
                raise ValueError("Intake scope escaped its configured root")
        if action == "manifest":
            from .librarian_manifest_intake import MAX_MANIFEST_BYTES, receive_manifest

            if size > MAX_MANIFEST_BYTES:
                raise ValueError("Manifest exceeds private intake limits")
            reply({"status": "READY"})
            content = bytearray()
            while len(content) < size:
                chunk = incoming.read(min(CHUNK, size - len(content)))
                if not chunk or len(chunk) > size - len(content):
                    raise ValueError("Manifest transfer is truncated or exceeds its frame")
                content.extend(chunk)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Manifest digest mismatch")
            result = receive_manifest(root, grant, source, bytes(content))
            reply({"status": "MANIFEST_RECEIVED", **result})
            return True
        if size < len(MAGIC):
            raise ValueError("Invalid encrypted object size")
        existing = directory / digest
        if existing.exists() or existing.is_symlink():
            if not _verify(existing, size, digest):
                raise ValueError("Existing intake object does not match its address")
            reply({"status": "ALREADY_PRESENT", "sha256": digest, "bytes": size})
            return True
        reply({"status": "READY"})
        result = receive_granted_object(incoming, root, grant, source, size, digest)
        reply({"status": "RECEIVED", **result})
        return True
    except (OSError, ValueError, TypeError, PermissionError, UnicodeError):
        # Do not expose filesystem paths or server configuration to remote clients.
        reply({"status": "REJECTED"})
        return False


def serve_connection(incoming: BinaryIO, outgoing: BinaryIO, intake_root: Path,
                     grant: DeviceGrant) -> None:
    """Serve either a legacy request or a bounded, explicitly negotiated session."""
    first = incoming.readline(MAX_HEADER_BYTES + 1)
    if not first:
        return
    # Compare exact canonical bytes; arbitrary input is handled by the ordinary
    # strict parser, so negotiation cannot select a peer identity or source.
    if first != b'{"action":"session","version":1}\n':
        serve_once(incoming, outgoing, intake_root, grant, first_header=first)
        return
    outgoing.write(b'{"status":"SESSION_READY","version":1}\n')
    outgoing.flush()
    for _ in range(MAX_SESSION_REQUESTS):
        header = incoming.readline(MAX_HEADER_BYTES + 1)
        if not header:
            return
        if not serve_once(incoming, outgoing, intake_root, grant, first_header=header):
            return


def _verify(path: Path, expected_size: int, expected_digest: str) -> bool:
    if path.is_symlink():
        raise ValueError("Intake object cannot be a symbolic link")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
    return size == expected_size and digest.hexdigest() == expected_digest


def receive_object(
    stream: BinaryIO, root: Path, expected_size: int, expected_digest: str,
) -> dict[str, object]:
    """Receive one framed encrypted object. Never accepts a path from the stream.

    `root` is a pre-existing private, server-local filesystem chosen by a trusted
    launcher. `stream` supplies exactly the declared bytes for a single request.
    The transport must cap transfer time and bind the authenticated device itself.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Intake root must be an existing directory")
    if type(expected_size) is not int or not len(MAGIC) <= expected_size <= MAX_OBJECT_BYTES:
        raise ValueError("Invalid encrypted object size")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_digest):
        raise ValueError("Invalid encrypted object digest")
    final = root / expected_digest
    if final.exists() or final.is_symlink():
        if not _verify(final, expected_size, expected_digest):
            raise ValueError("Existing intake object does not match its address")
        return {"sha256": expected_digest, "bytes": expected_size, "reused": True}
    fd, name = tempfile.mkstemp(prefix=".incoming-", dir=root)
    temporary = Path(name)
    try:
        digest = hashlib.sha256()
        remaining = expected_size
        prefix = bytearray()
        with os.fdopen(fd, "wb") as out:
            while remaining:
                data = stream.read(min(CHUNK, remaining))
                if not data or len(data) > remaining:
                    raise ValueError("Encrypted transfer is truncated or exceeds its frame")
                if len(prefix) < len(MAGIC):
                    prefix.extend(data[:len(MAGIC) - len(prefix)])
                out.write(data)
                digest.update(data)
                remaining -= len(data)
            out.flush()
            os.fsync(out.fileno())
        if bytes(prefix) != MAGIC or digest.hexdigest() != expected_digest:
            raise ValueError("Encrypted transfer failed its format or digest check")
        try:
            # Exclusive publication on a server-local filesystem; a concurrent winner
            # is accepted only after independent size and hash verification.
            os.link(temporary, final)
            reused = False
        except FileExistsError:
            if not _verify(final, expected_size, expected_digest):
                raise ValueError("Concurrent intake object does not match its address") from None
            reused = True
        return {"sha256": expected_digest, "bytes": expected_size, "reused": reused}
    finally:
        temporary.unlink(missing_ok=True)
