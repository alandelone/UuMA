from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Error as PlaywrightError

from uuma import mcp_chatgpt
from uuma.auth import TokenRegistry
from uuma.chatgpt_bridge import BridgeStore, Consultation, conversation_url
from uuma.chatgpt_browser import BridgeRunner, BrowserBlocked, ChatGPTBrowser
from uuma.chatgpt_cli import dashboard_url
from uuma.chatgpt_deploy import configure, deploy, rollback
from uuma.chatgpt_extension import ExtensionBroker
from uuma.chatgpt_server import admin_secret, create_app
from uuma.chrome_profiles import chrome_profiles, validate_chrome_profile
from uuma.event_store import EventStore


@pytest.fixture
def store(tmp_path):
    EventStore(tmp_path / "uuma.db")
    store = BridgeStore(tmp_path / "uuma.db")
    with store.connect() as db:
        for agent in ("brainstormer", "wisdom-oldman", "orchestrator", "forge-lab-bot",
                      "scholar", "yonc"):
            db.execute("""INSERT INTO tasks(task_id,title,status,assignee,contract_json,
                current_run_id,updated_sequence) VALUES(?,?,'RUNNING',?,'{}',?,0)""",
                       ("task-" + agent, agent, agent, "run-" + agent))
            db.execute("""INSERT INTO runs(run_id,task_id,agent_id,status,source,
                execution_class,progress_json,updated_sequence)
                VALUES(?,?,?,'RUNNING','direct','READ_ONLY','{}',0)""",
                       ("run-" + agent, "task-" + agent, agent))
    store.add_account("main", "person@example.com", "Personal")
    store.account_state("main", "READY", ["chat", "search", "deep_research"])
    return store


def request(agent="brainstormer", **changes):
    body = {"run_id": "run-" + agent, "prompt": "Compare two designs",
            "idempotency_key": "one"}
    body.update(changes)
    return Consultation(**body)


def test_browser_relaunches_after_cached_context_disconnects(tmp_path):
    class FakeBrowser:
        def __init__(self, connected):
            self.connected = connected

        def is_connected(self):
            return self.connected

    class FakeContext:
        def __init__(self, connected):
            self.browser = FakeBrowser(connected)
            self.timeout = None

        def set_default_timeout(self, value):
            self.timeout = value

    fresh = FakeContext(True)
    launches = []
    chromium = SimpleNamespace(
        launch_persistent_context=lambda *args, **kwargs: launches.append((args, kwargs)) or fresh
    )
    browser = ChatGPTBrowser(tmp_path)
    browser.runtime = SimpleNamespace(chromium=chromium)
    browser.contexts["main"] = FakeContext(False)

    assert browser.context("main") is fresh
    assert len(launches) == 1
    assert fresh.timeout == 5000


def test_browser_retries_when_page_closes_during_human_handoff(tmp_path, monkeypatch):
    target_closed_error = type("TargetClosedError", (PlaywrightError,), {})

    class Page:
        url = "https://chatgpt.com/"

        def __init__(self, closes=False):
            self.closes = closes
            self.visits = []

        def is_closed(self):
            return False

        def goto(self, url, **kwargs):
            self.url = url
            self.visits.append((url, kwargs))

        def bring_to_front(self):
            if self.closes:
                raise target_closed_error("closed during handoff")

    stale, fresh = Page(closes=True), Page()
    contexts = iter([
        SimpleNamespace(pages=[stale]),
        SimpleNamespace(pages=[], new_page=lambda: fresh),
    ])
    browser = ChatGPTBrowser(tmp_path)
    monkeypatch.setattr(browser, "context", lambda alias: next(contexts))

    assert browser.open({"alias": "main"}) is fresh
    assert fresh.visits == [("https://chatgpt.com/", {"wait_until": "domcontentloaded"})]


def test_browser_opens_selected_normal_chrome_profile_without_reading_cookies(
    tmp_path, monkeypatch
):
    opened = []
    monkeypatch.setattr(
        "uuma.chatgpt_browser.open_chrome_profile", lambda profile: opened.append(profile)
    )
    browser = ChatGPTBrowser(tmp_path)
    account = {"alias": "main", "chrome_profile": "Profile 10",
               "identity": "person@example.com", "workspace": "Personal"}
    assert browser.open(account) is None
    assert opened == ["Profile 10"]
    with pytest.raises(BrowserBlocked, match="EXTENSION_CONNECTION_REQUIRED"):
        browser.verify(account)


def test_extension_deep_research_uses_confirmed_slash_command(tmp_path):
    calls = []

    class Extension:
        def call(self, alias, action, payload):
            calls.append((alias, action, payload))
            if action == "prepare":
                return {"url": "https://chatgpt.com/"}
            if action == "send":
                return {"url": "https://chatgpt.com/c/test"}
            raise AssertionError(action)

    browser = ChatGPTBrowser(tmp_path, Extension())
    account = {
        "alias": "main",
        "chrome_profile": "Profile 10",
        "identity": "person@example.com",
        "workspace": "Personal",
    }

    req = {
        "id": "cgpt-test",
        "account": "main",
        "mode": "deep_research",
        "payload": {"prompt": "Investigate this", "sites": [], "parent_id": None},
    }

    browser.prepare(account, req, None)
    browser.send(req)

    assert [call[1] for call in calls] == ["prepare", "send"]
    assert calls[0][2]["mode"] == "chat"
    assert calls[1][2]["prompt"].startswith("/Deepresearch [UuMA consultation cgpt-test]")


def test_user_confirmed_deep_research_survives_browser_reverification(store):
    store.confirm_capability("main", "deep_research", True)
    store.account_state("main", "READY", ["chat", "search"])
    account = next(row for row in store.accounts() if row["alias"] == "main")
    assert json.loads(account["capabilities"]) == ["chat", "deep_research", "search"]
    assert json.loads(account["confirmed_capabilities"]) == ["deep_research"]


def test_chrome_profiles_are_discovered_from_local_state(tmp_path):
    state = tmp_path / "Local State"
    state.write_text(json.dumps({"profile": {"info_cache": {
        "Profile 10": {"name": "wan", "user_name": "unimaspv@gmail.com"},
        "System Profile": {"name": "internal"},
    }}}), encoding="utf-8")
    assert chrome_profiles(tmp_path) == [{
        "directory": "Profile 10", "name": "wan", "email": "unimaspv@gmail.com"
    }]
    assert validate_chrome_profile("Profile 10", tmp_path) == "Profile 10"
    with pytest.raises(ValueError, match="available Chrome profile"):
        validate_chrome_profile("Profile 11", tmp_path)


def test_extension_broker_pairs_without_storing_clear_token(tmp_path):
    broker = ExtensionBroker(tmp_path / "pairs.json")
    token = broker.pair("main")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(broker.call, "main", "verify", {"identity": "person@example.com"})
        command = broker.poll("main", token, timeout=2)
        assert command["action"] == "verify"
        broker.complete("main", token, command["id"], {
            "ok": True, "value": {"capabilities": ["chat"]}
        })
        assert future.result(timeout=2) == {"capabilities": ["chat"]}
    assert token not in (tmp_path / "pairs.json").read_text(encoding="utf-8")


def test_mcp_client_starts_bridge_after_loopback_connection_failure(monkeypatch):
    attempts = iter([
        URLError("stopped"),
        {"service": "uuma-chatgpt-bridge"},
        {"status": "QUEUED"},
    ])
    starts = []
    wakes = []

    def fake_open(request):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(mcp_chatgpt, "_open", fake_open)
    monkeypatch.setattr(mcp_chatgpt, "_start_local_bridge", lambda: starts.append(True))
    monkeypatch.setattr(
        mcp_chatgpt,
        "_wake_profile_extension",
        lambda base, agent: wakes.append((base, agent)),
    )
    request = SimpleNamespace(full_url="http://127.0.0.1:8787/agent/requests")
    result = mcp_chatgpt._open_with_lazy_start(request, agent="orchestrator")
    assert result == {"status": "QUEUED"}
    assert starts == [True]
    assert wakes == [("http://127.0.0.1:8787", "orchestrator")]


def test_mcp_profile_wake_uses_routed_profile_and_fragment_secret(tmp_path, monkeypatch):
    class FakeStore:
        def __init__(self, database_path):
            assert database_path == tmp_path / "uuma.db"

        def routes(self):
            return [{"agent": "orchestrator", "account": "main"}]

        def accounts(self):
            return [{"alias": "main", "chrome_profile": "Profile 10"}]

    settings = SimpleNamespace(data_dir=tmp_path, database_path=tmp_path / "uuma.db")
    opened = []
    monkeypatch.setattr(mcp_chatgpt.Settings, "from_env", lambda: settings)
    monkeypatch.setattr(mcp_chatgpt, "BridgeStore", FakeStore)
    monkeypatch.setattr(
        "uuma.chrome_profiles.open_chrome_profile",
        lambda profile, url: opened.append((profile, url)),
    )
    monkeypatch.setattr("uuma.chatgpt_server.admin_secret", lambda data_dir: "secret")

    mcp_chatgpt._wake_profile_extension("http://127.0.0.1:8787", "orchestrator")

    profile, url = opened[0]
    assert profile == "Profile 10"
    assert "connect=main" in url
    assert url.endswith("#token=secret")
    assert "secret" not in url.split("#", 1)[0]


def test_dashboard_launch_url_forces_navigation_without_sending_secret(tmp_path):
    url = dashboard_url(tmp_path, 8787)
    base, fragment = url.split("#", 1)
    assert base.startswith("http://127.0.0.1:8787/?launch=")
    assert fragment == "token=" + admin_secret(tmp_path)
    assert admin_secret(tmp_path) not in base


@pytest.mark.parametrize("agent", ["scholar", "yonc", "unknown", ""])
def test_excluded_identities_cannot_submit_or_read(store, agent):
    with pytest.raises(PermissionError):
        store.request(agent, request(agent))
    with pytest.raises(PermissionError):
        store.threads(agent)


def test_lab_search_only_and_ownership(store):
    with pytest.raises(PermissionError):
        store.request("forge-lab-bot", request("forge-lab-bot"))
    queued = store.request("forge-lab-bot", request("forge-lab-bot", mode="search"))
    with pytest.raises(PermissionError):
        store.get("brainstormer", queued["id"])
    with pytest.raises(PermissionError):
        store.cancel("orchestrator", queued["id"])


def test_run_ownership_epoch_and_terminal_enforced(store):
    with pytest.raises(PermissionError):
        store.request("brainstormer", request(run_id="run-wisdom-oldman"))
    with store.connect() as db:
        db.execute("UPDATE tasks SET current_run_id='replacement' WHERE assignee='brainstormer'")
    with pytest.raises(PermissionError):
        store.request("brainstormer", request())


def test_idempotency_concurrent_and_payload_conflict(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: store.request("brainstormer", request()), range(4)))
    assert len({r["id"] for r in rows}) == 1
    with pytest.raises(ValueError, match="different request"):
        store.request("brainstormer", request(prompt="Different prompt"))
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM chatgpt_events WHERE kind='QUEUED'").fetchone()[0] == 1


def test_per_account_serialization_and_thread_isolation(store):
    first = store.request("brainstormer", request(project="alpha"))
    second = store.request("brainstormer", request(project="beta", idempotency_key="two"))
    assert store.claim()["id"] == first["id"]
    assert store.claim() is None
    store.transition(first["id"], "COMPLETED", expected={"PREFLIGHT"})
    assert store.claim()["id"] == second["id"]
    store.remember_thread(first, "https://chatgpt.com/c/alpha")
    store.remember_thread(second, "https://chatgpt.com/c/beta")
    assert store.thread_url(first) != store.thread_url(second)


def test_thread_cannot_be_stolen_by_rebinding(store):
    store.bind_thread("main", "brainstormer", "alpha", "main", "https://chatgpt.com/c/alpha")
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        store.bind_thread("main", "wisdom-oldman", "beta", "main", "https://chatgpt.com/c/alpha")
    assert store.threads("brainstormer")[0]["url"] == "https://chatgpt.com/c/alpha"


def test_recovery_never_resends_uncertain_submission(store):
    row = store.request("brainstormer", request())
    store.claim()
    store.transition(row["id"], "SENDING", expected={"PREFLIGHT"})
    store.recover()
    assert store.get("brainstormer", row["id"])["status"] == "NEEDS_REVIEW"
    assert store.claim() is None
    store.resume(row["id"])
    assert store.get("brainstormer", row["id"])["status"] == "RUNNING"
    assert store.claim() is None


def test_disabled_account_and_explicit_rebind(store):
    store.account_action("main", "disable")
    with pytest.raises(ValueError, match="ACCOUNT_DISABLED"):
        store.request("brainstormer", request())
    store.add_account("second", "second@example.com", "Personal")
    store.bind("brainstormer", "second")
    assert store.request("brainstormer", request())["account"] == "second"
    with pytest.raises(PermissionError):
        store.request("brainstormer", request(idempotency_key="other", account="main"))


def test_agent_route_can_be_unassigned(store):
    store.bind("brainstormer", "")
    assert not any(route["agent"] == "brainstormer" for route in store.routes())
    with pytest.raises(ValueError, match="No account binding"):
        store.request("brainstormer", request())


@pytest.mark.parametrize("url", ["http://chatgpt.com/c/a", "https://evil.test/c/a",
                                "https://chatgpt.com/share/a", "https://chatgpt.com/c/a?x=y"])
def test_thread_url_rejects_external_and_shared_urls(url):
    with pytest.raises(ValueError):
        conversation_url(url)


class FakeBrowser:
    def __init__(self, *, fail_send=False, result=None):
        self.sent = []
        self.stopped = []
        self.fail_send = fail_send
        self.result = result
        self.page = SimpleNamespace(url="https://chatgpt.com/c/fixture")

    def prepare(self, account, req, url):
        return self.page

    def send(self, req):
        self.sent.append(req["id"])
        if self.fail_send:
            raise BrowserBlocked("SUBMISSION_UNCERTAIN")

    def page_for(self, req, url):
        return self.page

    def observe(self, account, req):
        return self.result

    def stop(self, rid):
        self.stopped.append(rid)


def test_runner_completed_result_and_append_only_event_order(store):
    row = store.request("brainstormer", request())
    result = {"answer": "Located answer", "citations": [{"url": "https://example.com"}],
              "needs_input": False}
    browser = FakeBrowser(result=result)
    runner = BridgeRunner(store, browser)
    runner.tick()
    completed = store.get("brainstormer", row["id"])
    assert completed["status"] == "COMPLETED"
    assert completed["result"] == result
    assert completed["url"] == "https://chatgpt.com/c/fixture"
    runner.tick()
    assert browser.sent == [row["id"]]
    with store.connect() as db:
        events = [r[0] for r in db.execute(
            "SELECT kind FROM chatgpt_events WHERE subject=? ORDER BY sequence", (row["id"],))]
    assert events == ["QUEUED", "PREFLIGHT", "SENDING", "RUNNING", "COMPLETED"]


def test_runner_send_failure_does_not_duplicate(store):
    row = store.request("brainstormer", request())
    browser = FakeBrowser(fail_send=True)
    runner = BridgeRunner(store, browser)
    runner.tick()
    runner.tick()
    assert store.get("brainstormer", row["id"])["status"] == "NEEDS_REVIEW"
    assert len(browser.sent) == 1


def test_runner_cancel_and_expired_run(store):
    row = store.request("brainstormer", request())
    browser = FakeBrowser()
    runner = BridgeRunner(store, browser)
    runner.tick()
    with store.connect() as db:
        db.execute("UPDATE runs SET status='CANCELLED' WHERE run_id='run-brainstormer'")
    runner.tick()
    assert store.get("brainstormer", row["id"])["status"] == "CANCELLED"
    assert row["id"] in browser.stopped


def test_clarification_continuation_preserves_thread_and_rejects_other_project(store):
    row = store.request("brainstormer", request())
    store.transition(row["id"], "AWAITING_INPUT", expected={"QUEUED"},
                     result={"answer": "Which year?", "needs_input": True})
    with pytest.raises(PermissionError):
        store.request("brainstormer", request(idempotency_key="bad", parent_id=row["id"],
                                              project="another"))
    child = store.request("brainstormer", request(idempotency_key="reply", parent_id=row["id"],
                                                 prompt="This year"))
    assert child["thread"] == row["thread"]
    assert store.get("brainstormer", row["id"])["status"] == "COMPLETED"


def test_loopback_auth_agent_scope_and_human_csrf(store, tmp_path):
    credentials = TokenRegistry(tmp_path / "tokens.json").initialize()
    client = TestClient(create_app(tmp_path, start_worker=False), base_url="http://127.0.0.1:8787")
    body = request().model_dump()
    assert client.post("/agent/requests", json=body).status_code == 401
    assert client.get("/human/state").status_code == 401
    headers = {"X-UuMA-Identity": "scholar", "Authorization": "Bearer " + credentials["scholar"]}
    assert client.post("/agent/requests", json=body, headers=headers).status_code == 403
    headers = {"X-UuMA-Identity": "brainstormer",
               "Authorization": "Bearer " + credentials["brainstormer"]}
    assert client.post("/agent/requests", json=body, headers=headers).status_code == 200
    assert client.post("/human/accounts", json={}, headers=headers).status_code == 401
    origin = {"Origin": "http://127.0.0.1:8787"}
    login = client.post("/human/login", json={"token": admin_secret(tmp_path)}, headers=origin)
    assert login.status_code == 200
    assert client.post("/human/accounts/main", json={"action": "disable"}).status_code == 403
    origin["X-Bridge-CSRF"] = login.json()["csrf"]
    assert client.post("/human/accounts/main", json={"action": "disable"}, headers=origin).status_code == 200
    assert client.get("/health", headers={"Host": "evil.test"}).status_code == 403
    assert client.get("/human/state", headers={"Origin": "https://evil.test"}).status_code == 403


def test_human_dashboard_session_survives_service_restart(tmp_path):
    origin = {"Origin": "http://127.0.0.1:8787"}
    first = TestClient(create_app(tmp_path, start_worker=False), base_url="http://127.0.0.1:8787")
    login = first.post("/human/login", json={"token": admin_secret(tmp_path)}, headers=origin)
    cookie = login.cookies.get("bridge_session")

    restarted = TestClient(
        create_app(tmp_path, start_worker=False), base_url="http://127.0.0.1:8787"
    )
    restarted.cookies.set("bridge_session", cookie)
    assert restarted.get("/human/state").status_code == 200


def test_profile_config_is_additive_and_excludes_scholar_yonc():
    for agent in ("brainstormer", "wisdom-oldman", "orchestrator", "forge-lab-bot", "scholar", "yonc"):
        config = {"mcp_servers": {"existing": {"value": "preserve"}, "chatgpt-bridge": {}}}
        configure(config, agent, "python", "src", "data")
        assert config["mcp_servers"]["existing"] == {"value": "preserve"}
        assert ("chatgpt-bridge" in config["mcp_servers"]) == (agent not in {"scholar", "yonc"})


def test_deployment_has_restorable_backups_and_preserves_unrelated_config(tmp_path):
    project, data, hermes = tmp_path / "project", tmp_path / "data", tmp_path / "hermes"
    skill = project / "profiles/shared/chatgpt-consultation/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("consultation skill")
    for home in (hermes, *[hermes / "profiles" / a for a in
                          ("brainstormer", "wisdom-oldman", "forge-lab-bot")]):
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("custom: preserved\n")
    path = deploy(project, data, hermes)
    manifest = json.loads(path.read_text())
    assert len(manifest["files"]) == 8
    assert "custom: preserved" in (hermes / "config.yaml").read_text()
    saved = [f for f in manifest["files"] if f["existed"]]
    assert len(saved) == 4
    assert all(__import__("pathlib").Path(f["backup"]).read_text() == "custom: preserved\n"
               for f in saved)
    rollback(path)
    assert all((home / "config.yaml").read_text() == "custom: preserved\n" for home in
               (hermes, hermes / "profiles/brainstormer", hermes / "profiles/wisdom-oldman",
                hermes / "profiles/forge-lab-bot"))
    assert not any((home / "skills/chatgpt-consultation/SKILL.md").exists() for home in
                   (hermes, hermes / "profiles/brainstormer", hermes / "profiles/wisdom-oldman",
                    hermes / "profiles/forge-lab-bot"))


def test_deployment_removes_bridge_from_excluded_existing_profiles(tmp_path):
    project, data, hermes = tmp_path / "project", tmp_path / "data", tmp_path / "hermes"
    skill = project / "profiles/shared/chatgpt-consultation/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("consultation skill")
    for agent in ("brainstormer", "wisdom-oldman", "forge-lab-bot", "scholar", "yonc"):
        home = hermes / "profiles" / agent
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            "mcp_servers:\n  chatgpt-bridge: {}\nplugins:\n  entries:\n"
            "    uuma_control_guard:\n      mcp_allowlist: [chatgpt-bridge]\n"
        )
        if agent in {"scholar", "yonc"}:
            target = home / "skills/chatgpt-consultation/SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("stale")
    hermes.mkdir(parents=True, exist_ok=True)
    (hermes / "config.yaml").write_text("{}\n")
    deploy(project, data, hermes)
    from ruamel.yaml import YAML

    for agent in ("scholar", "yonc"):
        home = hermes / "profiles" / agent
        config = YAML(typ="safe").load((home / "config.yaml").read_text())
        assert "chatgpt-bridge" not in config["mcp_servers"]
        assert "chatgpt-bridge" not in config["plugins"]["entries"][
            "uuma_control_guard"
        ]["mcp_allowlist"]
        assert not (home / "skills/chatgpt-consultation/SKILL.md").exists()


def test_extension_pair_and_poll_api(store, tmp_path, monkeypatch):
    client = TestClient(
        create_app(tmp_path, start_worker=False), base_url="http://127.0.0.1:8787"
    )
    origin = {"Origin": "http://127.0.0.1:8787"}
    login = client.post("/human/login", json={"token": admin_secret(tmp_path)}, headers=origin)
    csrf_headers = {**origin, "X-Bridge-CSRF": login.json()["csrf"]}

    # Pair fails when no normal Chrome profile configured
    pair_res = client.post("/human/accounts/main/extension-pair", headers=csrf_headers)
    assert pair_res.status_code == 409

    # Set normal Chrome profile
    monkeypatch.setattr(
        "uuma.chatgpt_server.chrome_profiles",
        lambda: [{"directory": "Profile 10", "name": "wan", "email": "person@example.com"}],
    )
    client.post(
        "/human/accounts/main/browser", json={"profile": "Profile 10"}, headers=csrf_headers
    )

    # Now pairing succeeds and returns token
    pair_res = client.post("/human/accounts/main/extension-pair", headers=csrf_headers)
    assert pair_res.status_code == 200
    data = pair_res.json()
    assert data["alias"] == "main"
    assert "token" in data
    assert data["port"] == 8787

    # Poll with wrong token fails
    poll_bad = client.post("/extension/poll", json={"alias": "main", "token": "wrong"})
    assert poll_bad.status_code == 403

    # Extension state before poll is disconnected
    state_res = client.get("/human/state", headers=csrf_headers)
    assert state_res.status_code == 200
    account = next(a for a in state_res.json()["accounts"] if a["alias"] == "main")
    assert not account["extension_connected"]

    # Open dashboard in profile succeeds
    opened_urls = []
    monkeypatch.setattr(
        "uuma.chatgpt_server.open_chrome_profile",
        lambda prof, url: opened_urls.append((prof, url)),
    )
    open_res = client.post(
        "/human/accounts/main/open-dashboard", json={}, headers=csrf_headers
    )
    assert open_res.status_code == 200
    assert len(opened_urls) == 1
    assert opened_urls[0][0] == "Profile 10"
    assert "token=" in opened_urls[0][1]
