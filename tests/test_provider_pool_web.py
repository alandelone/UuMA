import json
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from uuma.provider_pool import AccountPool
from uuma.provider_pool_web import LoginConsole, authorization_url, create_server

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux operator console")

AUTH_URL = (
    "https://accounts.google.com/o/oauth2/auth?client_id=fake.apps.googleusercontent.com"
    "&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback&response_type=code"
    "&scope=openid&state=fake-state&code_challenge=fake-challenge&code_challenge_method=S256"
)


@pytest.fixture
def pool(tmp_path):
    command = tmp_path / "fake-agy"
    command.write_text(
        '#!/usr/bin/env python3\n'
        'import json, pathlib, sys, time\n'
        'home = pathlib.Path.home()\n'
        'with (home/"calls.jsonl").open("a") as stream:\n'
        ' stream.write(json.dumps(sys.argv[1:])+"\\n")\n'
        'if sys.argv[1:] == ["models"]:\n'
        ' print("fake-model"); sys.exit(0)\n'
        'print("Select login method: Google OAuth", flush=True)\n'
        'input()\n'
        f'print({AUTH_URL!r}, flush=True)\n'
        'code = input()\n'
        'if code != "fake-code-12345": sys.exit(1)\n'
        'token = home/".gemini/antigravity-cli/jetski-standalone-oauth-token"\n'
        'token.parent.mkdir(parents=True, exist_ok=True)\n'
        'token.write_text("fake-token-not-real")\n'
        'time.sleep(10)\n', encoding="utf-8",
    )
    command.chmod(0o700)
    pool = AccountPool(tmp_path / "pool")
    pool.initialize(command)
    pool.add("account-01", label="Test account")
    return pool


def wait_status(console, status):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if console.snapshot()["status"] == status:
            return console.snapshot()
        time.sleep(0.02)
    pytest.fail(f"Expected {status}, got {console.snapshot()}")


def test_console_authenticates_with_no_model_prompt(pool):
    console = LoginConsole(pool)
    console.start("account-01")
    state = wait_status(console, "WAITING_FOR_CODE")
    assert state["url"].startswith("https://accounts.google.com/")
    console.submit("fake-code-12345", state["attempt_id"])
    wait_status(console, "SUCCEEDED")
    assert pool.status()["accounts"][0]["status"] == "READY"
    assert pool.status()["verification"] is None
    calls = [json.loads(line) for line in (
        pool.home("account-01") / "calls.jsonl"
    ).read_text().splitlines()]
    assert calls == [[], ["models"]]


def test_console_rejects_stale_or_invalid_codes(pool):
    console = LoginConsole(pool)
    from uuma.provider_pool import PoolError

    with pytest.raises(PoolError):
        console.submit("fake-code-12345", "stale")
    with pytest.raises(PoolError):
        console.submit("line1\nline2", "stale")


def test_terminal_hyperlink_does_not_concatenate_duplicate_oauth_parameters():
    terminal = "\x1b]8;;" + AUTH_URL + "\x07" + AUTH_URL[:100]
    assert authorization_url(terminal) == AUTH_URL
    assert authorization_url(AUTH_URL + "\x1b\\") == AUTH_URL


@pytest.mark.parametrize("output", [
    AUTH_URL,  # Partial PTY reads must not publish an unfinished URL.
    AUTH_URL + "&client_id=second\n",
    AUTH_URL.replace("accounts.google.com", "untrusted.example") + "\n",
    AUTH_URL.replace("code_challenge_method=S256", "code_challenge_method=plain") + "\n",
])
def test_incomplete_or_invalid_oauth_link_is_rejected(output):
    assert authorization_url(output) is None


def test_http_requires_operator_token_and_same_origin(pool):
    token = "test-operator-token-not-a-real-credential"
    server = create_server(pool, token, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base) as response:
            assert response.status == 200
            assert "no-store" in response.headers["Cache-Control"]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/api/status")
        assert error.value.code == 401
        request = urllib.request.Request(base + "/api/status", headers={
            "Authorization": "Bearer " + token,
        })
        with urllib.request.urlopen(request) as response:
            assert json.load(response)["accounts"][0]["status"] == "NEEDS_LOGIN"
        request = urllib.request.Request(base + "/api/accounts", data=b'{"label":"Backup"}',
                                         headers={"Authorization": "Bearer " + token,
                                                  "Content-Type": "application/json",
                                                  "Origin": "https://untrusted.example"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 403
        request.add_header("Origin", "http://127.0.0.1:18771")
        with urllib.request.urlopen(request) as response:
            assert response.status == 201
        assert len(pool.status()["accounts"]) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_http_callback_needs_state_and_redeems_without_bearer(pool):
    (pool.root / "oauth-client.json").write_text(json.dumps({
        "client_id": "fake.apps.googleusercontent.com", "client_secret": "fake-client-config",
    }))
    calls = []

    def fake_google(url, **_kwargs):
        calls.append(url)
        return ({"access_token": "fake-access", "refresh_token": "fake-refresh",
                 "expires_in": 3600} if url.endswith("/token") else
                {"id": "subject-1", "email": "fake@example.test", "verified_email": True})

    token = "fake-operator-token-not-a-real-credential"
    server = create_server(pool, token, port=0, oauth_http=fake_google)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def status():
        q = urllib.request.Request(base + "/api/status",
                                   headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(q) as r:
            return json.load(r)

    try:
        q = urllib.request.Request(base + "/api/login", data=b'{"account_id":"account-01"}',
                                   headers={"Authorization": "Bearer " + token,
                                            "Origin": "http://127.0.0.1:18771",
                                            "Content-Type": "application/json"})
        with urllib.request.urlopen(q) as r:
            assert r.status == 200
        deadline = time.monotonic() + 5
        data = status()
        while data["login"]["status"] != "WAITING_FOR_BROWSER" and time.monotonic() < deadline:
            time.sleep(.01)
            data = status()
        state = parse_qs(urlsplit(data["login"]["url"]).query)["state"][0]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/callback?state=wrong&code=fake")
        assert error.value.code == 400
        assert calls == []
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/callback?state=" + state + "&state=second&code=fake")
        assert calls == []
        with urllib.request.urlopen(base + "/callback?" + urlencode({
            "state": state, "code": "fake-code",
        })) as r:
            assert r.status == 202
        deadline = time.monotonic() + 5
        while status()["login"]["status"] != "SUCCEEDED" and time.monotonic() < deadline:
            time.sleep(.01)
        assert status()["accounts"][0]["status"] == "READY"
        assert len(calls) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
