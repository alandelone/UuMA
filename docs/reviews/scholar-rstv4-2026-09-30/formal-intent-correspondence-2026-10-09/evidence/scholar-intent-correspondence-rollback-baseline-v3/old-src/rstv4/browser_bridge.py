"""Loopback handoff between Network workers and one authorized Chrome profile.

The extension receives only browser acquisition requests. Downloaded bytes return through
Chrome's Downloads folder and are adopted through the existing PDF receipt gate.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .acquisition import AcquisitionService
from .database import transaction
from .models import BrowserAcquisitionReceiptInput

MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_REQUEST_BYTES = 32 * 1024
EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")
PUBLISHER_DOWNLOAD_HOSTS = {
    "ieeexplore.ieee.org", "www.sciencedirect.com", "reader.elsevier.com",
    "ars.els-cdn.com", "pdf.sciencedirectassets.com", "www.mdpi.com", "mdpi-res.com",
}


def _safe_source_url(raw: str | None) -> str | None:
    """Keep publisher provenance without storing signed URLs or browser credentials."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme != "https" or parsed.hostname not in PUBLISHER_DOWNLOAD_HOSTS
                or parsed.username or parsed.password):
            return None
    except ValueError:
        return None
    query = ""
    if parsed.hostname == "ieeexplore.ieee.org" and parsed.path.endswith("/getPDF.jsp"):
        article_number = parse_qs(parsed.query).get("arnumber", [""])[0]
        if article_number.isdecimal() and len(article_number) <= 12:
            query = f"arnumber={article_number}"
    safe = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    return safe if len(safe) <= 4000 else None


def _bridge_token(root: Path) -> str:
    path = root / ".rstv4-local" / "browser-bridge" / "token"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(32))
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("Browser bridge pairing token is invalid")
    return token


class BrowserBridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, service: AcquisitionService, *, port: int = 8876,
        download_root: Path | None = None,
    ) -> None:
        self.service = service
        self.token = _bridge_token(service.root)
        configured_download_root = os.environ.get("RSTV4_CHROME_DOWNLOAD_ROOT")
        resolved_download_root = download_root or (
            Path(configured_download_root) if configured_download_root else Path.home() / "Downloads"
        )
        self.download_root = resolved_download_root.resolve()
        super().__init__(("127.0.0.1", port), BrowserBridgeHandler)

    def adopt_download(
        self, request_id: str, execution_id: str, filename: str,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        with transaction(self.service.db_path) as conn:
            request = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        if request is None or request["execution_id"] != execution_id:
            raise ValueError("Unknown or stale browser execution")
        if request["status"] != "RUNNING":
            raise ValueError("Browser request is not running")

        source = Path(filename).resolve(strict=True)
        expected = (self.download_root / "RSTV4" / request_id).resolve()
        if not expected.is_relative_to(self.download_root):
            raise PermissionError("Assigned Chrome folder escapes Downloads")
        if not source.is_file() or not source.is_relative_to(expected):
            raise PermissionError("Download is outside the assigned Chrome folder")
        if source.suffix.casefold() != ".pdf" or source.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("Download is not a PDF within the size limit")
        with source.open("rb") as stream:
            head = stream.read(1024)
            stream.seek(max(0, source.stat().st_size - 2048))
            tail = stream.read()
        if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise ValueError("Chrome download is not a complete PDF")

        sha256 = self.service._file_digest(source)
        target_dir = Path(request["target_directory"]).resolve()
        allowed = (self.service.import_root / "browser").resolve()
        if target_dir.parent != allowed:
            raise PermissionError("Browser request target is outside the import area")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"source-{sha256[:16]}.pdf"
        if target.exists():
            if self.service._file_digest(target) != sha256:
                raise ValueError("Existing staged PDF does not match this download")
        else:
            temporary = target_dir / f".{execution_id}.partial"
            shutil.copy2(source, temporary)
            if self.service._file_digest(temporary) != sha256:
                temporary.unlink(missing_ok=True)
                raise ValueError("Download changed while copying")
            os.replace(temporary, target)
        result = self.service.submit_browser_acquisition_receipt(
            BrowserAcquisitionReceiptInput(
                request_id=request_id, execution_id=execution_id,
                action_id="rstv4-chrome-extension", action_version="1",
                status="COMPLETED", output_paths=[str(target)],
                source_url=_safe_source_url(source_url),
            )
        )
        registered = result.get("registered_files", [])
        if len(registered) == 1:
            canonical = Path(registered[0]["storage_path"]).resolve()
            expected_canonical = (
                self.service.artifacts_root / request["paper_id"] / sha256 / "source.pdf"
            ).resolve()
            if (canonical == expected_canonical and canonical.is_file()
                    and self.service._file_digest(canonical) == sha256):
                # The Catalog copy is authoritative. Leave only it after a successful receipt.
                for transient in (source, target):
                    try:
                        transient.unlink(missing_ok=True)
                    except OSError:
                        pass
                for directory in (expected, target_dir):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
        return result

    def adopt_upload(
        self, request_id: str, execution_id: str, stream: Any, length: int,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        """Register a PDF the person selected after publisher browser verification."""
        if not 0 < length <= MAX_PDF_BYTES:
            raise ValueError("Uploaded PDF exceeds the size limit")
        with transaction(self.service.db_path) as conn:
            request = conn.execute(
                "SELECT * FROM browser_acquisition_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        if (request is None or request["execution_id"] != execution_id
                or request["status"] != "WAITING_HUMAN"):
            raise ValueError("No matching browser request is waiting for a PDF")
        target_dir = Path(request["target_directory"]).resolve()
        if target_dir.parent != (self.service.import_root / "browser").resolve():
            raise PermissionError("Browser request target is outside the import area")
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target_dir / f".{secrets.token_hex(8)}.upload.partial"
        try:
            remaining = length
            with temporary.open("xb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Uploaded PDF ended early")
                    output.write(chunk)
                    remaining -= len(chunk)
            with temporary.open("rb") as input_file:
                head = input_file.read(1024)
                input_file.seek(max(0, length - 2048))
                tail = input_file.read()
            if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
                raise ValueError("Selected file is not a complete PDF")
            sha256 = self.service._file_digest(temporary)
            target = target_dir / f"source-{sha256[:16]}.pdf"
            if target.exists():
                if self.service._file_digest(target) != sha256:
                    raise ValueError("Existing staged PDF does not match this upload")
            else:
                os.replace(temporary, target)
            result = self.service.submit_browser_acquisition_receipt(
                BrowserAcquisitionReceiptInput(
                    request_id=request_id, execution_id=execution_id,
                    action_id="rstv4-chrome-human-upload", action_version="1",
                    status="COMPLETED", output_paths=[str(target)],
                    source_url=_safe_source_url(source_url),
                )
            )
            registered = result.get("registered_files", [])
            if len(registered) == 1:
                canonical = Path(registered[0]["storage_path"]).resolve()
                expected = (
                    self.service.artifacts_root / request["paper_id"] / sha256 / "source.pdf"
                ).resolve()
                if (canonical == expected and canonical.is_file()
                        and self.service._file_digest(canonical) == sha256):
                    target.unlink(missing_ok=True)
                    try:
                        target_dir.rmdir()
                    except OSError:
                        pass
            return result
        finally:
            temporary.unlink(missing_ok=True)


class BrowserBridgeHandler(BaseHTTPRequestHandler):
    server: BrowserBridgeServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin and EXTENSION_ORIGIN.fullmatch(origin):
            return origin
        return None

    def _allowed(self, *, require_token: bool = True) -> bool:
        host = self.headers.get("Host", "")
        if host != f"127.0.0.1:{self.server.server_port}":
            return False
        origin = self.headers.get("Origin")
        if origin and not self._origin():
            return False
        return not require_token or hmac.compare_digest(
            self.headers.get("X-RSTV4-Bridge-Token", ""), self.server.token
        )

    def _json(self, status: int, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if origin := self._origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(encoded)

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("Invalid browser bridge request size")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise TypeError("Browser bridge request must be a JSON object")
        return value

    def do_OPTIONS(self) -> None:
        if not self._allowed(require_token=False) or not self._origin():
            self._json(403, {"error": "Forbidden"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._origin() or "")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-RSTV4-Bridge-Token, X-RSTV4-Request-ID, "
            "X-RSTV4-Execution-ID, X-RSTV4-Article-URL",
        )
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._allowed():
            self._json(403, {"error": "Forbidden"})
            return
        if self.path == "/api/v1/next":
            self._json(200, {"task": self.server.service.claim_browser_acquisition()})
        else:
            self._json(404, {"error": "Unknown endpoint"})

    def do_POST(self) -> None:
        if not self._allowed():
            self._json(403, {"error": "Forbidden"})
            return
        try:
            if self.path == "/api/v1/upload":
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/pdf":
                    raise ValueError("Upload must be a PDF")
                result = self.server.adopt_upload(
                    self.headers.get("X-RSTV4-Request-ID", ""),
                    self.headers.get("X-RSTV4-Execution-ID", ""),
                    self.rfile,
                    int(self.headers.get("Content-Length", "0")),
                    self.headers.get("X-RSTV4-Article-URL"),
                )
                self._json(200, {"result": result})
                return
            payload = self._payload()
            if self.path == "/api/v1/complete":
                result = self.server.adopt_download(
                    str(payload["request_id"]), str(payload["execution_id"]),
                    str(payload["filename"]), payload.get("source_url"),
                )
            elif self.path == "/api/v1/status":
                status = payload["status"]
                if status not in {"RUNNING", "WAITING_HUMAN", "FAILED", "ABORTED"}:
                    raise ValueError("Invalid browser status")
                result = self.server.service.submit_browser_acquisition_receipt(
                    BrowserAcquisitionReceiptInput(
                        request_id=payload["request_id"],
                        execution_id=payload["execution_id"],
                        action_id="rstv4-chrome-extension", action_version="1",
                        status=status, error=payload.get("error"),
                    )
                )
            elif self.path == "/api/v1/resume":
                result = self.server.service.resume_browser_acquisition(
                    str(payload["request_id"]), str(payload["execution_id"])
                )
            else:
                self._json(404, {"error": "Unknown endpoint"})
                return
        except (KeyError, TypeError, ValueError, PermissionError, OSError) as exc:
            self._json(422, {"error": str(exc)})
            return
        self._json(200, {"result": result})
