"""Forced-command entry point for one authenticated Librarian device transfer.

The SSH daemon must bind the fixed --device and --policy arguments to one key using
an authorized_keys forced command with forwarding, PTY, agent and user-rc disabled.
This module never evaluates SSH_ORIGINAL_COMMAND.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from .librarian_intake import IDENTITY, DeviceGrant, serve_connection

MAX_POLICY_BYTES = 65536


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy key")
        result[key] = value
    return result


def load_policy(path: Path, device: str) -> tuple[Path, DeviceGrant]:
    """Load private, server-owned policy, selecting the launcher-bound device."""
    if os.name != "posix":
        raise OSError("SSH intake policy is supported on the server POSIX host only")
    if not IDENTITY.fullmatch(device):
        raise ValueError("Invalid bound device")
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Intake policy cannot be a symlink")
    stat = path.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise PermissionError("Intake policy must be private and owned by the service user")
    with path.open("rb") as stream:
        data = stream.read(MAX_POLICY_BYTES + 1)
    if len(data) > MAX_POLICY_BYTES:
        raise ValueError("Intake policy is too large")
    policy = json.loads(data, object_pairs_hook=_unique)
    if not isinstance(policy, dict) or set(policy) != {"schema_version", "intake_root", "devices"}:
        raise ValueError("Invalid intake policy")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise ValueError("Unsupported intake policy version")
    devices = policy["devices"]
    if not isinstance(devices, dict) or device not in devices or len(devices) > 500:
        raise PermissionError("Unregistered device")
    sources = devices[device]
    if (not isinstance(sources, list) or not sources or len(sources) > 500
            or any(not isinstance(source, str) or not IDENTITY.fullmatch(source) for source in sources)
            or len(sources) != len(set(sources))):
        raise ValueError("Invalid source grant")
    if not isinstance(policy["intake_root"], str):
        raise TypeError("Invalid intake root")
    configured = Path(policy["intake_root"])
    if not configured.is_absolute() or configured.is_symlink():
        raise ValueError("Intake root must be an absolute non-symlink path")
    root = configured.resolve(strict=True)
    stat = root.stat()
    if not root.is_dir() or stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise PermissionError("Intake root must be private and owned by the service user")
    return root, DeviceGrant(device=device, sources=frozenset(sources))


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive one forced-command encrypted object")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--device", required=True)
    args = parser.parse_args()
    try:
        root, grant = load_policy(Path(args.policy), args.device)
        # This limits one remote process even if a client never finishes its frame.
        signal.alarm(14400)
        serve_connection(sys.stdin.buffer, sys.stdout.buffer, root, grant)
    except (OSError, ValueError, TypeError, PermissionError, UnicodeError):
        sys.stdout.buffer.write(b'{"status":"REJECTED"}\n')
        sys.stdout.buffer.flush()
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
