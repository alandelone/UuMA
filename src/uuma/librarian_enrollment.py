"""Server-side enrollment of a separately generated workstation SSH key.

The caller supplies an independently checked request digest and a server-owned
receiver release. Enrollment adds one restricted key; it does not start capture.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .librarian_intake import IDENTITY
from .librarian_ssh import _unique, load_policy

if os.name == "posix":
    import fcntl

SAFE_COMMAND_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")
DEVICE = re.compile(r"workstation-[a-z0-9][a-z0-9-]{0,39}\Z")


def _private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected an existing regular file")
    stat = path.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise PermissionError("File must be private and owned by the service user")


def _write_exclusive(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _replace_if_unchanged(path: Path, old: bytes, new: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".librarian-enroll-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        _private_file(path)
        if path.read_bytes() != old:
            raise RuntimeError("Existing enrollment file changed during preparation")
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def enroll(*, request_path: Path, expected_request_sha256: str, policy_path: Path,
           authorized_keys: Path, receipts: Path, python: Path, launcher: Path,
           expected_launcher_sha256: str, template_device: str = "workstation") -> dict[str, object]:
    """Bind a new device key and its requested subset of the trusted source grant.

    All paths and both hashes come from the trusted server operator, not the request.
    The caller must compare the request digest through a trusted channel. A crash
    between replacements can leave an inert policy grant without an SSH key; the
    pre-change snapshots and intent receipt are retained for reconciliation.
    """
    if os.name != "posix":
        raise OSError("Enrollment requires the POSIX server")
    policy_path, authorized_keys, receipts = map(Path, (policy_path, authorized_keys, receipts))
    request_path, python, launcher = map(Path, (request_path, python, launcher))
    if not all(re.fullmatch(r"[a-f0-9]{64}", h) for h in
               (expected_request_sha256, expected_launcher_sha256)):
        raise ValueError("Expected checked SHA-256 digests")
    for path in (policy_path, authorized_keys):
        _private_file(path)
    if (receipts.is_symlink() or not receipts.is_dir() or receipts.stat().st_uid != os.geteuid()
            or receipts.stat().st_mode & 0o077):
        raise PermissionError("Enrollment receipts directory must be private")
    if request_path.is_symlink() or not request_path.is_file():
        raise ValueError("Enrollment request must be a regular file")
    raw = request_path.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_request_sha256:
        raise ValueError("Enrollment request does not match the checked digest")
    request = json.loads(raw, object_pairs_hook=_unique)
    if not isinstance(request, dict) or set(request) != {
        "device", "public_ssh_key", "source_ids", "missing_source_ids",
    }:
        raise ValueError("Invalid enrollment request")
    device, sources = request["device"], request["source_ids"]
    if (not isinstance(device, str) or not DEVICE.fullmatch(device)
            or not isinstance(sources, list) or not sources or len(sources) > 500
            or any(not isinstance(x, str) or not IDENTITY.fullmatch(x) for x in sources)
            or len(sources) != len(set(sources))):
        raise ValueError("Invalid requested device or source identities")
    if not isinstance(request["missing_source_ids"], list):
        raise TypeError("Invalid missing source list")
    key_text = request["public_ssh_key"]
    if not isinstance(key_text, str) or len(key_text) > 1024 or "\n" in key_text or "\r" in key_text:
        raise ValueError("Invalid SSH public key")
    parts = key_text.split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("Expected an Ed25519 SSH public key")
    # OpenSSH comments are not key material and may contain a localized user name.
    try:
        wire_key = (parts[0] + " " + parts[1]).encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Invalid SSH public key encoding") from None
    public = serialization.load_ssh_public_key(wire_key)
    if not isinstance(public, Ed25519PublicKey):
        raise TypeError("Only a device-specific Ed25519 public key is accepted")
    canonical = public.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
    for path in (python, launcher, policy_path):
        if not path.is_absolute() or not SAFE_COMMAND_PATH.fullmatch(str(path)):
            raise ValueError("Unsafe server command path")
    if launcher.is_symlink() or hashlib.sha256(launcher.read_bytes()).hexdigest() != expected_launcher_sha256:
        raise ValueError("Pinned intake launcher changed")
    if not python.is_file():
        raise ValueError("Pinned interpreter unavailable")
    lock_path = receipts / ".enrollment.lock"
    if lock_path.is_symlink():
        raise ValueError("Enrollment lock cannot be a symlink")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _private_file(lock_path)
        _private_file(policy_path)
        _private_file(authorized_keys)
        load_policy(policy_path, template_device)
        old_policy, old_keys = policy_path.read_bytes(), authorized_keys.read_bytes()
        policy = json.loads(old_policy, object_pairs_hook=_unique)
        if device in policy["devices"]:
            raise ValueError("Device already registered; reconcile existing enrollment")
        if not set(sources).issubset(set(policy["devices"][template_device])):
            raise PermissionError("Requested source exceeds the trusted template grant")
        if canonical.split()[1] in old_keys.split():
            raise ValueError("SSH key already appears in authorized keys")
        policy["devices"][device] = sources
        new_policy = json.dumps(policy, sort_keys=True, indent=2).encode() + b"\n"
        command = (f'restrict,command="{python} -I -B {launcher} --policy {policy_path}'
                   f' --device {device}" ').encode() + canonical + b"\n"
        new_keys = old_keys + (b"\n" if old_keys and not old_keys.endswith(b"\n") else b"") + command
        tag = "enrollment-" + uuid.uuid4().hex
        _write_exclusive(receipts / (tag + ".policy-before"), old_policy)
        _write_exclusive(receipts / (tag + ".keys-before"), old_keys)
        intent = {"device": device, "source_ids": sources, "request_sha256": expected_request_sha256,
                  "launcher_sha256": expected_launcher_sha256,
                  "policy_before_sha256": hashlib.sha256(old_policy).hexdigest(),
                  "keys_before_sha256": hashlib.sha256(old_keys).hexdigest(),
                  "created_at": datetime.now(UTC).isoformat(), "status": "PREPARED"}
        _write_exclusive(receipts / (tag + ".intent.json"), json.dumps(intent, sort_keys=True).encode())
        _replace_if_unchanged(policy_path, old_policy, new_policy)
        _replace_if_unchanged(authorized_keys, old_keys, new_keys)
        root, grant = load_policy(policy_path, device)
        if grant.sources != frozenset(sources):
            raise RuntimeError("Published device grant failed readback")
        result = intent | {"status": "ENROLLED", "intake_root": str(root),
                           "policy_after_sha256": hashlib.sha256(new_policy).hexdigest(),
                           "keys_after_sha256": hashlib.sha256(new_keys).hexdigest()}
        _write_exclusive(receipts / (tag + ".complete.json"), json.dumps(result, sort_keys=True).encode())
        return result
    finally:
        os.close(lock_fd)
