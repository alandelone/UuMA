import hashlib
import sqlite3

import pytest

from uuma.librarian_snapshot import snapshot_sqlite


def test_snapshot_deadline_never_publishes(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE records (value TEXT)")
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr("uuma.librarian_snapshot.time.monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        snapshot_sqlite(source, tmp_path / "copy.db", timeout_seconds=1)
    assert not (tmp_path / "copy.db").exists()
    assert not list(tmp_path.glob(".librarian-snapshot-*"))


def test_snapshot_includes_committed_wal_and_keeps_source(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records (value TEXT)")
        db.execute("INSERT INTO records VALUES (?)", ("original",))
        db.commit()
        destination = tmp_path / "copy.db"
        receipt = snapshot_sqlite(source, destination)
        with sqlite3.connect(destination) as copy:
            assert copy.execute("SELECT value FROM records").fetchall() == [("original",)]
        assert receipt["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
        assert receipt["quick_check"] == "ok"
        assert db.execute("SELECT value FROM records").fetchall() == [("original",)]


def test_existing_destination_and_missing_source_are_never_overwritten(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE records (value TEXT)")
    destination = tmp_path / "copy.db"
    destination.write_bytes(b"retain")
    with pytest.raises(FileExistsError):
        snapshot_sqlite(source, destination)
    assert destination.read_bytes() == b"retain"
    with pytest.raises(FileNotFoundError):
        snapshot_sqlite(tmp_path / "missing.db", tmp_path / "new.db")
    assert not (tmp_path / "new.db").exists()


def test_invalid_database_is_not_published(tmp_path):
    source = tmp_path / "bad.db"
    source.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        snapshot_sqlite(source, tmp_path / "snapshot.db")
    assert not (tmp_path / "snapshot.db").exists()
    assert not list(tmp_path.glob(".librarian-snapshot-*"))
