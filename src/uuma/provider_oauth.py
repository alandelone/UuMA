"""Antigravity desktop OAuth callback over the workstation's private SSH forward.

Uses the installed desktop client's application configuration, never an existing account's
credentials. Account tokens and PKCE verifiers are never included in public status or logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from .provider_pool import AccountPool, PoolError, atomic_json, file_lock
except ImportError:
    from uuma_provider_pool import AccountPool, PoolError, atomic_json, file_lock

SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "https://www.googleapis.com/auth/aicode",
    "openid",
)


def google_json(url: str, *, form=None, access_token=None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not emit provider response bodies: they may contain codes or credentials.
        raise PoolError(f"Google 授權服務回報 HTTP {exc.code}，請重新登入。") from None
    except (URLError, TimeoutError) as exc:
        raise PoolError("伺服器連接 Google 授權服務逾時，請重新登入。") from exc


class CallbackLogin:
    def __init__(self, pool: AccountPool, *, browser_port=18771, http=google_json,
                 lifetime=300):
        self.pool = pool
        self.redirect = f"http://127.0.0.1:{browser_port}/callback"
        self.http = http
        self.lifetime = lifetime
        self.lock = threading.Lock()
        self.state = {"status": "IDLE", "mode": "callback"}
        self.pending = None

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def start(self, account_id: str):
        self.pool._account(self.pool._read(), account_id)
        if self.pool.token(account_id):
            raise PoolError("此位置已有授權，請按『檢查授權』，不會覆蓋已保存的資料。")
        client_path = self.pool.root / "oauth-client.json"
        if client_path.is_symlink():
            raise PoolError("OAuth 應用程式設定不可使用連結。")
        try:
            client = json.loads(client_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PoolError("尚未配置桌面 OAuth 應用程式。") from exc
        if (not str(client.get("client_id", "")).endswith(".apps.googleusercontent.com")
                or not client.get("client_secret")):
            raise PoolError("OAuth 應用程式設定不完整。")
        verifier = secrets.token_urlsafe(64)
        nonce = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        query = urlencode({
            "client_id": client["client_id"], "redirect_uri": self.redirect,
            "response_type": "code", "scope": " ".join(SCOPES),
            "access_type": "offline", "prompt": "consent select_account", "state": nonce,
            "code_challenge": challenge.decode().rstrip("="), "code_challenge_method": "S256",
        })
        pending = {"account_id": account_id, "client": client, "verifier": verifier,
                   "state": nonce, "event": threading.Event(), "code": None,
                   "received": False, "deadline": time.monotonic() + self.lifetime}
        with self.lock:
            if self.pending is not None:
                raise PoolError("請先完成目前的登入，或等待目前流程結束。")
            self.pending = pending
            self.state = {"status": "STARTING", "mode": "callback", "account_id": account_id}
        threading.Thread(target=self._authorize, args=(pending, query), daemon=True).start()

    def callback(self, parameters: dict[str, str]):
        with self.lock:
            pending = self.pending
            if (pending is None or pending["received"]
                    or time.monotonic() > pending["deadline"]
                    or not hmac.compare_digest(parameters.get("state", ""), pending["state"])):
                raise PoolError("這次授權已失效，請回管理頁重新登入。")
            if parameters.get("error"):
                pending["received"] = True
                pending["error"] = "Google 授權未獲同意，沒有加入帳戶。"
                pending["event"].set()
                return
            code = parameters.get("code", "")
            if not code or len(code) > 4096 or any(ord(c) < 32 for c in code):
                raise PoolError("授權回呼沒有有效授權碼。")
            pending["received"] = True
            pending["code"] = code
            self.state = {"status": "AUTHORIZING", "mode": "callback",
                          "account_id": pending["account_id"], "phase": "交換 Google 授權"}
            pending["event"].set()

    def submit(self, *_args):
        raise PoolError("新版使用 Google 自動回呼，不需要貼授權碼。請重新開啟管理入口。")

    def checked(self, account_id: str, authorized: bool):
        with self.lock:
            if self.pending is None:
                self.state = {"status": "SUCCEEDED" if authorized else "FAILED",
                              "mode": "callback", "account_id": account_id}
                if not authorized:
                    self.state["error"] = "授權已保存，CLI 檢查未通過；請稍後再檢查。"

    def cancel(self):
        with self.lock:
            if self.pending is None or self.state["status"] not in {"STARTING", "WAITING_FOR_BROWSER"}:
                raise PoolError("目前沒有等待中的登入；交換中的授權請等待確認結果。")
            self.pending["received"] = True
            self.pending["error"] = "已取消這次登入，可以重新選擇帳戶。"
            self.pending["event"].set()

    def _authorize(self, pending: dict, query: str):
        account_id = pending["account_id"]
        try:
            with file_lock(self.pool.home(account_id).parent / "lease.lock", blocking=False) as fd:
                with self.lock:
                    self.state.update(status="WAITING_FOR_BROWSER",
                                      url="https://accounts.google.com/o/oauth2/v2/auth?" + query,
                                      expires_at=time.time() + self.lifetime)
                if not pending["event"].wait(self.lifetime):
                    raise PoolError("登入連結已逾時，請重新按登入。")
                if pending.get("error"):
                    raise PoolError(pending["error"])
                client = pending["client"]
                result = self.http("https://oauth2.googleapis.com/token", form={
                    "client_id": client["client_id"], "client_secret": client["client_secret"],
                    "redirect_uri": self.redirect, "code": pending["code"],
                    "grant_type": "authorization_code", "code_verifier": pending["verifier"],
                })
                if not result.get("access_token") or not result.get("refresh_token"):
                    raise PoolError("Google 沒有提供完整授權，請重新登入並同意存取。")
                identity = self.http("https://www.googleapis.com/oauth2/v2/userinfo",
                                     access_token=result["access_token"])
                subject, email = identity.get("id"), identity.get("email")
                if not subject or not email or identity.get("verified_email") is not True:
                    raise PoolError("無法確認 Google 帳戶身分，沒有加入帳戶。")
                with file_lock(self.pool.root / "metadata.lock"):
                    data = self.pool._read()
                    if any(a.get("google_subject") == subject and a["id"] != account_id
                           for a in data["accounts"]):
                        raise PoolError("這個 Google 帳戶已經加入帳戶池，請選擇其他帳戶。")
                    expiry = datetime.fromtimestamp(time.time() + float(result["expires_in"]), UTC)
                    directory = self.pool.home(account_id) / ".gemini" / "antigravity-cli"
                    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
                    directory.parent.chmod(0o700)
                    directory.chmod(0o700)
                    token_path = directory / "antigravity-oauth-token"
                    if token_path.exists() or self.pool.token(account_id) is not None:
                        raise PoolError("已有授權資料，不會覆蓋。")
                    # Desktop client credential schema also used by Anti-Tools CLI integration.
                    atomic_json(token_path, {"token": {
                        "access_token": result["access_token"],
                        "refresh_token": result["refresh_token"],
                        "token_type": result.get("token_type", "Bearer"),
                        "expiry": expiry.isoformat().replace("+00:00", "Z"),
                    }, "auth_method": "consumer"})
                    account = self.pool._account(data, account_id)
                    account.update(google_subject=subject, verified_email=email,
                                   authorization_source="desktop-oauth-callback")
                    atomic_json(self.pool.index, data)
                with self.lock:
                    self.state.update(phase="授權已保存，正在檢查 CLI 連線")
                if not self.pool._check(account_id, fd):
                    raise PoolError("授權已保存，但 CLI 連線尚未確認。請按『檢查授權』。")
                with self.lock:
                    self.state = {"status": "SUCCEEDED", "mode": "callback",
                                  "account_id": account_id}
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            # Only explicit safe messages are published; never serialize network responses.
            message = str(exc) if isinstance(exc, PoolError) else "授權處理未完成，請重新登入。"
            with self.lock:
                self.state = {"status": "FAILED", "mode": "callback", "account_id": account_id,
                              "error": message}
        finally:
            pending["code"] = pending["verifier"] = None
            with self.lock:
                self.pending = None
