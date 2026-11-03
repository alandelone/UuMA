"""Isolated Linux contracts; the fake executable never contacts a model provider."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from uuma.provider_pool import AccountPool, PoolError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux account leases")


@pytest.fixture
def pool(tmp_path):
    command = tmp_path / "fake-agy"
    command.write_text(
        '#!/usr/bin/env python3\n'
        'import os, pathlib, sys\n'
        'home = pathlib.Path.home()\n'
        'if sys.argv[1:] == ["models"]:\n'
        ' print("fake-model")\n'
        'elif "--quota" in sys.argv:\n'
        ' print("RESOURCE_EXHAUSTED", file=sys.stderr); sys.exit(1)\n'
        'elif "--fail" in sys.argv:\n'
        ' sys.exit(1)\n'
        'elif "--lease-child" in sys.argv:\n'
        ' import time\n'
        ' pathlib.Path(os.environ["CHILD_READY"]).write_text("ready")\n'
        ' time.sleep(2)\n'
        'elif "--spawn-orphan" in sys.argv:\n'
        ' import time\n'
        ' if os.fork() == 0:\n'
        '  time.sleep(5); sys.exit(0)\n'
        ' sys.exit(0)\n'
        'else:\n'
        ' token = home / ".gemini/antigravity-cli/jetski-standalone-oauth-token"\n'
        ' token.parent.mkdir(parents=True, exist_ok=True)\n'
        ' token.write_text("fake-token-not-a-real-credential")\n'
        ' print("OK")\n', encoding="utf-8",
    )
    command.chmod(0o700)
    pool = AccountPool(tmp_path / "pool")
    pool.initialize(command)
    return pool


def authorize(pool, account_id="account-01", priority=100):
    pool.add(account_id, label=account_id, priority=priority)
    assert pool.login(account_id) == 0


def test_add_never_imports_or_overwrites_accounts(pool):
    pool.add("account-01", label="Primary", priority=0)
    assert pool.status()["accounts"][0]["status"] == "NEEDS_LOGIN"
    with pytest.raises(PoolError, match="already exists"):
        pool.add("account-01", label="Replacement")
    with pytest.raises(PoolError):
        pool.add("../escape", label="Invalid")
    assert pool.root.stat().st_mode & 0o777 == 0o700


def test_authorization_and_credentials_stay_per_account(pool):
    authorize(pool)
    authorize(pool, "account-02")
    assert pool.home("account-01") != pool.home("account-02")
    assert pool.token("account-01").stat().st_mode & 0o777 == 0o600
    assert all(account["status"] == "READY" for account in pool.status()["accounts"])
    with pytest.raises(PoolError, match="Saved credential"):
        pool.login("account-01")


def test_concurrent_agents_use_distinct_leased_accounts(pool):
    authorize(pool, priority=0)
    authorize(pool, "account-02", priority=100)
    with pool.lease() as (first, _, _):
        assert first["id"] == "account-01"
        with pool.lease() as (second, _, _):
            assert second["id"] == "account-02"
            with pytest.raises(PoolError, match="No authorized account"), pool.lease():
                pytest.fail("An occupied account cannot be leased")


def test_disable_priority_and_missing_token(pool):
    authorize(pool)
    authorize(pool, "account-02")
    pool.configure("account-02", priority=0)
    with pool.lease() as (account, _, _):
        assert account["id"] == "account-02"
    pool.configure("account-02", enabled=False)
    assert pool.status()["accounts"][1]["status"] == "DISABLED"
    pool.token("account-01").unlink()
    assert pool.authentication_token() is None


def test_quota_cools_only_failed_account_and_never_replays(pool, capfd):
    authorize(pool, priority=0)
    authorize(pool, "account-02")
    assert pool.run(["--quota"]) == 1
    assert "RESOURCE_EXHAUSTED" in capfd.readouterr().err
    assert pool.status()["accounts"][0]["status"] == "COOLDOWN"
    with pool.lease() as (account, _, _):
        assert account["id"] == "account-02"


def test_ordinary_error_is_not_treated_as_quota(pool):
    authorize(pool)
    assert pool.run(["--fail"]) == 1
    assert pool.status()["accounts"][0]["status"] == "READY"


def test_provider_binary_change_and_cross_account_resume_fail_closed(pool):
    authorize(pool)
    with pytest.raises(PoolError, match="fresh provider turn"):
        pool.run(["--continue"])
    command = Path(pool._read()["command"])
    command.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(PoolError, match="command changed"), pool.lease():
        pytest.fail("Changed provider binary must be rejected")


def test_only_one_model_verification_attempt_is_allowed(pool):
    pool.add("account-01", label="Primary")
    assert pool.login("account-01", verify_once=True) == 0
    assert pool.status()["verification"]["status"] == "SUCCEEDED"
    pool.add("account-02", label="Backup")
    with pytest.raises(PoolError, match="already been attempted"):
        pool.login("account-02", verify_once=True)


def test_no_secret_values_are_returned_by_status(pool):
    authorize(pool)
    assert "fake-token" not in json.dumps(pool.status())


def test_pinned_cli_filename_wins_over_retained_import_source(pool):
    authorize(pool)
    original = pool.token("account-01")
    assert original.name == "jetski-standalone-oauth-token"
    canonical = original.with_name("antigravity-oauth-token")
    canonical.write_text("fake-canonical-native-token")
    assert pool.token("account-01") == canonical


def test_explicit_account_environment_drops_inherited_credentials(pool, monkeypatch):
    pool.add("account-01", label="Primary")
    monkeypatch.setenv("GOOGLE_API_KEY", "do-not-use")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/another/account.json")
    environment = pool.environment("account-01")
    assert "GOOGLE_API_KEY" not in environment
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in environment
    assert environment["HOME"] == str(pool.home("account-01"))


def test_killed_wrapper_cleans_child_before_releasing_account(pool, tmp_path):
    authorize(pool)
    ready = tmp_path / "child-ready"
    environment = dict(os.environ, CHILD_READY=str(ready))
    wrapper = subprocess.Popen([
        sys.executable, "-m", "uuma.provider_pool", "--root", str(pool.root),
        "run", "--", "--lease-child",
    ], env=environment)
    try:
        import time

        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        wrapper.kill()
        wrapper.wait(timeout=5)
        # The guardian keeps ownership until the cancelled child is gone; the account then
        # becomes available without leaving the old provider alive indefinitely.
        with pool.lease(wait_timeout=5) as (account, _, _):
            assert account["id"] == "account-01"
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
        wrapper.wait(timeout=5)


def test_lease_queues_and_acquires_when_account_freed(pool):
    import threading
    import time
    authorize(pool, priority=0)

    def hold_and_release():
        with pool.lease(wait_timeout=0.0):
            time.sleep(0.4)

    t = threading.Thread(target=hold_and_release)
    t.start()
    time.sleep(0.1)

    with pool.lease(wait_timeout=2.0, poll_interval=0.1) as (second, _, _):
        assert second["id"] == "account-01"

    t.join()


def test_run_queues_waiting_for_busy_account(pool):
    import threading
    import time
    authorize(pool, priority=0)

    def hold():
        with pool.lease(wait_timeout=0.0):
            time.sleep(0.4)

    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.1)

    assert pool.run(["models"], wait_timeout=2.0) == 0
    t.join()


def test_run_reaps_orphaned_holder_so_account_is_immediately_free(pool):
    authorize(pool, priority=0)
    assert pool.run(["--spawn-orphan"]) == 0
    with pool.lease(wait_timeout=0.0) as (account, _, _):
        assert account["id"] == "account-01"
