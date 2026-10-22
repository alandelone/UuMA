"""A migrated journal runner uses its explicit owner and native Hermes executable."""

from uuma import forge_journal_runner as module


def build(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "load_notion_connection", lambda _path: {})
    monkeypatch.setattr(module, "NotionJournalClient", lambda _headers: object())
    return module.build_runner(
        tmp_path / "profile", tmp_path / "gateway", tmp_path / "data", "logs", "candidates"
    )


def test_explicit_ledger_and_hermes_paths_are_used(tmp_path, monkeypatch):
    ledger = tmp_path / "production" / "forge" / "lab.db"
    executable = tmp_path / "runtime" / "bin" / "hermes"
    monkeypatch.setenv("LAB_DATABASE_PATH", str(ledger))
    monkeypatch.setenv("UUMA_HERMES_EXECUTABLE", str(executable))

    runner = build(tmp_path, monkeypatch)

    assert runner.store.database_path == ledger
    assert runner.dispatcher.hermes_executable == executable
    assert not (tmp_path / "data" / "forge-lab-bot" / "lab.db").exists()


def test_existing_default_paths_are_preserved(tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_DATABASE_PATH", raising=False)
    monkeypatch.delenv("UUMA_HERMES_EXECUTABLE", raising=False)

    runner = build(tmp_path, monkeypatch)

    assert runner.store.database_path == tmp_path / "data" / "forge-lab-bot" / "lab.db"
    assert runner.dispatcher.hermes_executable == (
        tmp_path / "gateway" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
    )


def test_empty_overrides_preserve_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATABASE_PATH", "")
    monkeypatch.setenv("UUMA_HERMES_EXECUTABLE", "")

    runner = build(tmp_path, monkeypatch)

    assert runner.store.database_path == tmp_path / "data" / "forge-lab-bot" / "lab.db"
    assert runner.dispatcher.hermes_executable.name == "hermes.exe"
