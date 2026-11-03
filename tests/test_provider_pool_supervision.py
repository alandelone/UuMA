"""Real Linux process/lease contracts with fake credentials and a fake native binary."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from uuma.provider_pool import AccountPool, atomic_json

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux process supervision")


@pytest.fixture
def supervised_pool(tmp_path):
    command = tmp_path / "native"
    command.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,pathlib,signal,sys,time\n"
        "ready=pathlib.Path(os.environ['GUARD_READY'])\n"
        "if '--orphan' in sys.argv or '--escape' in sys.argv:\n"
        " pid=os.fork()\n"
        " if pid:\n"
        "  while not ready.exists():time.sleep(.01)\n"
        "  sys.exit(0)\n"
        " if '--escape' in sys.argv:os.setsid()\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "fds=[]\n"
        "for fd in pathlib.Path('/proc/self/fd').iterdir():\n"
        " try:fds.append(os.readlink(fd))\n"
        " except OSError:pass\n"
        "ready.write_text(json.dumps({'pid':os.getpid(),'fds':fds}))\n"
        "print('native-ready',flush=True)\n"
        "while True:time.sleep(.05)\n", encoding="utf-8",
    )
    command.chmod(0o700)
    pool = AccountPool(tmp_path / "pool")
    pool.initialize(command)
    pool.add("account-01", label="Fake isolated account")
    token = pool.home("account-01") / ".gemini/antigravity-cli/antigravity-oauth-token"
    token.parent.mkdir(parents=True)
    token.write_text("fake-token-never-sent")
    data = pool._read()
    data["accounts"][0]["authorized"] = True
    atomic_json(pool.index, data)
    return pool


def wait_for(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Process/lease did not reach the required state within the deadline")


def alive(pid):
    path = Path(f"/proc/{pid}/stat")
    try:
        return path.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


@pytest.mark.parametrize("mode", ["--hang", "--orphan", "--escape"])
def test_normal_timeout_and_escaped_descendant_cleanup(supervised_pool, tmp_path, mode):
    pool = supervised_pool
    ready = tmp_path / "ready.json"
    environment = dict(os.environ, GUARD_READY=str(ready), UUMA_AGY_POOL_EXECUTION_TIMEOUT="0.7")
    started = time.monotonic()
    call = subprocess.Popen(
        [sys.executable, "-m", "uuma.provider_pool", "--root", str(pool.root),
         "run", "--", mode], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        wait_for(ready.exists)
        state = json.loads(ready.read_text())
        assert not any("lease.lock" in fd for fd in state["fds"])
        stdout, _ = call.communicate(timeout=6)
        assert call.returncode == (124 if mode == "--hang" else 0)
        assert stdout == b"native-ready\n"
        wait_for(lambda: not alive(state["pid"]))
        assert pool.status()["accounts"][0]["status"] == "READY"
        with pool.lease(wait_timeout=0):
            pass
        assert time.monotonic() - started < 6
    finally:
        if call.poll() is None:
            call.kill()
        call.wait(timeout=6)


@pytest.mark.parametrize("termination", [signal.SIGTERM, signal.SIGKILL])
def test_wrapper_death_cleans_native_and_reports_busy(supervised_pool, tmp_path, termination):
    pool = supervised_pool
    ready = tmp_path / "ready.json"
    call = subprocess.Popen(
        [sys.executable, "-m", "uuma.provider_pool", "--root", str(pool.root),
         "run", "--", "--hang"],
        env=dict(os.environ, GUARD_READY=str(ready)), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for(ready.exists)
        pid = json.loads(ready.read_text())["pid"]
        assert pool.status()["accounts"][0]["status"] == "BUSY"
        assert pool.status()["accounts"][0]["busy"] is True
        os.kill(call.pid, termination)
        call.communicate(timeout=6)
        wait_for(lambda: not alive(pid))
        wait_for(lambda: pool.status()["accounts"][0]["status"] == "READY")
        with pool.lease(wait_timeout=0):
            pass
    finally:
        if call.poll() is None:
            call.kill()
        call.wait(timeout=6)
