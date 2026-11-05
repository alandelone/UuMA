import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma import librarian_printer_weekly as collector
from uuma.librarian_crypto import recover
from uuma.librarian_queue import _key_fingerprint


@pytest.fixture
def config(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    for name in ("queue", "intake"):
        (tmp_path / name).mkdir(mode=0o700)
    return {
        "public_key": str(key), "public_fingerprint": _key_fingerprint(public),
        "snapshot_root": str(tmp_path / "snapshots"), "queue": str(tmp_path / "queue"),
        "intake": str(tmp_path / "intake"),
        "sources": [{"source_id": "printer-a-config",
                     "url": "https://printer-a.example/server/files/config/printer.cfg"},
                    {"source_id": "printer-b-config",
                     "url": "https://printer-b.example/server/files/config/printer.cfg"}],
        "private": private,
    }


def test_download_rejects_login_page_oversize_and_wrong_endpoint(monkeypatch):
    class Response(BytesIO):
        status = 200

        def __init__(self, raw):
            super().__init__(raw)
            self.headers = {"Content-Type": "text/plain"}

    payload = b"<html>Login</html>"
    monkeypatch.setattr(collector, "build_opener", lambda *_: type(
        "Opener", (), {"open": lambda *a, **k: Response(payload)},
    )())
    url = "https://printer.example/server/files/config/printer.cfg"
    with pytest.raises(ValueError, match="Klipper"):
        collector._download(url)
    payload = b"[printer]\n" + b"x" * collector.MAX_CONFIG_BYTES
    with pytest.raises(ValueError, match="size"):
        collector._download(url)
    with pytest.raises(ValueError, match="endpoint"):
        collector._download("http://printer.example/server/files/config/printer.cfg")
    payload = b"# original\r\n[printer]\r\nkinematics: corexy\r\n"
    assert collector._download(url) == payload


def test_retry_preserves_snapshot_and_other_printer_progress(config, monkeypatch):
    def download(url):
        if "printer-b" in url:
            raise TimeoutError("fixture offline")
        return b"[printer]\nkinematics: corexy\n"

    monkeypatch.setattr(collector, "_download", download)

    def capture(specs, **kwargs):
        assert len(specs) == 1 and kwargs["verify_owner"](specs[0])
        return {"sources": [{"source": specs[0]["source_id"], "coverage": "COMPLETE"}],
                "incomplete": 0}

    monkeypatch.setattr(collector, "run_sources", capture)
    now = datetime(2026, 11, 5, tzinfo=UTC)
    result = collector.run_weekly(config, now=now)
    assert result["incomplete"] == 1
    assert result["sources"][-1]["status"] == "FETCH_FAILED"
    source = config["sources"][0]
    snapshot = collector._snapshot(collector.Path(config["snapshot_root"]), source, "2026-11-05")
    original = (snapshot / "printer.cfg").read_bytes()
    monkeypatch.setattr(collector, "_download", lambda _: b"changed remote file")
    assert collector._snapshot(snapshot.parent.parent, source, "2026-11-05") == snapshot
    assert (snapshot / "printer.cfg").read_bytes() == original
    (snapshot / "printer.cfg").write_bytes(b"tampered snapshot")
    with pytest.raises(ValueError, match="provenance"):
        collector._snapshot(snapshot.parent.parent, source, "2026-11-05")


@pytest.mark.skipif(os.name != "posix", reason="Server intake requires POSIX ownership")
def test_real_intake_history_and_recovery(config, monkeypatch):
    payload = b"# fixture\n[printer]\nkinematics: corexy\n"
    monkeypatch.setattr(collector, "_download", lambda _: payload)
    first = collector.run_weekly(config, now=datetime(2026, 11, 5, tzinfo=UTC))
    assert first["incomplete"] == 0
    assert all(item["server_intake"] == "DELIVERED" for item in first["sources"])
    monkeypatch.setattr(collector, "_download", lambda _: payload + b"max_velocity: 200\n")
    second = collector.run_weekly(config, now=datetime(2026, 11, 8, tzinfo=UTC))
    assert second["incomplete"] == 0
    intake = collector.Path(config["intake"])
    with closing(sqlite3.connect(intake / "recovery-intake.sqlite")) as db:
        rows = db.execute("SELECT raw FROM manifest_revisions ORDER BY batch_id").fetchall()
    assert len(rows) == 4
    first_manifest = next(json.loads(row[0]) for row in rows
                          if json.loads(row[0])["batch_id"] == first["sources"][0]["batch_id"])
    entry = next(e for e in first_manifest["entries"] if e["source_path"].endswith("printer.cfg"))
    capsule = intake / "server" / first_manifest["source"] / entry["sha256"]
    assert hashlib.sha256(capsule.read_bytes()).hexdigest() == entry["sha256"]
    password = b"fixture password"
    private = config["private"].private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    destination = intake.parent / "restored-printer.cfg"
    recover(capsule, destination, private, password)
    assert destination.read_bytes() == payload
