"""Loopback operator console for adding server accounts over the workstation SSH tunnel.

OAuth returns through a loopback callback, following the installed Anti-Tools desktop flow.
The pinned CLI checks the saved authorization without requesting a model completion.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

try:
    from .provider_oauth import CallbackLogin
    from .provider_pool import AccountPool, PoolError, file_lock
except ImportError:
    from uuma_provider_oauth import CallbackLogin
    from uuma_provider_pool import AccountPool, PoolError, file_lock


def authorization_url(output: str) -> str | None:
    """Extract a complete terminal link, excluding OSC hyperlink BEL/ESC delimiters.

    A native terminal can emit the URL twice: once in OSC 8 metadata, then as visible
    text. A whitespace-only terminator concatenates those two links into invalid OAuth.
    Never repair OAuth parameters by guessing or dropping a repeated value.
    """
    pattern = r"https://accounts\.google\.com/o/oauth2/auth\?[^\x00-\x20\x7f]+(?=[\x00-\x20\x7f])"
    required = {"client_id", "redirect_uri", "response_type", "scope", "state",
                "code_challenge", "code_challenge_method"}
    for match in re.finditer(pattern, output):
        value = match.group(0)
        parsed = urlsplit(value)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        keys = [key for key, _ in pairs]
        parameters = dict(pairs)
        if (len(keys) != len(set(keys)) or not required.issubset(parameters)
                or any(not parameters[key] for key in required)
                or parameters["code_challenge_method"] != "S256"
                or parameters["response_type"] != "code"
                or parameters["redirect_uri"] != "https://antigravity.google/oauth-callback"):
            continue
        return value
    return None


class LoginConsole:
    def __init__(self, pool: AccountPool):
        self.pool = pool
        self.lock = threading.Lock()
        self.state = {"status": "IDLE"}
        self.master = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def start(self, account_id: str):
        self.pool._account(self.pool._read(), account_id)
        if self.pool.token(account_id):
            raise PoolError("此帳戶已有授權；請先檢查狀態，或新增另一個帳戶位置。")
        with self.lock:
            if self.state["status"] in {"STARTING", "WAITING_FOR_CODE", "AUTHORIZING"}:
                raise PoolError("請先完成目前的帳戶登入。")
            self.state = {"status": "STARTING", "account_id": account_id,
                          "attempt_id": secrets.token_urlsafe(18)}
        threading.Thread(target=self._login, args=(account_id,), daemon=True).start()

    def submit(self, code: str, attempt_id: str):
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9._~/-]{10,2048}", code):
            raise PoolError("請只貼上 Google 顯示的授權碼。")
        with self.lock:
            if (self.state["status"] != "WAITING_FOR_CODE" or self.master is None
                    or not hmac.compare_digest(str(attempt_id), self.state["attempt_id"])):
                raise PoolError("此登入流程已失效；請重新按登入。")
            os.write(self.master, code.encode() + b"\r")
            self.state["status"] = "AUTHORIZING"
            self.state.pop("url", None)

    def _login(self, account_id: str):
        import pty
        import select

        process = None
        master = slave = None
        try:
            with file_lock(self.pool.home(account_id).parent / "lease.lock", blocking=False) as fd:
                master, slave = pty.openpty()
                environment = self.pool.environment(account_id)
                environment["TERM"] = "xterm-256color"
                process = subprocess.Popen(
                    [self.pool._command(self.pool._read())],
                    cwd=self.pool.home(account_id).parent / "login-workspace",
                    env=environment, stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True, pass_fds=(fd,),
                )
                os.close(slave)
                slave = None
                with self.lock:
                    self.master = master
                output = ""
                selected = False
                deadline = time.monotonic() + 150
                while process.poll() is None and time.monotonic() < deadline:
                    if self.pool.token(account_id):
                        break
                    if not select.select([master], [], [], 0.1)[0]:
                        continue
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    output = (output + chunk.decode("utf-8", errors="replace"))[-32768:]
                    if "authentication timed out" in output.lower():
                        break
                    if not selected and "Select login method:" in output and "Google OAuth" in output:
                        os.write(master, b"\r")
                        selected = True
                    url = authorization_url(output)
                    if url:
                        with self.lock:
                            if self.state["status"] == "STARTING":
                                self.state.update(status="WAITING_FOR_CODE", url=url)
                # No model prompt is sent. Close the native UI as soon as credentials exist.
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                authorized = self.pool._check(account_id, fd)
                with self.lock:
                    self.state = {"status": "SUCCEEDED" if authorized else "FAILED",
                                  "account_id": account_id}
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # Provider terminal output and authorization codes must never enter HTTP logs.
            with self.lock:
                self.state = {"status": "FAILED", "account_id": account_id}
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            with self.lock:
                self.master = None
            if master is not None:
                os.close(master)
            if slave is not None:
                os.close(slave)


def create_server(pool: AccountPool, token: str, *, port=8771, browser_port=18771,
                  oauth_http=None):
    options = {"http": oauth_http} if oauth_http is not None else {}
    console = CallbackLogin(pool, browser_port=browser_port, **options)
    origins = {f"http://127.0.0.1:{browser_port}", f"http://127.0.0.1:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, value, content_type="application/json; charset=utf-8"):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", (
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
            ))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied, "Bearer " + token)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/callback":
                pairs = parse_qsl(parsed.query, keep_blank_values=True)
                if len(pairs) != len(dict(pairs)):
                    return self.respond(400, {"error": "授權參數重複，請重新登入。"})
                try:
                    console.callback(dict(pairs))
                except PoolError as exc:
                    return self.respond(400, {"error": str(exc)})
                page = (
                    '<!doctype html><meta charset="utf-8"><title>已收到 Google 授權</title>'
                    '<h1>已收到 Google 授權</h1><p>請返回原本的帳戶池頁面查看確認結果。'
                    '此分頁可以關閉。</p>'
                ).encode()
                return self.respond(202, page, "text/html; charset=utf-8")
            if parsed.path == "/":
                page = Path(__file__).with_name("provider_pool.html").read_bytes()
                return self.respond(200, page, "text/html; charset=utf-8")
            if not self.authorized():
                return self.respond(401, {"error": "需要管理入口授權。"})
            if self.path == "/api/status":
                status = pool.status()
                for account in status["accounts"]:
                    account["has_credential"] = pool.token(account["id"]) is not None
                return self.respond(200, {**status, "login": console.snapshot()})
            return self.respond(404, {"error": "找不到此入口。"})

        def do_POST(self):
            if not self.authorized():
                return self.respond(401, {"error": "需要管理入口授權。"})
            if self.headers.get("Origin") not in origins:
                return self.respond(403, {"error": "請從工作站的帳戶池頁面操作。"})
            if self.headers.get("Content-Type") != "application/json":
                return self.respond(415, {"error": "需要 JSON。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid length")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/accounts":
                    account_id = "account-" + secrets.token_hex(5)
                    pool.add(account_id, label=data["label"])
                    return self.respond(201, {"account_id": account_id})
                if self.path == "/api/login":
                    console.start(data["account_id"])
                elif self.path == "/api/code":
                    console.submit(data["code"], data["attempt_id"])
                elif self.path == "/api/cancel":
                    console.cancel()
                elif self.path == "/api/check":
                    authorized = pool.check(data["account_id"])
                    console.checked(data["account_id"], authorized)
                    return self.respond(200, {
                        "authorized": authorized,
                        "message": "CLI 檢查通過，帳戶已可用。" if authorized else
                                   "CLI 檢查未通過，授權仍保留。",
                    })
                elif self.path == "/api/prefer":
                    priority = min([a["priority"] for a in pool._read()["accounts"]] + [100]) - 1
                    pool.configure(data["account_id"], priority=priority)
                elif self.path == "/api/enabled":
                    if not isinstance(data["enabled"], bool):
                        raise ValueError("Invalid enabled")
                    pool.configure(data["account_id"], enabled=data["enabled"])
                else:
                    return self.respond(404, {"error": "找不到此入口。"})
                return self.respond(200, {"accepted": True})
            except PoolError as exc:
                return self.respond(409, {"error": str(exc)})
            except (ValueError, KeyError, TypeError, BlockingIOError):
                return self.respond(400, {"error": "資料不完整，或帳戶正在使用中。"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--browser-port", type=int, default=18771)
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("Operator token must contain at least 32 characters")
    create_server(AccountPool(args.root), token, port=args.port,
                  browser_port=args.browser_port).serve_forever()


if __name__ == "__main__":
    main()
