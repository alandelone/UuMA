import hashlib
import io
import json

import pytest

from uuma.librarian_crypto import MAGIC
from uuma.librarian_intake import DeviceGrant, receive_granted_object, receive_object, serve_once


def test_verified_intake_is_idempotent_and_never_exposes_path_argument(tmp_path):
    payload = MAGIC + b"encrypted-fixture-only"
    digest = hashlib.sha256(payload).hexdigest()
    first = receive_object(io.BytesIO(payload), tmp_path, len(payload), digest)
    assert not first["reused"]
    assert (tmp_path / digest).read_bytes() == payload
    second = receive_object(io.BytesIO(b""), tmp_path, len(payload), digest)
    assert second["reused"]
    assert list(tmp_path.iterdir()) == [tmp_path / digest]


@pytest.mark.parametrize("change", ["truncated", "digest", "format"])
def test_failed_intake_never_publishes_or_keeps_partial_objects(tmp_path, change):
    original = MAGIC + b"encrypted-fixture-only"
    payload = original[:-1] if change == "truncated" else original
    if change == "format":
        payload = b"X" + payload[1:]
    digest = hashlib.sha256(original).hexdigest()
    if change == "format":
        digest = hashlib.sha256(payload).hexdigest()
    if change == "digest":
        digest = "f" * 64
    with pytest.raises(ValueError):
        receive_object(io.BytesIO(payload), tmp_path, len(original), digest)
    assert list(tmp_path.iterdir()) == []


def test_damaged_existing_address_is_never_replaced(tmp_path):
    payload = MAGIC + b"fixture"
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / digest).write_bytes(b"existing damage")
    with pytest.raises(ValueError, match="Existing"):
        receive_object(io.BytesIO(payload), tmp_path, len(payload), digest)
    assert (tmp_path / digest).read_bytes() == b"existing damage"


def test_untrusted_digest_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="digest"):
        receive_object(io.BytesIO(b""), tmp_path, len(MAGIC), "../outside")


def test_server_selected_device_grant_cannot_ingest_another_source(tmp_path):
    payload = MAGIC + b"encrypted-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    grant = DeviceGrant(device="workstation", sources=frozenset({"codex"}))
    with pytest.raises(PermissionError):
        receive_granted_object(io.BytesIO(payload), tmp_path, grant, "honc", len(payload), digest)
    assert list(tmp_path.iterdir()) == []
    result = receive_granted_object(io.BytesIO(payload), tmp_path, grant, "codex", len(payload), digest)
    assert result["device"] == "workstation" and result["source"] == "codex"
    assert (tmp_path / "workstation" / "codex" / digest).read_bytes() == payload


def test_invalid_device_or_source_grants_fail_before_writes(tmp_path):
    grant = DeviceGrant(device="../escape", sources=frozenset({"codex"}))
    with pytest.raises(PermissionError):
        receive_granted_object(io.BytesIO(b""), tmp_path, grant, "codex", len(MAGIC), "a" * 64)
    assert list(tmp_path.iterdir()) == []


def test_framed_session_uses_server_identity_and_skips_repeat_transfer(tmp_path):
    payload = MAGIC + b"encrypted-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    header = json.dumps({"source": "codex", "bytes": len(payload), "sha256": digest}).encode() + b"\n"
    grant = DeviceGrant(device="pc1", sources=frozenset({"codex"}))
    output = io.BytesIO()
    serve_once(io.BytesIO(header + payload), output, tmp_path, grant)
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [x["status"] for x in replies] == ["READY", "RECEIVED"]
    assert replies[1]["device"] == "pc1"
    output = io.BytesIO()
    serve_once(io.BytesIO(header), output, tmp_path, grant)
    assert json.loads(output.getvalue())["status"] == "ALREADY_PRESENT"


@pytest.mark.parametrize("header", [
    b'{"source":"codex","source":"honc","bytes":100,"sha256":"' + b'a' * 64 + b'"}\n',
    b'{"device":"pc2","source":"codex","bytes":100,"sha256":"' + b'a' * 64 + b'"}\n',
    b'{"source":"honc","bytes":100,"sha256":"' + b'a' * 64 + b'"}\n',
    b'x' * 4097 + b'\n',
])
def test_untrusted_headers_cannot_choose_identity_or_scope(tmp_path, header):
    output = io.BytesIO()
    serve_once(io.BytesIO(header), output, tmp_path,
               DeviceGrant(device="pc1", sources=frozenset({"codex"})))
    assert json.loads(output.getvalue()) == {"status": "REJECTED"}
    assert list(tmp_path.iterdir()) == []
