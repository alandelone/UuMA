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
