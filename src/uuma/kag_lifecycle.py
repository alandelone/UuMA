"""Process-safe start/stop coordination for the disposable KAG runtime."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


def launch_runtime_process(command: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    """Start an owned service outside the short-lived MCP client's process tree."""
    if os.name != "nt":
        subprocess.Popen(command, cwd=cwd, env=environment, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return
    executable = Path(command[0])
    if executable.name.lower() == "pythonw.exe":
        console_python = executable.with_name("python.exe")
        if not console_python.is_file():
            raise OSError("The hidden bridge launcher requires the matching python.exe")
        # WMI hides the window; python.exe still supplies streams required by uvicorn logging.
        command = [str(console_python), *command[1:]]
    # WMI owns the child, so closing the MCP client's Windows Job Object cannot kill it.
    # Pass environment on stdin, never in command arguments, files or diagnostic output.
    script = """
$ErrorActionPreference = 'Stop'
$spec = [Console]::In.ReadToEnd() | ConvertFrom-Json
$vars = @($spec.environment.PSObject.Properties | ForEach-Object { $_.Name + '=' + $_.Value })
$startup = New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{
    ShowWindow = [uint16]0; EnvironmentVariables = [string[]]$vars
}
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $spec.command; CurrentDirectory = $spec.cwd; ProcessStartupInformation = $startup
}
if ($result.ReturnValue -ne 0) { exit ([int]$result.ReturnValue) }
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps({"command": subprocess.list2cmdline(command),
                          "cwd": str(cwd), "environment": environment}),
        capture_output=True, text=True, timeout=20, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise OSError(f"Independent knowledge service launch failed (code {result.returncode})")


@contextmanager
def runtime_lock(compose_file: Path, *, timeout_seconds: float = 360) -> Iterator[None]:
    """Serialize recovery and idle shutdown across Hermes MCP and bridge processes."""
    lock_path = compose_file.parent / ".uuma-kag-runtime.lock"
    deadline = time.monotonic() + timeout_seconds
    with lock_path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError) as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for the KAG runtime lock.") from exc
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class KagIdleTracker:
    """Count in-flight KAG work and atomically claim a genuinely idle shutdown."""

    def __init__(self, idle_seconds: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self.idle_seconds = idle_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._active = 0
        self._last_activity = self._clock()
        self._closing = False

    def begin(self) -> bool:
        with self._lock:
            if self._closing:
                return False
            self._active += 1
            self._last_activity = self._clock()
            return True

    def end(self) -> None:
        with self._lock:
            if self._active <= 0:
                raise RuntimeError("KAG activity counter is unbalanced")
            self._active -= 1
            self._last_activity = self._clock()

    def claim_idle_shutdown(self) -> bool:
        with self._lock:
            if self._closing or self._active:
                return False
            if self._clock() - self._last_activity < self.idle_seconds:
                return False
            self._closing = True
            return True

    def idle_due(self) -> bool:
        with self._lock:
            return (
                not self._closing
                and self._active == 0
                and self._clock() - self._last_activity >= self.idle_seconds
            )

    @property
    def closing(self) -> bool:
        with self._lock:
            return self._closing
