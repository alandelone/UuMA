import json

import pytest

from uuma.librarian_daily_cli import execute


def _config(tmp_path):
    status = tmp_path / "status"
    status.mkdir()
    config = {"schema_version": 1, "queue": str(tmp_path / "queue"), "device": "pc1",
              "source": "codex-state", "database": str(tmp_path / "source"),
              "public_key": str(tmp_path / "public"), "host": "example",
              "ssh_identity": str(tmp_path / "ssh"), "status_directory": str(status)}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path, status


def test_cli_records_intake_status_without_claiming_nas(tmp_path, monkeypatch):
    path, status = _config(tmp_path)
    result = {"coverage": "COMPLETE", "server_intake": "DELIVERED", "nas_publication": "NOT_CHECKED",
              "older_pending_before_retry": 0, "older_batches_delivered": 0}
    monkeypatch.setattr("uuma.librarian_daily_cli.run_daily_sqlite", lambda **kwargs: result)
    actual, code = execute(path)
    assert code == 0 and actual == result
    receipts = list(status.glob("run-*.json"))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text()) == result


def test_partial_or_backlog_does_not_report_success(tmp_path, monkeypatch):
    path, status = _config(tmp_path)
    result = {"coverage": "PARTIAL", "server_intake": "DELIVERED", "nas_publication": "NOT_CHECKED",
              "older_pending_before_retry": 1, "older_batches_delivered": 0}
    monkeypatch.setattr("uuma.librarian_daily_cli.run_daily_sqlite", lambda **kwargs: result)
    assert execute(path)[1] == 2
    assert len(list(status.glob("run-*.json"))) == 1


def test_invalid_config_cannot_create_a_status_receipt(tmp_path):
    path, status = _config(tmp_path)
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Duplicate"):
        execute(path)
    assert list(status.iterdir()) == []
