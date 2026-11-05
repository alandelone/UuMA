"""Read Klipper printer.cfg snapshots into the existing Librarian recovery intake."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4
from zoneinfo import ZoneInfo

from .librarian_queue import IDENTITY, _key_fingerprint
from .librarian_server_daily import run_sources

MAX_CONFIG_BYTES = 2 * 1024 * 1024
CONFIG_PATH = "/server/files/config/printer.cfg"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download(url: str) -> bytes:
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path != CONFIG_PATH or parts.query or parts.fragment):
        raise ValueError("Expected an explicit HTTPS printer.cfg endpoint")
    request = Request(url, headers={"User-Agent": "UuMA-Librarian/1.0"})
    with build_opener(_NoRedirect()).open(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError("Printer configuration download did not succeed")
        raw = response.read(MAX_CONFIG_BYTES + 1)
        if "html" in response.headers.get("Content-Type", "").lower():
            raise ValueError("Printer returned an HTML page")
    if not raw or len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("Printer configuration exceeds the supported size")
    text = raw.decode("utf-8-sig")
    if "\x00" in text or not re.search(
        r"^\s*\[(?:printer|include [^\]\r\n]+)\]", text, re.MULTILINE,
    ):
        raise ValueError("Downloaded content lacks a Klipper configuration section")
    return raw


def _snapshot(root: Path, source: dict[str, str], day: str) -> Path:
    directory = root / source["source_id"]
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("Printer snapshot directory cannot be a symbolic link")
    target = directory / day
    if target.is_symlink():
        raise ValueError("Printer snapshot cannot be a symbolic link")
    if target.exists():
        for name in ("printer.cfg", "source.json"):
            if (target / name).is_symlink():
                raise ValueError("Printer snapshot file cannot be a symbolic link")
        metadata = json.loads((target / "source.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256((target / "printer.cfg").read_bytes()).hexdigest()
        if metadata["source_url"] != source["url"] or metadata["plaintext_sha256"] != digest:
            raise ValueError("Existing printer snapshot provenance differs")
        return target
    raw = _download(source["url"])
    metadata = {
        "source_id": source["source_id"], "source_url": source["url"],
        "filename": "printer.cfg", "fetched_at": datetime.now(UTC).isoformat(),
        "bytes": len(raw), "plaintext_sha256": hashlib.sha256(raw).hexdigest(),
    }
    with tempfile.TemporaryDirectory(prefix=".fetch-", dir=directory) as temporary:
        staged = Path(temporary) / day
        staged.mkdir(mode=0o700)
        for name, data in (("printer.cfg", raw),
                           ("source.json", json.dumps(metadata, indent=2).encode("utf-8"))):
            with (staged / name).open("xb") as stream:
                os.chmod(staged / name, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        staged.rename(target)
    return target


def run_weekly(config: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Capture each registered printer independently and retain per-date snapshots."""
    current = now or datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Printer capture time requires a timezone")
    sources = config["sources"]
    ids = [item["source_id"] for item in sources]
    if (not sources or len(sources) > 20 or len(ids) != len(set(ids))
            or any(not IDENTITY.fullmatch(value) for value in ids)):
        raise ValueError("Invalid or duplicate printer identities")
    public = Path(config["public_key"]).read_bytes()
    if _key_fingerprint(public) != config["public_fingerprint"]:
        raise ValueError("Printer recovery public key changed")
    root = Path(config["snapshot_root"])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Expected an absolute private printer snapshot root")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and (root.stat().st_uid != os.geteuid()
                              or root.stat().st_mode & 0o077):
        raise PermissionError("Printer snapshots must be private to their owner")
    day = current.astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
    staged = []
    failures = []
    for source in sources:
        try:
            path = _snapshot(root, source, day)
            staged.append({"source_id": source["source_id"], "kind": "tree", "path": str(path)})
        except (OSError, ValueError, KeyError) as error:
            failures.append({"source": source["source_id"], "status": "FETCH_FAILED",
                             "error_type": type(error).__name__})
    result = {"date": day, "sources": [], "incomplete": 0}
    if staged:
        # This runner owns the fetched snapshots and has verified their endpoint provenance.
        result = run_sources(
            staged, queue=Path(config["queue"]), intake=Path(config["intake"]),
            public_pem=public, now=current, verify_owner=lambda spec: spec in staged,
        )
    result["sources"].extend(failures)
    result["incomplete"] += len(failures)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "posix":
        raise SystemExit("The printer collector runs on the server")
    import fcntl

    path = args.config
    info = path.stat()
    if path.is_symlink() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise SystemExit("The collector configuration must be private and owner-controlled")
    config = json.loads(path.read_text(encoding="utf-8"))
    status = Path(config["status_directory"])
    if (status.is_symlink() or not status.is_dir() or status.stat().st_uid != os.geteuid()
            or status.stat().st_mode & 0o077):
        raise SystemExit("Expected a private status directory")
    with (status / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = run_weekly(config)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            result = {"incomplete": len(config["sources"]), "error_type": type(error).__name__}
        receipt = status / f"run-{uuid4().hex}.json"
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({"receipt": str(receipt), "incomplete": result["incomplete"]}))
    raise SystemExit(0 if result["incomplete"] == 0 else 2)


if __name__ == "__main__":
    main()
