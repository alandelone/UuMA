import hashlib
import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from uuma import librarian_enrollment as enrollment
from uuma.librarian_ssh import load_policy

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Server enrollment requires POSIX")


def setup_enrollment(tmp_path):
    intake = tmp_path / "intake"
    receipts = tmp_path / "receipts"
    intake.mkdir(mode=0o700)
    receipts.mkdir(mode=0o700)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": 1, "intake_root": str(intake),
                                  "devices": {"workstation": ["codex-sessions", "scholar"]}}))
    keys = tmp_path / "authorized_keys"
    keys.write_text("# Existing keys and options are preserved\n")
    policy.chmod(0o600)
    keys.chmod(0o600)
    launcher = tmp_path / "launch.py"
    launcher.write_text("# test launcher\n")
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"device": "workstation-2", "public_ssh_key": public,
                                   "source_ids": ["codex-sessions"], "missing_source_ids": []}))
    return {"request_path": request, "expected_request_sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
            "policy_path": policy, "authorized_keys": keys, "receipts": receipts,
            "python": Path("/usr/bin/python3"), "launcher": launcher,
            "expected_launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest()}


def test_enrollment_preserves_keys_and_binds_restricted_device(tmp_path):
    args = setup_enrollment(tmp_path)
    before_keys = args["authorized_keys"].read_bytes()
    result = enrollment.enroll(**args)
    assert result["status"] == "ENROLLED"
    assert load_policy(args["policy_path"], "workstation-2")[1].sources == {"codex-sessions"}
    new_keys = args["authorized_keys"].read_bytes()
    assert new_keys.startswith(before_keys) and b'restrict,command="' in new_keys
    assert b"--device workstation-2" in new_keys and b"ssh-ed25519" in new_keys
    assert len(list(args["receipts"].glob("*.intent.json"))) == 1
    assert len(list(args["receipts"].glob("*.complete.json"))) == 1
    with pytest.raises(ValueError, match="already registered"):
        enrollment.enroll(**args)
    assert args["authorized_keys"].read_bytes() == new_keys


def test_untrusted_request_cannot_escalate_sources_or_use_unchecked_bytes(tmp_path):
    args = setup_enrollment(tmp_path)
    old_policy, old_keys = args["policy_path"].read_bytes(), args["authorized_keys"].read_bytes()
    data = json.loads(args["request_path"].read_text())
    data["source_ids"] = ["secret-source"]
    args["request_path"].write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checked digest"):
        enrollment.enroll(**args)
    args["expected_request_sha256"] = hashlib.sha256(args["request_path"].read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="template grant"):
        enrollment.enroll(**args)
    assert args["policy_path"].read_bytes() == old_policy
    assert args["authorized_keys"].read_bytes() == old_keys


def test_key_file_race_preserves_other_writes_and_records_intent(tmp_path, monkeypatch):
    args = setup_enrollment(tmp_path)
    old_keys = args["authorized_keys"].read_bytes()
    replace = enrollment._replace_if_unchanged

    def concurrent_change(path, old, new):
        if path == args["authorized_keys"]:
            path.write_bytes(old + b"# concurrent other change\n")
        return replace(path, old, new)

    monkeypatch.setattr(enrollment, "_replace_if_unchanged", concurrent_change)
    with pytest.raises(RuntimeError, match="changed during preparation"):
        enrollment.enroll(**args)
    assert args["authorized_keys"].read_bytes() == old_keys + b"# concurrent other change\n"
    assert len(list(args["receipts"].glob("*.intent.json"))) == 1
    assert not list(args["receipts"].glob("*.complete.json"))
    assert len(list(args["receipts"].glob("*.policy-before"))) == 1


def test_unicode_comment_is_discarded_but_newline_injection_is_rejected(tmp_path):
    args = setup_enrollment(tmp_path)
    data = json.loads(args["request_path"].read_text())
    data["public_ssh_key"] += " 用户@电脑"
    args["request_path"].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    args["expected_request_sha256"] = hashlib.sha256(args["request_path"].read_bytes()).hexdigest()
    assert enrollment.enroll(**args)["status"] == "ENROLLED"
    assert "用户".encode() not in args["authorized_keys"].read_bytes()
    other = tmp_path / "other"
    other.mkdir()
    args = setup_enrollment(other)
    data = json.loads(args["request_path"].read_text())
    data["public_ssh_key"] += "\nssh-ed25519 injected"
    args["request_path"].write_text(json.dumps(data))
    args["expected_request_sha256"] = hashlib.sha256(args["request_path"].read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Invalid SSH public key"):
        enrollment.enroll(**args)
