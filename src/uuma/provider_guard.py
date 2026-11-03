"""Linux per-call supervisor; never executes another turn or opens authorization."""

from __future__ import annotations

import argparse
import ctypes
import os
import select
import signal
import subprocess
import sys
import time


class Cancelled(Exception):
    pass


def _cancel(_signum, _frame):
    raise Cancelled


def _prctl(option: int, value: int) -> None:
    if ctypes.CDLL(None, use_errno=True).prctl(option, value, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot establish provider process supervision")


def _children() -> list[int]:
    # This process is a subreaper. Escaped/double-forked grandchildren are adopted here.
    path = f"/proc/self/task/{os.getpid()}/children"
    with open(path, encoding="ascii") as stream:
        return [int(pid) for pid in stream.read().split()]


def _exec_native(parent: int, command: list[str]) -> None:
    # A fresh interpreter performs setup, avoiding fork callbacks in threaded callers.
    os.setsid()
    _prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG, including supervisor SIGKILL.
    if os.getppid() != parent:
        os._exit(125)
    os.execvpe(command[0], command, os.environ)


def _cleanup(process: subprocess.Popen) -> None:
    # Ignore further cancellation while cleaning up. No other account's PIDs are scanned.
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while True:
        for pid in _children():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
            except ChildProcessError:
                return
        # Keep the lease until descendants are gone, including reparented children.
        time.sleep(0.02)


def supervise(command: list[str], lease_fd: int, lifetime_fd: int, timeout: float) -> int:
    _prctl(36, 1)  # PR_SET_CHILD_SUBREAPER
    os.fstat(lease_fd)  # Fail before spawning if the exclusive lease was not inherited.
    os.fstat(lifetime_fd)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _cancel)
    process = None
    try:
        # Pool and guardian cancellation may happen before native launch. Check EOF first.
        if select.select([lifetime_fd], [], [], 0)[0] and not os.read(lifetime_fd, 1):
            return 125
        # Native children never inherit lease/lifetime FDs.
        process = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--native", str(os.getpid()), *command],
            close_fds=True,
        )
        deadline = time.monotonic() + timeout
        while True:
            code = process.poll()
            if code is not None:
                return code if code >= 0 else 128 - code
            if time.monotonic() >= deadline:
                print("Account pool: Provider execution deadline exceeded; turn not replayed",
                      file=sys.stderr, flush=True)
                return 124
            if select.select([lifetime_fd], [], [], 0.1)[0] and not os.read(lifetime_fd, 1):
                return 125
    except Cancelled:
        return 125
    finally:
        if process is not None:
            _cleanup(process)
        os.close(lifetime_fd)
        os.close(lease_fd)


def main() -> None:
    if sys.argv[1:2] == ["--native"]:
        _exec_native(int(sys.argv[2]), sys.argv[3:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-fd", type=int, required=True)
    parser.add_argument("--lifetime-fd", type=int, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.timeout <= 3600:
        parser.error("A command and a finite execution deadline up to 3600 seconds are required")
    raise SystemExit(supervise(command, args.lease_fd, args.lifetime_fd, args.timeout))


if __name__ == "__main__":
    main()
