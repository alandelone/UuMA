import json
import sqlite3
import subprocess
import sys

import pytest

from uuma.session import Session


@pytest.fixture
def session(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text(".uuma-local/\n")
    instance = Session(tmp_path)
    yield instance
    instance.db.close()


def test_close_requires_current_handoff(session):
    session.start()
    with pytest.raises(ValueError):
        session.close()
    session.handoff("Implemented", "None observed", "Review")
    (session.root / "new.txt").write_text("change")
    with pytest.raises(ValueError):
        session.close()
    session.handoff("Updated", "None observed", "Review")
    session.close()
    session.start()


def test_failure_is_logged_and_invalidates_handoff(session):
    session.start()
    session.handoff("Ready", "None", "Review")
    assert session.run([sys.executable, "-c", "raise SystemExit(7)"]) == 7
    with pytest.raises(ValueError):
        session.close()
    assert '"exit_code": 7' in (session.root / "active-session/progress.md").read_text()


def test_unfinished_session_and_modified_handoff(session):
    session.start()
    with pytest.raises(ValueError):
        session.start()
    with pytest.raises(ValueError):
        session.handoff("", "None", "Review")
    session.handoff("Ready", "None", "Review")
    (session.root / "active-session/HANDOFF.md").write_text("forged")
    with pytest.raises(ValueError):
        session.check()


def test_deleted_file_and_spawn_failure(session):
    path = session.root / "tracked.txt"
    path.write_text("content")
    session.start()
    session.handoff("Ready", "None", "Review")
    path.unlink()
    with pytest.raises(ValueError):
        session.check()
    with pytest.raises(FileNotFoundError):
        session.run(["nonexistent-uuma-test-executable"])
    assert session.events()[-1][2] == "command_interrupted"


def test_cli_fails_closed(session):
    session.start()
    result = subprocess.run(
        [sys.executable, "-m", "uuma.session", "--root", str(session.root), "close"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "handoff" in result.stderr


def test_handoff_history_and_command_secret_not_persisted(session):
    session.start()
    session.handoff("First version", "None", "Review")
    session.run([sys.executable, "-c", "pass # token=do-not-store"])
    session.handoff("Second version", "None", "Review again")
    journal = str(session.events())
    assert "First version" in journal and "Second version" in journal
    assert "do-not-store" not in journal
    session.close()


def test_internal_lifecycle_checks_do_not_materialize_entire_history(session, monkeypatch):
    session.start()
    session.handoff("Original retained context", "None", "Continue")
    before = session.db.execute("SELECT id,payload FROM repo_session_events ORDER BY id").fetchall()

    def history_unavailable():
        raise MemoryError("Whole history does not fit in memory")

    monkeypatch.setattr(session, "events", history_unavailable)
    session.progress()
    assert session.run([sys.executable, "-c", "pass"]) == 0
    session.handoff("Current preserved context", "None", "Review")
    session.check()
    session.close()
    session.start()
    assert session.db.execute("SELECT id,payload FROM repo_session_events WHERE id<=? ORDER BY id",
                              (before[-1][0],)).fetchall() == before
    text = (session.root / "active-session/progress.md").read_text()
    assert '"content"' not in text and "closed" in text and "command_finished" in text


def test_progress_preserves_full_projection_without_sqlite_json_parsing(session):
    session.start()
    path = session.root / "active-session/progress.md"
    marker = "\n<!-- automatic-session-journal -->\n"
    # The marker crosses the prefix reader's chunk boundary, including non-ASCII text.
    prefix = "作者记录\n" + "p" * 65520
    path.write_text(prefix + marker + "old projection\n", encoding="utf-8")
    payloads = [
        {"content": "retained large context " * 50000, "snapshot": {"a": "sha", "b": "sha"},
         "exit_code": 0, "changed": ["file.txt"], "other": {"content": "nested retained"}},
        *({"snapshot": value} for value in [[], {}, None, "scalar", 7]),
        {"executable": "python.exe", "files_observed": 99},
    ]
    session.db.executemany(
        "INSERT INTO repo_session_events(time,kind,payload) VALUES (?,?,?)",
        [("fixture time", "fixture", json.dumps(payload)) for payload in payloads],
    )
    session.db.commit()
    before = session.events()
    # Capture the established projection contract on this isolated database, including
    # JSON scalars/null, before denying JSON functions to the production projection.
    expected = []
    for seq, time, kind, raw, count in session.db.execute(
        "SELECT id,time,kind,json_remove(payload,'$.content','$.snapshot'), "
        "CASE WHEN json_type(payload,'$.snapshot') IS NOT NULL THEN "
        "(SELECT COUNT(*) FROM json_each(payload,'$.snapshot')) ELSE NULL END "
        "FROM repo_session_events ORDER BY id"
    ):
        payload = json.loads(raw)
        if count is not None:
            payload["files_observed"] = count
        expected.append(f"- {time} #{seq} {kind}: {json.dumps(payload)}")

    def no_json_functions(action, name, function, database, trigger):
        if action == sqlite3.SQLITE_FUNCTION and str(function).startswith("json"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    session.db.set_authorizer(no_json_functions)
    try:
        session.progress()
    finally:
        session.db.set_authorizer(None)
    assert path.read_text(encoding="utf-8") == prefix + marker + "\n".join(expected) + "\n"
    assert session.events() == before
    assert "retained large context" not in path.read_text(encoding="utf-8")


def test_failed_progress_keeps_previous_projection_and_full_journal(session, monkeypatch):
    session.start()
    session.append("fixture", retained="projection failure target")
    path = session.root / "active-session/progress.md"
    before_file = path.read_bytes()
    before_journal = session.events()
    original_loads = json.loads

    def limited_decode(raw):
        if "projection failure target" in raw:
            raise MemoryError("controlled projection allocation failure")
        return original_loads(raw)

    monkeypatch.setattr("uuma.session.json.loads", limited_decode)
    with pytest.raises(MemoryError, match="controlled projection"):
        session.progress()
    assert path.read_bytes() == before_file
    assert session.events() == before_journal
    assert not list(path.parent.glob(".progress.md.*.tmp"))
