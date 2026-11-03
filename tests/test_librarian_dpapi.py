import sys

import pytest

from uuma.librarian_dpapi import protect, unprotect


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is a Windows user facility")
def test_current_user_protection_and_tamper_detection():
    secret = b"fixture-only-non-production-password\x00"
    encrypted = protect(secret)
    assert encrypted != secret
    assert secret not in encrypted
    assert unprotect(encrypted) == secret
    changed = bytearray(encrypted)
    changed[-1] ^= 1
    with pytest.raises(OSError):
        unprotect(bytes(changed))


def test_empty_input_does_not_create_a_secret():
    if sys.platform != "win32":
        pytest.skip("DPAPI is a Windows user facility")
    with pytest.raises(ValueError):
        protect(b"")
