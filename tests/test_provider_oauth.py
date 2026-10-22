import base64
import hashlib
import json
import sys
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from uuma.provider_oauth import CallbackLogin
from uuma.provider_pool import AccountPool, PoolError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux account pool")


@pytest.fixture
def pool(tmp_path):
    command = tmp_path / "fake-agy"
    command.write_text(
        '#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
        'if sys.argv[1:] != ["models"]: sys.exit(99)\n'
        'if not (Path.home()/".gemini/antigravity-cli/antigravity-oauth-token").is_file(): '
        'sys.exit(1)\n'
        'print("fake-model")\n', encoding="utf-8",
    )
    command.chmod(0o700)
    pool = AccountPool(tmp_path / "pool")
    pool.initialize(command)
    return pool


def wait(console, state):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = console.snapshot()
        if snapshot["status"] == state:
            return snapshot
        time.sleep(0.01)
    pytest.fail(f"Expected {state}, got {console.snapshot()}")


def setup(pool, *, http=None, lifetime=5):
    pool.add("account-01", label="Primary")
    (pool.root / "oauth-client.json").write_text(json.dumps({
        "client_id": "fake.apps.googleusercontent.com", "client_secret": "fake-client-config",
    }))
    calls = []

    def fake_google(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/token"):
            return {"access_token": "fake-access-not-real", "refresh_token": "fake-refresh-not-real",
                    "expires_in": 3600, "token_type": "Bearer"}
        return {"id": "google-subject-1", "email": "fake@example.test", "verified_email": True}

    console = CallbackLogin(pool, http=http or fake_google, lifetime=lifetime)
    console.start("account-01")
    state = wait(console, "WAITING_FOR_BROWSER")
    parameters = parse_qs(urlsplit(state["url"]).query)
    return console, parameters, calls


def test_callback_checks_identity_saves_native_credential_then_checks_cli(pool):
    console, parameters, calls = setup(pool)
    assert all(len(values) == 1 for values in parameters.values())
    assert parameters["redirect_uri"] == ["http://127.0.0.1:18771/callback"]
    console.callback({"state": parameters["state"][0], "code": "fake-authorization-code"})
    wait(console, "SUCCEEDED")
    assert len(calls) == 2
    form = calls[0][1]["form"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest())
    assert challenge.decode().rstrip("=") == parameters["code_challenge"][0]
    assert form["redirect_uri"] == parameters["redirect_uri"][0]
    assert form["grant_type"] == "authorization_code"
    token = json.loads(pool.token("account-01").read_text())
    assert token["auth_method"] == "consumer"
    assert token["token"]["refresh_token"] == "fake-refresh-not-real"
    assert token["token"]["expiry"].endswith("Z")
    assert pool.token("account-01").name == "antigravity-oauth-token"
    assert pool.token("account-01").stat().st_mode & 0o777 == 0o600
    assert pool.status()["accounts"][0]["status"] == "READY"
    assert pool.status()["verification"] is None
    assert "fake-refresh-not-real" not in json.dumps(console.snapshot())
    assert pool._read()["accounts"][0]["verified_email"] == "fake@example.test"


def test_wrong_state_and_duplicate_callback_are_not_redeemed(pool):
    console, parameters, calls = setup(pool)
    with pytest.raises(PoolError, match="已失效"):
        console.callback({"state": "wrong", "code": "fake-authorization-code"})
    assert calls == []
    data = {"state": parameters["state"][0], "code": "fake-authorization-code"}
    console.callback(data)
    with pytest.raises(PoolError, match="已失效"):
        console.callback(data)
    wait(console, "SUCCEEDED")
    assert len(calls) == 2


def test_expired_callback_and_denial_do_not_store_credentials(pool):
    console, parameters, calls = setup(pool, lifetime=.05)
    wait(console, "FAILED")
    assert "逾時" in console.snapshot()["error"]
    with pytest.raises(PoolError):
        console.callback({"state": parameters["state"][0], "code": "fake-code"})
    assert calls == []
    assert pool.token("account-01") is None


def test_google_denial_has_clear_safe_error(pool):
    console, parameters, calls = setup(pool)
    console.callback({"state": parameters["state"][0], "error": "access_denied"})
    wait(console, "FAILED")
    assert "未獲同意" in console.snapshot()["error"]
    assert calls == []


def test_google_response_or_network_failures_do_not_leak_credentials(pool):
    def failed_http(*_args, **_kwargs):
        raise RuntimeError("private-provider-response-should-not-leak")

    console, parameters, _ = setup(pool, http=failed_http)
    console.callback({"state": parameters["state"][0], "code": "fake-code"})
    wait(console, "FAILED")
    assert "private-provider-response" not in json.dumps(console.snapshot())
    assert pool.token("account-01") is None


def test_duplicate_google_identity_is_not_saved_twice(pool):
    pool.add("existing-account", label="Existing")
    data = pool._read()
    data["accounts"][0]["google_subject"] = "google-subject-1"
    pool.index.write_text(json.dumps(data))
    console, parameters, _ = setup(pool)
    console.callback({"state": parameters["state"][0], "code": "fake-code"})
    wait(console, "FAILED")
    assert "已經加入" in console.snapshot()["error"]
    assert pool.token("account-01") is None


def test_unconfirmed_cli_retains_credential_and_reports_actual_phase(pool, monkeypatch):
    monkeypatch.setattr(pool, "_check", lambda *_args: False)
    console, parameters, _ = setup(pool)
    console.callback({"state": parameters["state"][0], "code": "fake-code"})
    wait(console, "FAILED")
    assert "授權已保存" in console.snapshot()["error"]
    assert pool.token("account-01") is not None
    assert pool.status()["accounts"][0]["status"] == "NEEDS_LOGIN"


def test_account_home_cannot_use_shared_linux_keyring(pool):
    pool.add("account-01", label="Primary")
    address = pool.environment("account-01")["DBUS_SESSION_BUS_ADDRESS"]
    assert address == "unix:path=" + str(pool.home("account-01") / ".no-session-bus")


def test_canceled_login_cannot_redeem_its_old_callback(pool):
    console, parameters, calls = setup(pool)
    console.cancel()
    wait(console, "FAILED")
    assert "已取消" in console.snapshot()["error"]
    with pytest.raises(PoolError):
        console.callback({"state": parameters["state"][0], "code": "old-code"})
    assert calls == []
    assert pool.token("account-01") is None


def test_manual_check_replaces_stale_login_error(pool):
    console = CallbackLogin(pool)
    console.state = {"status": "FAILED", "error": "Old diagnostic"}
    console.checked("account-01", True)
    assert console.snapshot()["status"] == "SUCCEEDED"
    assert "error" not in console.snapshot()
