from __future__ import annotations

import email.utils
import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser


class UnsafeUrlError(ValueError):
    pass


class RetryAfterError(RuntimeError):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(frozen=True)
class FetchedResource:
    body: bytes
    final_url: str
    content_type: str
    headers: dict[str, str]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SafeWebFetcher:
    """Bounded public-web fetcher with redirect SSRF checks and robots/rate controls."""

    REDIRECT_CODES: ClassVar[set[int]] = {301, 302, 303, 307, 308}

    def __init__(
        self,
        *,
        user_agent: str = "UuMA-Wisdom-Oldman/0.1 (+local knowledge research)",
        timeout: float = 30,
        maximum_bytes: int = 20 * 1024 * 1024,
        minimum_host_interval: float = 1.0,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        opener=None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.maximum_bytes = maximum_bytes
        self.minimum_host_interval = max(0.0, minimum_host_interval)
        self.resolver = resolver
        self.opener = opener or build_opener(_NoRedirect())
        self._host_access: dict[str, float] = {}
        self._host_lock = threading.Lock()
        self._robots: dict[str, RobotFileParser | None] = {}

    def validate_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeUrlError("Only public http/https URLs can be fetched.")
        if parsed.username or parsed.password:
            raise UnsafeUrlError("Credentials in source URLs are not allowed.")
        try:
            addresses = {item[4][0] for item in self.resolver(parsed.hostname, None)}
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"Cannot resolve web source host: {parsed.hostname}") from exc
        if not addresses:
            raise UnsafeUrlError(f"Cannot resolve web source host: {parsed.hostname}")
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise UnsafeUrlError(
                    "Private, loopback, link-local, and reserved URLs are blocked."
                )

    def fetch(
        self,
        url: str,
        *,
        accept: str = "text/html,application/pdf,text/plain,application/xhtml+xml",
        allowed_content_types: set[str] | None = None,
        check_robots: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> FetchedResource:
        if check_robots and not self._robots_allows(url):
            raise PermissionError(f"robots.txt disallows automated retrieval of {url}")
        headers = {"User-Agent": self.user_agent, "Accept": accept} | (extra_headers or {})
        current = url
        for _ in range(6):
            self.validate_public_url(current)
            self._rate_limit(urlparse(current).hostname or "")
            request = Request(current, headers=headers)
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                if exc.code in self.REDIRECT_CODES:
                    location = exc.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect response omitted its Location header.") from exc
                    current = urljoin(current, location)
                    continue
                if exc.code in {429, 503}:
                    retry_after = self._retry_after_seconds(exc.headers.get("Retry-After"))
                    raise RetryAfterError(
                        f"Remote host requested a retry after HTTP {exc.code}.", retry_after
                    ) from exc
                raise
            except URLError:
                raise
            with response:
                final_url = response.geturl()
                self.validate_public_url(final_url)
                content_type = response.headers.get_content_type().lower()
                length = response.headers.get("Content-Length")
                if length and int(length) > self.maximum_bytes:
                    raise ValueError("Web source exceeds the configured download limit.")
                if allowed_content_types and content_type not in allowed_content_types:
                    raise ValueError(f"Unsupported web source content type: {content_type}")
                body = response.read(self.maximum_bytes + 1)
                if len(body) > self.maximum_bytes:
                    raise ValueError("Web source exceeds the configured download limit.")
                return FetchedResource(
                    body=body,
                    final_url=final_url,
                    content_type=content_type,
                    headers={key: value for key, value in response.headers.items()},
                )
        raise ValueError("Web source exceeded the five-redirect limit.")

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            try:
                fetched = self.fetch(
                    robots_url,
                    accept="text/plain,*/*;q=0.1",
                    allowed_content_types={"text/plain"},
                    check_robots=False,
                )
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(fetched.body.decode("utf-8", errors="replace").splitlines())
                self._robots[origin] = parser
            except (HTTPError, URLError, RetryAfterError, ValueError):
                self._robots[origin] = None
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def _rate_limit(self, hostname: str) -> None:
        if not hostname or self.minimum_host_interval <= 0:
            return
        with self._host_lock:
            now = time.monotonic()
            wait = self.minimum_host_interval - (now - self._host_access.get(hostname, 0.0))
            if wait > 0:
                time.sleep(wait)
            self._host_access[hostname] = time.monotonic()

    @staticmethod
    def _retry_after_seconds(value: str | None) -> int:
        if not value:
            return 60
        try:
            return max(1, int(value))
        except ValueError:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed is None:
                return 60
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(1, int((parsed - datetime.now(UTC)).total_seconds()))
