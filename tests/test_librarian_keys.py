import sys

import pytest
from cryptography.hazmat.primitives import serialization

from uuma.librarian_crypto import recover, seal
from uuma.librarian_keys import export_offline, initialize

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Real Windows DPAPI required")


def test_exported_key_can_restore_after_local_key_directory_is_unavailable(tmp_path):
    keys = tmp_path / "user-key"
    fingerprint = initialize(keys)
    offline = tmp_path / "offline-key.pem"
    password = b"fixture-offline-password"
    assert export_offline(keys, offline, password) == fingerprint
    raw = offline.read_bytes()
    with pytest.raises(ValueError):
        serialization.load_pem_private_key(raw, b"wrong-password")
    source = tmp_path / "source"
    source.write_bytes(b"private fixture")
    capsule = tmp_path / "capsule"
    seal(source, capsule, (keys / "public.pem").read_bytes())
    keys.rename(tmp_path / "unavailable")
    restored = tmp_path / "restored"
    recover(capsule, restored, raw, password)
    assert restored.read_bytes() == source.read_bytes()


def test_existing_key_or_offline_export_never_overwritten(tmp_path):
    keys = tmp_path / "user-key"
    initialize(keys)
    old = (keys / "private.pem").read_bytes()
    with pytest.raises(FileExistsError):
        initialize(keys)
    assert (keys / "private.pem").read_bytes() == old
    offline = tmp_path / "offline.pem"
    offline.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        export_offline(keys, offline, b"fixture-password")
    assert offline.read_bytes() == b"preserve"


def test_mismatched_public_key_cannot_be_exported(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    initialize(first)
    initialize(second)
    (first / "public.pem").write_bytes((second / "public.pem").read_bytes())
    with pytest.raises(ValueError, match="do not match"):
        export_offline(first, tmp_path / "offline.pem", b"fixture-password")
