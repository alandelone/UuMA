import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_daily import run_daily_sqlite


@pytest.fixture(scope="module")
def public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_daily_retry_does_not_recapture_a_completed_batch(tmp_path, public, monkeypatch):
    database = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE records(value TEXT)")
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    monkeypatch.setattr("uuma.librarian_daily.deliver_queued_batch", lambda *a, **kw: {"sha256": "fixture"})
    kwargs = {"queue": tmp_path / "queue", "device": "pc1", "source": "codex-state",
              "database": database, "public_key": key, "host": "fixture", "ssh_identity": key,
              "now": datetime(2026, 10, 28, 16, 5, tzinfo=UTC)}
    first = run_daily_sqlite(**kwargs)
    capsules = {p: p.read_bytes() for p in (tmp_path / "queue").rglob("*.capsule")}
    with closing(sqlite3.connect(database)) as db:
        db.execute("INSERT INTO records VALUES ('later')")
        db.commit()
    second = run_daily_sqlite(**kwargs)
    assert first == second and first["batch_id"].endswith("2026-10-29")
    assert first["server_intake"] == "DELIVERED" and first["nas_publication"] == "NOT_CHECKED"
    assert capsules == {p: p.read_bytes() for p in (tmp_path / "queue").rglob("*.capsule")}


def test_offline_failure_is_pending_and_retry_preserves_batch(tmp_path, public, monkeypatch):
    database = tmp_path / "source.sqlite"
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    monkeypatch.setattr("uuma.librarian_daily.deliver_queued_batch", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    kwargs = {"queue": tmp_path / "queue", "device": "pc1", "source": "codex-state",
              "database": database, "public_key": key, "host": "fixture", "ssh_identity": key,
              "now": datetime(2026, 10, 29, 0, 0, tzinfo=UTC)}
    first = run_daily_sqlite(**kwargs)
    assert first["coverage"] == "PARTIAL" and first["server_intake"] == "PENDING"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE records(value TEXT)")
    second = run_daily_sqlite(**kwargs)
    assert second["batch_id"] == first["batch_id"] and second["revision"] == 2
    assert second["coverage"] == "COMPLETE" and second["server_intake"] == "PENDING"


def test_missed_day_and_older_pending_batch_are_visible(tmp_path, public, monkeypatch):
    database = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE records(value TEXT)")
    key = tmp_path / "public.pem"
    key.write_bytes(public)
    calls = []

    def offline(*args, **kwargs):
        calls.append(args[1])
        raise OSError("offline fixture")

    monkeypatch.setattr("uuma.librarian_daily.deliver_queued_batch", offline)
    kwargs = {"queue": tmp_path / "queue", "device": "pc1", "source": "codex-state",
              "database": database, "public_key": key, "host": "fixture", "ssh_identity": key}
    run_daily_sqlite(**kwargs, now=datetime(2026, 10, 26, 0, 0, tzinfo=UTC))
    result = run_daily_sqlite(**kwargs, now=datetime(2026, 10, 28, 0, 0, tzinfo=UTC))
    assert result["missed_dates_count"] == 1 and result["missed_dates_sample"] == ["2026-10-27"]
    assert result["older_pending_before_retry"] == 1 and result["older_batches_delivered"] == 0
    assert calls[-1].endswith("2026-10-26")
