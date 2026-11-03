import json
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_queue import _key_fingerprint
from uuma.librarian_server_cli import execute

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Server CLI requires POSIX ownership")


def _config(tmp_path):
    queue, intake, status = tmp_path / "queue", tmp_path / "intake", tmp_path / "status"
    for directory in (queue, intake, status):
        directory.mkdir(mode=0o700)
    public = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    spec = {"source_id": "fixture", "kind": "sqlite", "path": str(tmp_path / "db"),
            "owner_unit": "uuma-fixture.service", "owner_env": "UUMA_DATA_DIR", "owner_value": str(tmp_path)}
    config = {"schema_version": 1, "queue": str(queue), "intake": str(intake), "public_key": str(key),
              "public_fingerprint": _key_fingerprint(public), "status_directory": str(status), "sources": [spec]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    return path, status


def test_cli_keeps_scoped_incomplete_state_visible(tmp_path, monkeypatch):
    path, status = _config(tmp_path)
    monkeypatch.setattr("uuma.librarian_server_cli.run_sources", lambda *a, **kw: {
        "date": "2026-10-30", "sources": [{"source": "fixture", "status": "OWNER_UNVERIFIED"}],
        "incomplete": 1,
    })
    result, code = execute(path)
    assert code == 2 and result["scope"] == "registered server sources only"
    assert len(list(status.glob("run-*.json"))) == 1


def test_public_configuration_is_rejected_before_status_write(tmp_path):
    path, status = _config(tmp_path)
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        execute(path)
    assert list(status.iterdir()) == []
