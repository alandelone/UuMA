"""Root-scoped, reentrant process locks for Brainstormer's JSON store."""

from __future__ import annotations

import errno
import getpass
import hashlib
import math
import os
import stat
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Self


@dataclass
class _State:
    thread_lock: Any = field(default_factory=threading.RLock)
    depth: int = 0
    handle: BinaryIO | None = None


_states: dict[str, _State] = {}
_states_guard = threading.Lock()


def _after_fork() -> None:
    global _states, _states_guard
    for state in _states.values():
        if state.handle is not None:
            state.handle.close()
    _states = {}
    _states_guard = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def _state_for(root: Path) -> _State:
    key = os.path.normcase(str(root))
    with _states_guard:
        return _states.setdefault(key, _State())


def _reject_link(metadata: os.stat_result) -> None:
    if stat.S_ISLNK(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise PermissionError("Brainstormer lock metadata cannot use links or reparse points")


def _private_lock_path(root: Path) -> Path:
    identity = str(os.getuid()) if hasattr(os, "getuid") else (
        hashlib.sha256(getpass.getuser().encode("utf-8")).hexdigest()[:16]
    )
    directory = Path(tempfile.gettempdir()) / f"uuma-brainstormer-locks-{identity}"
    directory.mkdir(mode=0o700, exist_ok=True)
    metadata = directory.lstat()
    _reject_link(metadata)
    if not stat.S_ISDIR(metadata.st_mode):
        raise PermissionError("Brainstormer lock directory is not a directory")
    if os.name != "nt" and (
        metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise PermissionError("Brainstormer lock directory must be owned by this user with mode 0700")
    key = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
    return directory / f"{key}.lock"


def _open_private_lock(path: Path) -> BinaryIO:
    try:
        _reject_link(path.lstat())
    except FileNotFoundError:
        pass
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        current = path.lstat()
        _reject_link(current)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink > 1
            or (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise PermissionError("Brainstormer lock file must be a private regular file")
        if os.name != "nt" and (
            metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise PermissionError("Brainstormer lock file must be owned by this user with mode 0600")
        handle = os.fdopen(descriptor, "r+b")
    except BaseException:
        os.close(descriptor)
        raise
    return handle


def _try_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class BrainstormerProcessLock:
    """Serialize threads and processes; nested stores with one root share ownership.

    The persistent lock file is never deleted. File existence is not evidence of
    ownership: the operating system releases ownership when its process exits.
    """

    def __init__(self, root: Path, *, timeout_seconds: float = 30) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Lock timeout must be positive and finite")
        self.root = root.resolve()
        self.timeout_seconds = timeout_seconds
        self.lock_path = _private_lock_path(self.root)

    def __enter__(self) -> Self:
        state = _state_for(self.root)
        deadline = time.monotonic() + self.timeout_seconds
        if not state.thread_lock.acquire(timeout=self.timeout_seconds):
            raise TimeoutError("Timed out waiting for the Brainstormer store lock")
        if state.depth:
            state.depth += 1
            return self
        handle = None
        try:
            if _private_lock_path(self.root) != self.lock_path:
                raise RuntimeError("Brainstormer lock directory changed during this process")
            handle = _open_private_lock(self.lock_path)
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                try:
                    _try_lock(handle)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            "Timed out waiting for the Brainstormer store lock"
                        ) from error
                    time.sleep(min(0.025, remaining))
            state.handle = handle
            state.depth = 1
            return self
        except BaseException:
            if handle is not None:
                handle.close()
            state.thread_lock.release()
            raise

    def __exit__(self, *_exception: object) -> None:
        state = _state_for(self.root)
        try:
            state.depth -= 1
            if state.depth == 0:
                handle = state.handle
                state.handle = None
                assert handle is not None
                try:
                    _unlock(handle)
                finally:
                    handle.close()
        finally:
            state.thread_lock.release()
