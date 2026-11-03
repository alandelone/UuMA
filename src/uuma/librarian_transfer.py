"""Client side of a single authenticated encrypted-object transfer."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from .librarian_crypto import MAGIC
from .librarian_intake import (
    CHUNK,
    IDENTITY,
    MAX_HEADER_BYTES,
    MAX_OBJECT_BYTES,
    MAX_SESSION_REQUESTS,
)
from .librarian_manifest_intake import MAX_MANIFEST_BYTES

DEFAULT_BYTES_PER_SECOND = 8 * 1024 * 1024


def send_manifest(
    incoming: BinaryIO, outgoing: BinaryIO, raw: bytes, *, device: str, source: str,
    bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
) -> dict[str, object]:
    """Send one frozen manifest only after all its objects have reached intake."""
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid device or source identity")
    if not 1 <= len(raw) <= MAX_MANIFEST_BYTES:
        raise ValueError("Manifest exceeds private intake limits")
    if type(bytes_per_second) is not int or not 1 <= bytes_per_second <= 1024 * 1024 * 1024:
        raise ValueError("Invalid transfer bandwidth")
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("device") != device
            or manifest.get("source") != source or type(manifest.get("revision")) is not int
            or not isinstance(manifest.get("batch_id"), str)):
        raise ValueError("Frozen manifest does not match the configured device and source")
    digest = hashlib.sha256(raw).hexdigest()
    header = {"action": "manifest", "source": source, "bytes": len(raw), "sha256": digest}
    outgoing.write(json.dumps(header, sort_keys=True).encode("utf-8") + b"\n")
    outgoing.flush()
    if _response(incoming) != {"status": "READY"}:
        raise ValueError("Server rejected the manifest transfer")
    started = time.monotonic()
    for offset in range(0, len(raw), CHUNK):
        outgoing.write(raw[offset:offset + CHUNK])
        remaining = min(offset + CHUNK, len(raw)) / bytes_per_second - (time.monotonic() - started)
        while remaining > 0:
            time.sleep(min(remaining, 1.0))
            remaining = min(offset + CHUNK, len(raw)) / bytes_per_second - (time.monotonic() - started)
    outgoing.flush()
    response = _response(incoming)
    if (response.get("status") != "MANIFEST_RECEIVED" or response.get("sha256") != digest
            or response.get("batch_id") != manifest["batch_id"]
            or response.get("revision") != manifest["revision"]
            or response.get("coverage") != manifest.get("coverage")
            or type(response.get("reused")) is not bool):
        raise ValueError("Server manifest receipt does not match the frozen batch")
    return response


def _response(stream: BinaryIO) -> dict[str, object]:
    raw = stream.readline(MAX_HEADER_BYTES + 1)
    if len(raw) > MAX_HEADER_BYTES or not raw.endswith(b"\n"):
        raise ValueError("Invalid intake response frame")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate response key")
            result[key] = value
        return result

    result = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise TypeError("Invalid intake response")
    return result


def send_object(
    incoming: BinaryIO, outgoing: BinaryIO, capsule: Path, *, device: str, source: str,
    expected_digest: str,
    bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
) -> dict[str, object]:
    """Send one ciphertext through a verified, device-bound transport.

    The caller creates the trusted transport, verifies the SSH host key, binds the
    client key to `device`, and enforces a process/connection deadline. This function
    never accepts or sends a filesystem path to the server.
    """
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid device or source identity")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_digest):
        raise ValueError("Invalid frozen object digest")
    if type(bytes_per_second) is not int or not 1 <= bytes_per_second <= 1024 * 1024 * 1024:
        raise ValueError("Invalid transfer bandwidth")
    path = Path(capsule)
    if path.is_symlink():
        raise ValueError("Local encrypted object cannot be a symlink")
    before = path.stat()
    size = before.st_size
    if not len(MAGIC) <= size <= MAX_OBJECT_BYTES:
        raise ValueError("Invalid encrypted object size")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        prefix = stream.read(len(MAGIC))
        if prefix != MAGIC:
            raise ValueError("Only recovery capsules can be transferred")
        digest.update(prefix)
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    observed = path.stat()
    if (observed.st_size, observed.st_mtime_ns, observed.st_ino) != (
        before.st_size, before.st_mtime_ns, before.st_ino
    ):
        raise ValueError("Encrypted object changed before transfer")
    checksum = digest.hexdigest()
    if checksum != expected_digest:
        raise ValueError("Encrypted object does not match its frozen batch digest")
    header = json.dumps({"source": source, "bytes": size, "sha256": checksum},
                        sort_keys=True).encode("utf-8") + b"\n"
    outgoing.write(header)
    outgoing.flush()
    first = _response(incoming)
    if first.get("status") == "ALREADY_PRESENT":
        if first.get("sha256") != checksum or first.get("bytes") != size:
            raise ValueError("Existing-object receipt does not match the request")
        return {"device": device, "source": source, "sha256": checksum,
                "bytes": size, "reused": True}
    if first != {"status": "READY"}:
        raise ValueError("Server rejected encrypted transfer")
    sent = 0
    started = time.monotonic()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            outgoing.write(chunk)
            sent += len(chunk)
            remaining = sent / bytes_per_second - (time.monotonic() - started)
            while remaining > 0:
                time.sleep(min(remaining, 1.0))
                remaining = sent / bytes_per_second - (time.monotonic() - started)
    outgoing.flush()
    after = path.stat()
    if (after.st_size, after.st_mtime_ns, after.st_ino) != (
        before.st_size, before.st_mtime_ns, before.st_ino
    ) or sent != size:
        raise ValueError("Encrypted object changed during transfer")
    final = _response(incoming)
    if (final.get("status") != "RECEIVED" or final.get("device") != device
            or final.get("source") != source or final.get("sha256") != checksum
            or final.get("bytes") != size or type(final.get("reused")) is not bool):
        raise ValueError("Server receipt does not match the sent object")
    return {"device": device, "source": source, "sha256": checksum,
            "bytes": size, "reused": final["reused"]}


def send_over_ssh(
    capsule: Path, *, device: str, source: str, expected_digest: str,
    host: str, identity_file: Path, timeout_seconds: float = 14400,
    bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
) -> dict[str, object]:
    """Run one no-shell SSH forced command with host-key checking and a deadline."""
    return _run_ssh(
        lambda incoming, outgoing: send_object(
            incoming, outgoing, capsule, device=device, source=source,
            expected_digest=expected_digest, bytes_per_second=bytes_per_second,
        ), host=host, identity_file=identity_file, timeout_seconds=timeout_seconds,
    )


def send_manifest_over_ssh(
    raw: bytes, *, device: str, source: str, host: str, identity_file: Path,
    timeout_seconds: float = 14400, bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
) -> dict[str, object]:
    """Send one frozen manifest via the same authenticated forced-command transport."""
    return _run_ssh(
        lambda incoming, outgoing: send_manifest(incoming, outgoing, raw, device=device, source=source,
                                                 bytes_per_second=bytes_per_second),
        host=host, identity_file=identity_file, timeout_seconds=timeout_seconds,
    )


def send_objects_over_ssh(
    objects: list[tuple[Path, str]], *, device: str, source: str, host: str,
    identity_file: Path, timeout_seconds: float = 14400,
    bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
) -> dict[str, object]:
    """Send a bounded group over one authenticated, explicitly negotiated SSH session."""
    if not 1 <= len(objects) <= MAX_SESSION_REQUESTS:
        raise ValueError("Invalid number of objects in the transfer session")

    def exchange(incoming: BinaryIO, outgoing: BinaryIO) -> dict[str, object]:
        outgoing.write(b'{"action":"session","version":1}\n')
        outgoing.flush()
        if _response(incoming) != {"status": "SESSION_READY", "version": 1}:
            raise ValueError("Server did not accept the bounded transfer session")
        reused = 0
        for path, digest in objects:
            receipt = send_object(incoming, outgoing, path, device=device, source=source,
                                  expected_digest=digest, bytes_per_second=bytes_per_second)
            reused += int(receipt["reused"])
        return {"device": device, "source": source, "objects": len(objects), "reused": reused}

    return _run_ssh(exchange, host=host, identity_file=identity_file, timeout_seconds=timeout_seconds)


def _run_ssh(
    exchange: Callable[[BinaryIO, BinaryIO], dict[str, object]], *, host: str,
    identity_file: Path, timeout_seconds: float,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,254}", host):
        raise ValueError("Invalid configured SSH host alias")
    if not 0 < timeout_seconds <= 14400:
        raise ValueError("Invalid SSH transfer deadline")
    key = Path(identity_file).absolute()
    if key.is_symlink() or not key.is_file():
        raise ValueError("The configured SSH identity file must already exist")
    command = ["ssh", "-T", "-i", str(key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-o",
               "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2", host]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    result: dict[str, object] = {}
    error: list[BaseException] = []
    complete = threading.Event()

    def transfer() -> None:
        try:
            assert process.stdout is not None and process.stdin is not None
            result.update(exchange(process.stdout, process.stdin))
        except BaseException as exc:  # noqa: BLE001 -- preserve all worker failures across threads
            error.append(exc)
        finally:
            complete.set()

    worker = threading.Thread(target=transfer, daemon=True, name="librarian-ssh-transfer")
    worker.start()
    deadline = time.monotonic() + timeout_seconds
    try:
        while not complete.wait(timeout=min(1.0, max(0.0, deadline - time.monotonic()))):
            if time.monotonic() >= deadline:
                raise TimeoutError("SSH encrypted transfer exceeded its deadline")
        if error:
            raise RuntimeError("SSH encrypted transfer failed") from error[0]
        if process.stdin is not None:
            process.stdin.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("SSH encrypted transfer exceeded its deadline")
        try:
            code = process.wait(timeout=min(remaining, 10))
        except subprocess.TimeoutExpired:
            raise TimeoutError("SSH intake did not terminate after its receipt") from None
        if code:
            raise RuntimeError("SSH intake exited unsuccessfully after its receipt")
        return result
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        worker.join(timeout=2)
        if process.stdout is not None:
            process.stdout.close()
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
