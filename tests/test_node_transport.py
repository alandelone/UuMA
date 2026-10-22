import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from uuma.a2a_node import DispatchCoordinator, HermesAdapter
from uuma.desktop_connector import DesktopConnector, DesktopRequest
from uuma.migration import backup_database, database_inventory
from uuma.node_journal import NodeJournal


def test_wal_backup_is_a_standalone_database_and_leaves_source_unchanged(tmp_path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO records VALUES (1, 'preserved')")
        writer.commit()
        snapshot = tmp_path / "snapshot.db"
        backup_database(source, snapshot)
        with sqlite3.connect(snapshot) as captured:
            assert captured.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            assert captured.execute("SELECT value FROM records").fetchone()[0] == "preserved"
        assert not snapshot.with_name("snapshot.db-wal").exists()
        assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert writer.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1


class Control:
    def __init__(self):
        self.status = "PENDING"
        self.epoch = 1

    def require_run(self, run_id):
        return {
            "task_id": "task",
            "agent_id": "brainstormer",
            "status": self.status,
            "source": "orchestrator",
            "execution_epoch": self.epoch,
        }

    def require_task(self, task_id):
        return {
            "assignee": "brainstormer",
            "current_run_id": "run",
            "contract": {"objective": "Compare"},
        }


class Adapter:
    def __init__(self, *, fail=False):
        self.starts = 0
        self.fail = fail

    async def start(self, key, task):
        self.starts += 1
        if self.fail:
            raise TimeoutError("acceptance response lost")
        return "runtime-1"

    async def get(self, reference):
        return {"status": "running"}

    async def cancel(self, reference):
        return {"status": "stopping"}


def test_restart_reuses_dispatch_receipt(tmp_path):
    adapter, control = Adapter(), Control()
    path = tmp_path / "node.db"
    first = DispatchCoordinator(control, NodeJournal(path), {"brainstormer": adapter})
    asyncio.run(first.dispatch("brainstormer", "run", 1, "a2a-1"))
    second = DispatchCoordinator(control, NodeJournal(path), {"brainstormer": adapter})
    receipt = asyncio.run(second.dispatch("brainstormer", "run", 1, "a2a-2"))
    assert receipt["runtime_ref"] == "runtime-1"
    assert adapter.starts == 1


def test_lost_response_does_not_launch_again(tmp_path):
    adapter = Adapter(fail=True)
    coordinator = DispatchCoordinator(
        Control(), NodeJournal(tmp_path / "node.db"), {"brainstormer": adapter}
    )
    with pytest.raises(TimeoutError):
        asyncio.run(coordinator.dispatch("brainstormer", "run", 1, "a2a"))
    with pytest.raises(RuntimeError, match="reconcile"):
        asyncio.run(coordinator.dispatch("brainstormer", "run", 1, "a2a"))
    assert adapter.starts == 1


def test_paused_and_fenced_runs_cannot_dispatch(tmp_path):
    control = Control()
    adapter = Adapter()
    coordinator = DispatchCoordinator(
        control, NodeJournal(tmp_path / "node.db"), {"brainstormer": adapter}
    )
    control.status = "PAUSED"
    with pytest.raises(PermissionError):
        asyncio.run(coordinator.dispatch("brainstormer", "run", 1, "a2a"))
    control.status, control.epoch = "PENDING", 2
    with pytest.raises(PermissionError):
        asyncio.run(coordinator.dispatch("brainstormer", "run", 1, "a2a"))
    assert adapter.starts == 0


def test_hermes_uses_actual_input_and_idempotency_contract():
    class Client:
        def start(self, payload, *, idempotency_key):
            assert "input" in payload and "prompt" not in payload
            assert idempotency_key == "dispatch-key"
            assert payload["session_id"] == "uuma-assigned:task:run:1"
            return {"run_id": "receipt"}

    assert (
        asyncio.run(HermesAdapter(Client(), "brainstormer").start(
            "dispatch-key", {"task_id": "task", "run_id": "run", "epoch": 1}
        )) == "receipt"
    )


def test_desktop_side_effect_runs_once_and_checks_identity(tmp_path):
    calls = []

    def authorize(identity, request):
        if identity != "forge-lab-bot":
            raise PermissionError("wrong identity")

    connector = DesktopConnector(
        NodeJournal(tmp_path / "node.db"),
        authorize,
        {"lookup": lambda identity, payload: calls.append(payload) or {"ok": True}},
    )
    request = DesktopRequest.issue(
        request_id="request",
        run_id="run",
        execution_epoch=1,
        operation="lookup",
        payload={"item": "resistor"},
    )
    assert connector.execute("forge-lab-bot", request)["phase"] == "COMPLETED"
    assert connector.execute("forge-lab-bot", request)["phase"] == "COMPLETED"
    assert len(calls) == 1
    with pytest.raises(PermissionError):
        connector.execute("honc", request)
    with pytest.raises(ValueError, match="conflicts"):
        connector.execute(
            "forge-lab-bot", request.model_copy(update={"payload": {"item": "other"}})
        )


def test_expired_desktop_request_waits_for_confirmation(tmp_path):
    calls = []
    connector = DesktopConnector(
        NodeJournal(tmp_path / "node.db"), lambda *_: None, {"lookup": lambda *_: calls.append(1)}
    )
    now = datetime.now(UTC)
    request = DesktopRequest(
        request_id="old",
        run_id="run",
        execution_epoch=1,
        operation="lookup",
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=90),
    )
    assert connector.execute("forge-lab-bot", request)["phase"] == "EXPIRED"
    assert not calls


def test_desktop_interval_cannot_exceed_thirty_minutes(tmp_path):
    connector = DesktopConnector(
        NodeJournal(tmp_path / "node.db"), lambda *_: None, {"lookup": lambda *_: None}
    )
    request = DesktopRequest.issue(
        request_id="request", run_id="run", execution_epoch=1, operation="lookup"
    )
    request = request.model_copy(
        update={"expires_at": request.created_at + timedelta(minutes=30, microseconds=1)}
    )
    with pytest.raises(ValueError, match="validity interval"):
        connector.execute("forge-lab-bot", request)


def test_wal_database_snapshot_and_no_overwrite(tmp_path):
    source, target = tmp_path / "source.db", tmp_path / "backup.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO records VALUES (1,'paused task')")
        db.commit()
        receipt = backup_database(source, target)
    assert receipt["inventory"] == database_inventory(source)
    assert receipt["inventory"]["tables"]["records"]["rows"] == 1
    with pytest.raises(FileExistsError):
        backup_database(source, target)
