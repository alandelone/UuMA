"""Visible-UI transport. No cookies, hidden account APIs, or credentials are extracted."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .chatgpt_bridge import ACTIVE, BridgeStore
from .chatgpt_extension import ExtensionBroker, ExtensionUnavailable
from .chrome_profiles import open_chrome_profile

LOGGER = logging.getLogger(__name__)


class BrowserBlocked(RuntimeError):
    pass


@dataclass
class ExtensionPage:
    alias: str
    url: str


def consultation_prompt(request: dict) -> str:
    sites = request["payload"]["sites"]
    return (
        f"[UuMA consultation {request['id']}]\n"
        "Treat this as a bounded consultation. Do not use connected apps, upload files, "
        "or perform external actions. Return advice with source links where applicable. "
        "If clarification or research-plan approval is needed, begin with UUMA_NEEDS_INPUT.\n"
        + ("Preferred public websites (preferences, not an enforced filter): "
           + ", ".join(sites) + "\n" if sites else "")
        + request["payload"]["prompt"]
    )


class ChatGPTBrowser:
    """All Playwright operations are owned by the single runner thread."""

    def __init__(self, profile_root: Path, extension: ExtensionBroker | None = None):
        self.profile_root = profile_root
        self.extension = extension
        self.contexts = {}
        self.pages = {}
        self.stable = {}
        self.runtime = None

    def extension_call(self, alias: str, action: str, payload: dict | None = None) -> dict:
        if self.extension is None:
            raise BrowserBlocked("EXTENSION_CONNECTION_REQUIRED")
        try:
            return self.extension.call(alias, action, payload)
        except ExtensionUnavailable as exc:
            raise BrowserBlocked(str(exc)) from exc

    def extension_ready(self, alias: str) -> bool:
        return bool(self.extension and self.extension.is_paired(alias))

    def context(self, alias: str):
        cached = self.contexts.get(alias)
        if cached is not None:
            try:
                browser = cached.browser
                if browser is not None and browser.is_connected():
                    return cached
            except Exception:
                LOGGER.exception("Unable to inspect cached Chrome context for account %s", alias)
            self.contexts.pop(alias, None)
        if alias not in self.contexts:
            from playwright.sync_api import sync_playwright

            if self.runtime is None:
                self.runtime = sync_playwright().start()
            path = (self.profile_root / alias).resolve()
            if path.parent != self.profile_root.resolve():
                raise BrowserBlocked("INVALID_PROFILE")
            path.mkdir(parents=True, exist_ok=True)
            self.contexts[alias] = self.runtime.chromium.launch_persistent_context(
                str(path), channel="chrome", headless=False, accept_downloads=False,
            )
            self.contexts[alias].set_default_timeout(5000)
        return self.contexts[alias]

    def open(self, account: dict):
        if account.get("chrome_profile"):
            if self.extension_ready(account["alias"]):
                result = self.extension_call(account["alias"], "open")
                return ExtensionPage(account["alias"], result.get("url", "https://chatgpt.com/"))
            open_chrome_profile(account["chrome_profile"])
            return None
        from playwright.sync_api import Error as PlaywrightError

        for attempt in range(2):
            context = self.context(account["alias"])
            page = next((
                p for p in context.pages
                if not p.is_closed() and p.url.startswith("https://chatgpt.com")
            ), None)
            try:
                if page is None:
                    page = context.new_page()
                    page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
                page.bring_to_front()
                return page
            except PlaywrightError as exc:
                if type(exc).__name__ != "TargetClosedError":
                    raise
                self.contexts.pop(account["alias"], None)
                if attempt:
                    raise
        raise BrowserBlocked("BROWSER_UNAVAILABLE")  # pragma: no cover - loop always returns/raises

    @staticmethod
    def visible(locator):
        return locator.count() == 1 and locator.is_visible()

    def verify(self, account: dict, page=None):
        if account.get("chrome_profile"):
            result = self.extension_call(account["alias"], "verify", {
                "identity": account["identity"], "workspace": account["workspace"]
            })
            return ExtensionPage(account["alias"], result.get("url", "https://chatgpt.com/"))
        page = page or self.open(account)
        if not page.url.startswith("https://chatgpt.com/"):
            raise BrowserBlocked("AUTH_REQUIRED")
        body = page.locator("body").inner_text()
        if re.search(r"verify you are human|checking your browser|captcha", body, re.IGNORECASE):
            raise BrowserBlocked("CHALLENGE_REQUIRED")
        profile = page.get_by_role("button", name="Open profile menu", exact=True)
        if not self.visible(profile):
            raise BrowserBlocked("AUTH_REQUIRED")
        profile.click()
        try:
            menu = page.get_by_role("menu")
            if not self.visible(menu):
                raise BrowserBlocked("IDENTITY_UNVERIFIED")
            text = menu.inner_text()
            emails = {s.casefold() for s in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)}
            if account["identity"].casefold() not in emails:
                raise BrowserBlocked("WRONG_ACCOUNT" if emails else "IDENTITY_UNVERIFIED")
            # Exact visible workspace label is required; a reachable thread is not identity proof.
            lines = {s.strip().casefold() for s in text.splitlines()}
            if account["workspace"].casefold() not in lines:
                raise BrowserBlocked("WORKSPACE_UNVERIFIED")
        finally:
            page.keyboard.press("Escape")
        return page

    def capabilities(self, account: dict):
        if account.get("chrome_profile"):
            result = self.extension_call(account["alias"], "verify", {
                "identity": account["identity"], "workspace": account["workspace"]
            })
            return result.get("capabilities", ["chat"])
        page = self.verify(account)
        capabilities = ["chat"]
        menu = page.get_by_role("button", name="Add files and more", exact=True)
        if self.visible(menu):
            menu.click()
            try:
                for mode, pattern in (("search", r"^(Web search|Search)$"),
                                      ("deep_research", r"^Deep research$")):
                    item = page.get_by_role("menuitem", name=re.compile(pattern, re.IGNORECASE))
                    if self.visible(item) and item.is_enabled():
                        capabilities.append(mode)
            finally:
                page.keyboard.press("Escape")
        return capabilities

    def page_for(self, request: dict, url: str | None):
        key = request["id"]
        if self.extension_ready(request["account"]):
            result = self.extension_call(request["account"], "locate", {
                "url": url, "request_id": key
            })
            page = ExtensionPage(request["account"], result.get("url", url or ""))
            self.pages[key] = page
            return page
        page = self.pages.get(key)
        if page is not None and not page.is_closed():
            return page
        context = self.context(request["account"])
        page = next((p for p in context.pages if url and p.url == url), None)
        if page is None and not url:
            marker = f"[UuMA consultation {request['id']}]"
            for candidate in context.pages:
                try:
                    if marker in candidate.locator("body").inner_text(timeout=1000):
                        page = candidate
                        break
                except Exception:  # noqa: BLE001,S112 - ignore inaccessible recovery tabs
                    continue
        if page is None:
            page = context.new_page()
            page.goto(url or "https://chatgpt.com/", wait_until="domcontentloaded")
        self.pages[key] = page
        return page

    def prepare(self, account: dict, request: dict, url: str | None):
        if account.get("chrome_profile"):
            result = self.extension_call(account["alias"], "prepare", {
                # A new logical thread must begin on ChatGPT's new-chat page instead
                # of silently reusing whichever conversation tab happens to be open.
                "url": url or f"https://chatgpt.com/#uuma-{request['id']}",
                "request_id": request["id"],
                # A user-confirmed Deep Research account uses ChatGPT's supported
                # slash command, avoiding dependency on mutable tool-menu markup.
                "mode": "chat" if request["mode"] == "deep_research" else request["mode"],
                "parent_id": request["payload"].get("parent_id"),
                "identity": account["identity"],
                "workspace": account["workspace"],
            })
            page = ExtensionPage(account["alias"], result.get("url", url or ""))
            self.pages[request["id"]] = page
            return page
        page = self.page_for(request, url)
        self.verify(account, page)
        body = page.locator("body").inner_text()
        if re.search(
            r"conversation not found|unable to load conversation", body, re.IGNORECASE
        ):
            raise BrowserBlocked("CONVERSATION_UNAVAILABLE")
        if request["payload"].get("parent_id"):
            # A continuation remains in the original mode and exact conversation.
            if not url:
                raise BrowserBlocked("CONVERSATION_UNAVAILABLE")
        elif request["mode"] != "chat":
            menu = page.get_by_role("button", name="Add files and more", exact=True)
            if not self.visible(menu):
                raise BrowserBlocked("CAPABILITY_UNAVAILABLE")
            menu.click()
            pattern = r"^(Web search|Search)$" if request["mode"] == "search" else r"^Deep research$"
            option = page.get_by_role("menuitem", name=re.compile(pattern, re.IGNORECASE))
            if not self.visible(option) or not option.is_enabled():
                page.keyboard.press("Escape")
                raise BrowserBlocked("CAPABILITY_UNAVAILABLE")
            option.click()
            selected = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE))
            if not self.visible(selected):
                raise BrowserBlocked("MODE_UNVERIFIED")
        if not self.visible(page.locator("#prompt-textarea")):
            raise BrowserBlocked("COMPOSER_UNAVAILABLE")
        return page

    def send(self, request: dict):
        page = self.pages[request["id"]]
        prompt = consultation_prompt(request)
        if isinstance(page, ExtensionPage):
            if request["mode"] == "deep_research":
                prompt = "/Deepresearch " + prompt
            result = self.extension_call(page.alias, "send", {
                "request_id": request["id"], "prompt": prompt
            })
            page.url = result.get("url", page.url)
            return
        composer = page.locator("#prompt-textarea")
        composer.fill(prompt)
        send = page.get_by_role(
            "button", name=re.compile(r"^(Send|Send prompt|Send message)$", re.IGNORECASE)
        )
        if not self.visible(send) or not send.is_enabled():
            raise BrowserBlocked("SEND_UNVERIFIED")
        send.click()

    def observe(self, account: dict, request: dict):
        if account.get("chrome_profile"):
            result = self.extension_call(account["alias"], "observe", {
                "url": request["url"],
                "request_id": request["id"],
                "identity": account["identity"],
                "workspace": account["workspace"],
            })
            if result.get("pending"):
                self.stable.pop(request["id"], None)
                return None
            text = str(result.get("answer") or "").strip()
            if not text:
                return None
            digest = hashlib.sha256(text.encode()).hexdigest()
            previous = self.stable.get(request["id"])
            self.stable[request["id"]] = (
                digest,
                previous[1] if previous and previous[0] == digest else time.monotonic(),
            )
            if time.monotonic() - self.stable[request["id"]][1] < 5:
                return None
            citations = result.get("citations") or []
            needs_input = bool(result.get("needs_input"))
            if request["mode"] in {"search", "deep_research"} and not citations and not needs_input:
                raise BrowserBlocked("CITATIONS_UNAVAILABLE")
            return {"answer": text, "citations": citations,
                    "conversation_url": result.get("conversation_url"),
                    "needs_input": needs_input, "completed_at": time.time(),
                    "provenance": "ChatGPT Web consultation; external advice, not accepted knowledge"}
        page = self.page_for(request, request["url"])
        if not request["url"] and request["id"] not in page.locator("body").inner_text():
            raise BrowserBlocked("SUBMISSION_UNCERTAIN")
        body = page.locator("body").inner_text()
        if re.search(
            r"usage limit|reached your.*limit|try again after", body, re.IGNORECASE
        ):
            raise BrowserBlocked("QUOTA_LIMIT")
        users = page.locator('[data-message-author-role="user"]')
        matching = users.filter(has_text=f"[UuMA consultation {request['id']}]")
        if matching.count() != 1:
            raise BrowserBlocked("SUBMISSION_UNCERTAIN")
        # The unique prompt must still be the last user turn. Never capture somebody else's answer.
        if request["id"] not in users.last.inner_text():
            raise BrowserBlocked("CONVERSATION_CHANGED")
        if page.get_by_role("button", name=re.compile(r"^Stop", re.IGNORECASE)).count():
            self.stable.pop(request["id"], None)
            return None
        messages = page.locator('[data-message-author-role="assistant"]')
        if not messages.count():
            return None
        answer = messages.last
        # Require the assistant turn to follow the matching prompt in the rendered DOM.
        ordered = page.locator('[data-message-author-role]').all_text_contents()
        anchor = next((i for i, t in enumerate(ordered) if
                       f"[UuMA consultation {request['id']}]" in t), len(ordered))
        if anchor >= len(ordered) - 1:
            return None
        text = answer.inner_text().strip()
        if not text:
            return None
        digest = hashlib.sha256(text.encode()).hexdigest()
        previous = self.stable.get(request["id"])
        self.stable[request["id"]] = (digest, previous[1] if previous and previous[0] == digest
                                      else time.monotonic())
        if time.monotonic() - self.stable[request["id"]][1] < 5:
            return None
        # A completed message exposes its own copy action. Absence is not completion evidence.
        turn = answer.locator('xpath=ancestor::article')
        if turn.count() != 1 or not turn.get_by_role(
            "button", name=re.compile("Copy", re.IGNORECASE)
        ).count():
            return None
        links = []
        for link in answer.get_by_role("link").all():
            href = link.get_attribute("href") or ""
            if href.startswith(("https://", "http://")):
                links.append({"title": link.inner_text(), "url": href})
        needs_input = "UUMA_NEEDS_INPUT" in text or bool(
            page.get_by_role(
                "button", name=re.compile(r"^Start research$", re.IGNORECASE)
            ).count()
        )
        if request["mode"] in {"search", "deep_research"} and not links and not needs_input:
            raise BrowserBlocked("CITATIONS_UNAVAILABLE")
        self.verify(account, page)
        return {"answer": text, "citations": links, "conversation_url": page.url,
                "needs_input": needs_input, "completed_at": time.time(),
                "provenance": "ChatGPT Web consultation; external advice, not accepted knowledge"}

    def stop(self, rid: str):
        page = self.pages.get(rid)
        if isinstance(page, ExtensionPage):
            self.extension_call(page.alias, "stop", {"request_id": rid})
            return
        if page is not None and not page.is_closed():
            stop = page.get_by_role("button", name=re.compile(r"^Stop", re.IGNORECASE))
            if self.visible(stop):
                stop.click()

    def close(self):
        for context in self.contexts.values():
            context.close()
        if self.runtime:
            self.runtime.stop()


class BridgeRunner:
    def __init__(self, store: BridgeStore, browser: ChatGPTBrowser):
        self.store, self.browser = store, browser
        self.stop_event = threading.Event()
        self.last_tick = 0.0
        self.last_error = None
        self.cancelled = set()

    def remember_thread_if_canonical(self, request: dict, url: str) -> bool:
        """Keep transient ChatGPT URL variants from turning a sent request uncertain."""
        try:
            self.store.remember_thread(request, url)
            return True
        except ValueError:
            LOGGER.info("Waiting for canonical conversation URL for request %s: %s",
                        request["id"], url)
            return False
    def tick(self):
        accounts = {a["alias"]: a for a in self.store.accounts()}
        for account in accounts.values():
            if account["action"]:
                try:
                    if account["action"] == "open":
                        page = self.browser.open(account)
                        status = (
                            "EXTENSION_CONNECTION_REQUIRED"
                            if account.get("chrome_profile") and page is None
                            else "AUTH_REQUIRED"
                        )
                        self.store.account_state(account["alias"], status)
                    else:
                        caps = self.browser.capabilities(account)
                        self.store.account_state(account["alias"], "READY", caps)
                except BrowserBlocked as exc:
                    self.store.account_state(account["alias"], str(exc))
                except Exception:
                    LOGGER.exception("ChatGPT browser action failed for account %s",
                                     account["alias"])
                    self.store.account_state(account["alias"], "BROWSER_UNAVAILABLE")
        for req in self.store.recent():
            if req["status"] == "CANCELLED" and req["id"] not in self.cancelled:
                self.browser.stop(req["id"])
                self.cancelled.add(req["id"])
            if req["status"] in ACTIVE and not accounts[req["account"]]["enabled"]:
                self.browser.stop(req["id"])
                self.store.transition(req["id"], "PAUSED", expected=ACTIVE,
                                      error="ACCOUNT_DISABLED")
        req = self.store.claim()
        if req:
            account = accounts[req["account"]]
            try:
                if req["mode"] not in __import__("json").loads(account["capabilities"]):
                    raise BrowserBlocked("CAPABILITY_UNAVAILABLE")
                page = self.browser.prepare(account, req, self.store.thread_url(req))
                with self.store.connect() as db:
                    self.store.require_run(db, req["agent"], req["run_id"])
                if self.store.transition(req["id"], "SENDING", expected={"PREFLIGHT"}):
                    self.browser.send(req)
                    # Save any assigned conversation URL even when generation is still pending.
                    if "/c/" in page.url:
                        self.remember_thread_if_canonical(req, page.url)
                    self.store.transition(req["id"], "RUNNING", expected={"SENDING"})
            except BrowserBlocked as exc:
                self.store.transition(req["id"], "PAUSED", expected={"PREFLIGHT"}, error=str(exc))
                self.store.transition(req["id"], "NEEDS_REVIEW", expected={"SENDING"}, error=str(exc))
            except Exception:  # Preserve uncertain submission instead of retrying.
                LOGGER.exception("ChatGPT submission failed for request %s", req["id"])
                self.store.transition(req["id"], "PAUSED", expected={"PREFLIGHT"},
                                      error="PREFLIGHT_FAILED")
                self.store.transition(req["id"], "NEEDS_REVIEW", expected={"SENDING"},
                                      error="SUBMISSION_UNCERTAIN")
        for req in self.store.runnable():
            try:
                with self.store.connect() as db:
                    self.store.require_run(db, req["agent"], req["run_id"])
                limit = 3600 if req["mode"] == "deep_research" else 600
                if time.time() - req["updated"] > limit:
                    raise BrowserBlocked("OBSERVATION_TIMEOUT")
                page = self.browser.page_for(req, req["url"])
                if (not req["url"] and "/c/" in page.url
                        and self.remember_thread_if_canonical(req, page.url)):
                    req["url"] = page.url
                result = self.browser.observe(accounts[req["account"]], req)
                if result:
                    self.store.transition(req["id"], "AWAITING_INPUT" if result["needs_input"]
                                          else "COMPLETED", expected={"RUNNING"}, result=result)
            except PermissionError:
                self.browser.stop(req["id"])
                self.store.transition(req["id"], "CANCELLED", expected={"RUNNING"},
                                      error="Originating UuMA run is no longer active.")
            except BrowserBlocked as exc:
                self.store.transition(req["id"], "PAUSED", expected={"RUNNING"}, error=str(exc))
            except Exception:  # noqa: BLE001 - browser DOM drift requires human review
                self.store.transition(req["id"], "NEEDS_REVIEW", expected={"RUNNING"},
                                      error="BROWSER_OBSERVATION_FAILED")
        self.last_tick = time.time()

    def run(self):
        self.store.recover()
        try:
            while not self.stop_event.is_set():
                try:
                    self.tick()
                    self.last_error = None
                except Exception as exc:
                    LOGGER.exception("ChatGPT bridge runner tick failed")
                    self.last_error = type(exc).__name__
                self.stop_event.wait(2)
        finally:
            self.browser.close()
