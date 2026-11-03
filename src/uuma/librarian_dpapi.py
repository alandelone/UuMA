"""Current-user Windows DPAPI protection for local recovery-key passwords."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _transform(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise OSError("Windows DPAPI is only available on Windows")
    if not data:
        raise ValueError("DPAPI input must not be empty")
    array = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), array)
    destination = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    blob_pointer = ctypes.POINTER(_Blob)
    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [blob_pointer, ctypes.c_void_p, blob_pointer, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.DWORD, blob_pointer]
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [blob_pointer, wintypes.LPCWSTR, blob_pointer, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.DWORD, blob_pointer]
    function.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; omit machine scope so only this Windows user can decrypt.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree(destination.pbData)


def protect(data: bytes) -> bytes:
    """Protect bytes for the current Windows user, without interactive prompts."""
    return _transform(data, decrypt=False)


def unprotect(data: bytes) -> bytes:
    """Decrypt current-user DPAPI bytes; raises on tampering or another user."""
    return _transform(data, decrypt=True)
