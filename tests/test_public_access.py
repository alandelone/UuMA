from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from uuma import public_access as access

TOKEN = "fixture-secret-never-production-" + "x" * 32
HOST = "live.95963210.xyz"


class Chunks(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"data: first\n\n"
        yield b"data: second\n\n"


@pytest.fixture
def ingress(tmp_path):
    token = tmp_path / "access.token"
    token.write_text(TOKEN, encoding="utf-8")
    requests = []

    async def upstream(request):
        requests.append((request, await request.aread()))
        return httpx.Response(200, stream=Chunks(), headers=[
            ("Content-Type", "text/event-stream"),
            ("Set-Cookie", "native_a=1; Path=/"), ("Set-Cookie", "native_b=2; Path=/"),
            ("Cache-Control", "public, max-age=86400"),
        ])

    app = access.create_app(token, httpx.MockTransport(upstream))
    with TestClient(app, base_url=f"https://{HOST}", follow_redirects=False) as client:
        yield client, requests, token


def login(client):
    response = client.get("/?auth=" + TOKEN)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Domain=" not in cookie and TOKEN not in cookie
    return response.cookies.get(access.COOKIE)


@pytest.mark.parametrize("path", ["/", "/assets/app.js", "/api/status", "/docs", "/live/"])
def test_all_paths_are_protected_without_contacting_upstream(ingress, path):
    client, requests, _ = ingress
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert not requests


def test_link_consumes_token_preserves_deep_link_and_cookie_reopens(ingress):
    client, requests, _ = ingress
    response = client.get("/live/?item=example&auth=" + TOKEN + "&x=1&x=2")
    assert response.status_code == 303
    assert response.headers["location"] == "/live/?item=example&x=1&x=2"
    assert not requests
    assert client.get(response.headers["location"]).status_code == 200
    assert client.get("/").status_code == 200
    assert all("auth=" not in str(request.url) for request, _ in requests)


def test_invalid_duplicate_tokens_and_unknown_hosts_fail_closed(ingress):
    client, requests, _ = ingress
    for query in ["?auth=wrong", "?auth=", "?auth=" + TOKEN + "&auth=" + TOKEN]:
        assert client.get("/" + query).status_code == 401
    assert client.get("/", headers={"host": "evil.example"}).status_code == 404
    assert not requests


def test_sessions_are_bound_to_host_expiry_signature_and_current_secret(ingress):
    client, requests, token_file = ingress
    cookie = login(client)
    for value in [cookie + "x", "0.x", "garbage", f"{int(time.time())-1}.x"]:
        assert client.get("/api/status", headers={"cookie": access.COOKIE + "=" + value}).status_code == 401
    assert client.get("/", headers={"host": "scholar.95963210.xyz",
                                   "cookie": access.COOKIE + "=" + cookie}).status_code == 401
    token_file.write_text("changed-credential-" + "y" * 40, encoding="utf-8")
    assert client.get("/api/status").status_code == 401
    token_file.unlink()
    assert client.get("/api/status").status_code == 401
    assert not requests


def test_proxies_body_query_stream_and_native_cookies_without_ingress_cookie(ingress):
    client, requests, _ = ingress
    login(client)
    response = client.post("/api/save?item=a%2Fb&x=1&x=2", content=b"fixture body",
                           headers={"origin": f"https://{HOST}",
                                    "cookie": f"{access.COOKIE}={client.cookies.get(access.COOKIE)}; native=ok",
                                    "x-forwarded-host": "evil.example"})
    assert response.status_code == 200
    assert response.content == b"data: first\n\ndata: second\n\n"
    assert len(response.headers.get_list("set-cookie")) == 2
    assert response.headers["cache-control"] == "private, no-store"
    request, body = requests[-1]
    assert body == b"fixture body"
    assert str(request.url).endswith("/api/save?item=a%2Fb&x=1&x=2")
    assert access.COOKIE not in request.headers["cookie"]
    assert "native=ok" in request.headers["cookie"]
    assert request.headers["x-forwarded-host"] == HOST
    assert client.post("/api/save", headers={"origin": "https://evil.example"}).status_code == 403
    assert len(requests) == 1


def test_hermes_existing_host_override_is_supported(ingress):
    client, requests, _ = ingress
    response = client.get("/?auth=" + TOKEN, headers={"host": "localhost:9119"})
    cookie = response.cookies.get(access.COOKIE)
    assert response.status_code == 303
    response = client.get("/api/status", headers={"host": "localhost:9119",
                          "cookie": f"{access.COOKIE}={cookie}"})
    assert response.status_code == 200
    assert str(requests[0][0].url) == "http://127.0.0.1:9119/api/status"


@pytest.mark.parametrize("host", list(access.SITES))
def test_all_three_sites_issue_six_month_cookies(ingress, host):
    client, _, _ = ingress
    response = client.get("/?auth=" + TOKEN, headers={"host": host})
    assert response.status_code == 303
    assert "Max-Age=15552000" in response.headers["set-cookie"]
    expires = int(response.cookies.get(access.COOKIE).split(".")[0])
    assert abs(expires - time.time() - 15552000) < 2


def test_signed_session_survives_eight_hours_and_expires_at_180_days(ingress, monkeypatch):
    client, _, _ = ingress
    clock = [int(time.time())]
    monkeypatch.setattr(access.time, "time", lambda: clock[0])
    cookie = login(client)
    start = clock[0]
    for elapsed in [28801, 90 * 86400, 180 * 86400 - 1]:
        clock[0] = start + elapsed
        assert access.valid_cookie(cookie, TOKEN, HOST)
    clock[0] = start + 180 * 86400
    assert not access.valid_cookie(cookie, TOKEN, HOST)


def test_real_websocket_denies_anonymous_and_relays_text_binary_and_subprotocol(ingress, monkeypatch):
    client, _, _ = ingress
    backend = FastAPI()

    @backend.websocket("/echo")
    async def echo(ws: WebSocket):
        await ws.accept(subprotocol="fixture")
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await ws.send_bytes(message["bytes"])
                else:
                    await ws.send_text(message["text"])
        except WebSocketDisconnect:
            pass

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(10)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(backend, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        monkeypatch.setitem(access.SITES, HOST, ("Fixture", f"http://127.0.0.1:{port}"))
        with (pytest.raises(WebSocketDisconnect),
              client.websocket_connect(f"wss://{HOST}/echo", subprotocols=["fixture"])):
            pass
        login(client)
        with (pytest.raises(WebSocketDisconnect),
              client.websocket_connect(f"wss://{HOST}/echo",
                                       headers={"origin": "https://evil.example"})):
            pass
        with client.websocket_connect(f"wss://{HOST}/echo", subprotocols=["fixture"],
                                      headers={"origin": f"https://{HOST}"}) as ws:
            assert ws.accepted_subprotocol == "fixture"
            ws.send_text("fixture text")
            assert ws.receive_text() == "fixture text"
            ws.send_bytes(b"\x00\x01\xff")
            assert ws.receive_bytes() == b"\x00\x01\xff"
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive()
