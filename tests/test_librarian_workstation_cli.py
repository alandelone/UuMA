import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_queue import _key_fingerprint
from uuma.librarian_workstation_cli import execute


def _config(tmp_path):
    queue, status = tmp_path / "queue", tmp_path / "status"
    queue.mkdir()
    status.mkdir()
    public = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    config = {"schema_version": 1, "queue": str(queue), "device": "pc1", "public_key": str(key),
              "public_fingerprint": _key_fingerprint(public), "host": "fixture",
              "ssh_identity": str(tmp_path / "ssh"), "status_directory": str(status),
              "sources": [{"source_id": "history", "kind": "tree", "path": str(tmp_path / "tree")}]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path, status


def test_cli_keeps_per_source_and_final_status_receipts(tmp_path, monkeypatch):
    path, status = _config(tmp_path)

    def capture(*args, **kwargs):
        item = {"source": "history", "coverage": "PARTIAL", "server_intake": "PENDING"}
        kwargs["on_result"](item)
        return {"date": "2026-10-30", "sources": [item], "incomplete": 1}

    monkeypatch.setattr("uuma.librarian_workstation_cli.run_sources", capture)
    result, code = execute(path)
    assert code == 2 and result["scope"] == "registered workstation sources only"
    receipt = next(status.glob("*.jsonl"))
    events = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert events[0]["source"] == "history" and events[1]["summary"]["incomplete"] == 1


def test_public_key_mismatch_cannot_start_capture_or_write_status(tmp_path):
    path, status = _config(tmp_path)
    data = json.loads(path.read_text())
    data["public_fingerprint"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        execute(path)
    assert list(status.iterdir()) == []


def test_sessions_are_explicit_and_invalid_configuration_is_rejected(tmp_path, monkeypatch):
    path, status = _config(tmp_path)
    data = json.loads(path.read_text())
    data['transfer_sessions'] = True
    path.write_text(json.dumps(data))
    calls = []

    def capture(*args, **kwargs):
        calls.append(kwargs['use_sessions'])
        return {'date': '2026-10-30', 'sources': [], 'incomplete': 0}

    monkeypatch.setattr('uuma.librarian_workstation_cli.run_sources', capture)
    assert execute(path)[1] == 0 and calls == [True]
    data['transfer_sessions'] = 'true'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Invalid workstation'):
        execute(path)
    assert len(list(status.glob('*.jsonl'))) == 1
