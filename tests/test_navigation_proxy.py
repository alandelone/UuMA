import sqlite3

import httpx
import pytest
from starlette.testclient import TestClient

from uuma.navigation_proxy import BODY_LIMIT, create_app


def application(tmp_path, handler, **options):
    token = tmp_path / "orchestrator.token"
    token.write_text("isolated-orchestrator-token", encoding="utf-8")
    return create_app(
        "http://127.0.0.1:18773", token, transport=httpx.MockTransport(handler), **options,
    )


def test_proxy_uses_fixed_authority_and_never_opens_local_database(tmp_path, monkeypatch):
    observed = []

    def upstream(request):
        observed.append(request)
        return httpx.Response(200, json={"status": "owner-result"})

    def forbidden(*args, **kwargs):
        raise AssertionError("A navigation facade cannot open a local database")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    app = application(tmp_path, upstream)
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        response = client.post("/api/v1/review?scope=topic", json={"approve": True}, headers={
            "Authorization": "Bearer supplied-by-caller", "X-Uuma-Identity": "brainstormer",
            "Origin": "http://localhost:8772",
        })
        assert response.status_code == 200
        assert response.json() == {"status": "owner-result"}
        assert response.headers["access-control-allow-origin"] == "http://localhost:8772"
    assert len(observed) == 1
    sent = observed[0]
    assert str(sent.url) == "http://127.0.0.1:18773/api/v1/review?scope=topic"
    assert sent.headers["authorization"] == "Bearer isolated-orchestrator-token"
    assert sent.headers["x-uuma-identity"] == "orchestrator"
    assert sent.content == b'{"approve":true}'


def test_offline_returns_explicit_wait_without_retry_or_fallback(tmp_path):
    attempts = []

    def offline(request):
        attempts.append(request.url)
        raise httpx.ConnectError("unavailable", request=request)

    app = application(tmp_path, offline)
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert "waiting" in response.json()["detail"]
    assert len(attempts) == 1
    assert "token" not in response.text


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example:8772"},
    {"Origin": "http://evil.example"},
    {"Origin": "null"},
])
def test_proxy_refuses_nonlocal_host_or_external_origin(tmp_path, headers):
    calls = []
    app = application(tmp_path, lambda request: calls.append(request))
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        assert client.post("/api/v1/navigation", json={}, headers=headers).status_code == 403
    assert calls == []


def test_explicit_local_ui_origin_and_preflight(tmp_path):
    calls = []
    app = application(
        tmp_path, lambda request: calls.append(request),
        allowed_origins={"http://localhost:3000"},
    )
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        response = client.options("/api/v1/navigation", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
        })
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert calls == []


def test_proxy_does_not_follow_redirects_or_return_sensitive_headers(tmp_path):
    calls = []

    def upstream(request):
        calls.append(request.url)
        return httpx.Response(302, content=b"upstream redirect", headers={
            "Location": "http://external.example/", "Connection": "keep-alive, X-Private",
            "X-Private": "hidden", "Authorization": "Bearer do-not-return",
            "Set-Cookie": "secret=cookie", "Content-Type": "text/plain", "ETag": "safe",
        })

    app = application(tmp_path, upstream)
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        response = client.get("/health", follow_redirects=False)
    assert response.status_code == 302
    assert response.content == b"upstream redirect"
    for key in ("location", "connection", "x-private", "authorization", "set-cookie"):
        assert key not in response.headers
    assert response.headers["etag"] == "safe"
    assert len(calls) == 1


def test_proxy_rejects_large_body_and_unknown_route_before_contacting_owner(tmp_path):
    calls = []
    app = application(tmp_path, lambda request: calls.append(request))
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        assert client.post("/api/v1/navigation", content=b"x" * (BODY_LIMIT + 1)).status_code == 413
        assert client.get("/anything?url=http://external.example").status_code == 404
    assert calls == []


def test_proxy_checks_chunked_size_without_trusting_declared_length(tmp_path):
    calls = []
    app = application(tmp_path, lambda request: calls.append(request))
    with TestClient(app, base_url="http://127.0.0.1:8772") as client:
        response = client.post("/api/v1/navigation", content=iter([b"x" * BODY_LIMIT, b"y"]))
    assert response.status_code == 413
    assert calls == []


@pytest.mark.parametrize("url", [
    "http://external.example", "http://user:password@127.0.0.1:18773",
    "http://127.0.0.1:18773/api/v1", "http://127.0.0.1:18773/?token=secret",
])
def test_proxy_cannot_be_configured_as_arbitrary_url_relay(tmp_path, url):
    token = tmp_path / "orchestrator.token"
    token.write_text("test-token")
    with pytest.raises(ValueError):
        create_app(url, token)
