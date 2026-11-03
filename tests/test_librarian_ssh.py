import hashlib
import io
import json
import os
import subprocess
import sys

import pytest

from uuma.librarian_crypto import MAGIC
from uuma.librarian_intake import serve_once
from uuma.librarian_ssh import load_policy

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX SSH server policy required")


@pytest.fixture
def policy(tmp_path):
    root = tmp_path / "intake"
    root.mkdir(mode=0o700)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"schema_version": 1, "intake_root": str(root),
                                "devices": {"pc1": ["codex"]}}))
    path.chmod(0o600)
    return path, root


def test_policy_binds_device_and_rejects_peer_identity(policy):
    path, root = policy
    actual_root, grant = load_policy(path, "pc1")
    assert actual_root == root and grant.device == "pc1" and grant.sources == {"codex"}
    output = io.BytesIO()
    request = b'{"device":"pc2","source":"codex","bytes":100,"sha256":"' + b'a'*64 + b'"}\n'
    serve_once(io.BytesIO(request), output, actual_root, grant)
    assert json.loads(output.getvalue()) == {"status": "REJECTED"}
    with pytest.raises(PermissionError):
        load_policy(path, "pc2")


def test_public_policy_and_intake_root_are_rejected(policy):
    path, root = policy
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        load_policy(path, "pc1")
    path.chmod(0o600)
    root.chmod(0o755)
    with pytest.raises(PermissionError):
        load_policy(path, "pc1")


def test_duplicate_policy_key_is_rejected(policy):
    path, _ = policy
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Duplicate"):
        load_policy(path, "pc1")


def test_forced_command_stdio_ignores_original_command(policy):
    path, root = policy
    payload = MAGIC + b"fixture encrypted bytes"
    digest = hashlib.sha256(payload).hexdigest()
    header = json.dumps({"source": "codex", "bytes": len(payload), "sha256": digest}).encode() + b"\n"
    env = dict(os.environ)
    env["SSH_ORIGINAL_COMMAND"] = "touch " + str(root / "should-not-exist")
    result = subprocess.run(
        [sys.executable, "-m", "uuma.librarian_ssh", "--policy", str(path), "--device", "pc1"],
        input=header + payload, capture_output=True, env=env, check=False, timeout=15,
    )
    assert result.returncode == 0
    assert [json.loads(line)["status"] for line in result.stdout.splitlines()] == ["READY", "RECEIVED"]
    assert (root / "pc1" / "codex" / digest).read_bytes() == payload
    assert not (root / "should-not-exist").exists()
