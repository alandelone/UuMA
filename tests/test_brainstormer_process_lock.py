from __future__ import annotations

import json
import multiprocessing
import os
import stat
from pathlib import Path

import pytest

from uuma import brainstormer_lock, brainstormer_state
from uuma.brainstormer_state import (
    BrainstormerStore,
    ObjectKind,
    RevisionConflict,
    StateOperation,
    StateTransaction,
    TransactionAction,
)


def _proposal(store, name):
    return store.propose(
        StateTransaction(
            project_id="shared", rationale="Concurrent bounded state update",
            operations=[StateOperation(
                action=TransactionAction.CREATE, kind=ObjectKind.QUESTION,
                target_id=name, expected_revision=0, values={"title": name},
            )],
        ),
        requested_by="brainstormer",
    )


def _write_questions(root, worker, start, output):
    store = BrainstormerStore(root, lock_timeout_seconds=10)
    assert start.wait(15)
    proposal_ids = []
    for index in range(4):
        proposal = _proposal(store, f"question-{worker}-{index}")
        store.commit_safe(proposal["proposal_id"], actor_id="brainstormer")
        proposal_ids.append(proposal["proposal_id"])
    output.put(proposal_ids)


def _review_once(root, proposal_id, start, output):
    store = BrainstormerStore(root, lock_timeout_seconds=10)
    assert start.wait(15)
    try:
        store.commit_safe(proposal_id, actor_id="brainstormer")
    except RevisionConflict:
        output.put("conflict")
    else:
        output.put("approved")


def _try_read_with_timeout(root, output):
    store = BrainstormerStore(root, lock_timeout_seconds=0.15)
    try:
        store.get_context("shared")
    except TimeoutError:
        output.put("timeout")
    else:
        output.put("read")


def _atomic_writer(root, worker, start):
    assert start.wait(15)
    for index in range(10):
        BrainstormerStore._atomic_json(
            Path(root) / "atomic.json", {"worker": worker, "index": index, "body": "x" * 10_000}
        )


def _join(processes):
    try:
        for process in processes:
            process.join(20)
        assert all(not process.is_alive() for process in processes), "Lock acquisition hung"
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)


def test_independent_process_writes_preserve_all_proposals_and_history(tmp_path):
    context = multiprocessing.get_context("spawn")
    start, output = context.Event(), context.Queue()
    processes = [context.Process(target=_write_questions, args=(str(tmp_path), i, start, output))
                 for i in range(4)]
    for process in processes:
        process.start()
    start.set()
    _join(processes)
    proposal_ids = [identifier for _ in processes for identifier in output.get(timeout=5)]
    state = json.loads((tmp_path / "projects/shared/state.json").read_text(encoding="utf-8"))
    assert len(state["objects"]) == 16
    assert state["revision"] == 16
    assert len(state["history"]) == 16
    assert [entry["revision"] for entry in state["history"]] == list(range(1, 17))
    assert {entry["proposal_id"] for entry in state["history"]} == set(proposal_ids)
    store = BrainstormerStore(tmp_path)
    assert len(list(store.proposals.glob("*.json"))) == 16
    assert all(store.get_proposal(identifier)["status"] == "APPROVED" for identifier in proposal_ids)
    assert not list(tmp_path.rglob("*.tmp"))


def test_same_proposal_can_only_be_committed_once_across_processes(tmp_path):
    store = BrainstormerStore(tmp_path)
    proposal = _proposal(store, "question-once")
    context = multiprocessing.get_context("spawn")
    start, output = context.Event(), context.Queue()
    processes = [context.Process(target=_review_once,
                                 args=(str(tmp_path), proposal["proposal_id"], start, output))
                 for _ in range(2)]
    for process in processes:
        process.start()
    start.set()
    _join(processes)
    assert sorted(output.get(timeout=5) for _ in processes) == ["approved", "conflict"]
    state = json.loads((tmp_path / "projects/shared/state.json").read_text(encoding="utf-8"))
    assert state["revision"] == 1
    assert len(state["history"]) == 1


def test_two_store_instances_share_reentrant_ownership_and_release_after_exception(tmp_path):
    first = BrainstormerStore(tmp_path, lock_timeout_seconds=0.2)
    second = BrainstormerStore(tmp_path / ".", lock_timeout_seconds=0.2)
    with pytest.raises(RuntimeError, match="leave transaction"), first._lock, second._lock:
        proposal = _proposal(second, "nested-question")
        first.commit_safe(proposal["proposal_id"], actor_id="brainstormer")
        raise RuntimeError("leave transaction")
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    reader = context.Process(target=_try_read_with_timeout, args=(str(tmp_path), output))
    reader.start()
    _join([reader])
    assert output.get(timeout=5) == "read"
    assert first._lock.lock_path.is_file()
    assert not first._lock.lock_path.is_relative_to(tmp_path)
    assert first.get_context("shared")["revision"] == 1


def test_other_process_times_out_while_original_process_owns_lock(tmp_path):
    store = BrainstormerStore(tmp_path)
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    with store._lock:
        reader = context.Process(target=_try_read_with_timeout, args=(str(tmp_path), output))
        reader.start()
        _join([reader])
        assert output.get(timeout=5) == "timeout"
        assert store._lock.lock_path.is_file()
    assert store.get_context("shared")["revision"] == 0


def test_atomic_writers_use_independent_temporary_files(tmp_path):
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [context.Process(target=_atomic_writer, args=(str(tmp_path), i, start))
                 for i in range(4)]
    for process in processes:
        process.start()
    start.set()
    _join(processes)
    result = json.loads((tmp_path / "atomic.json").read_text(encoding="utf-8"))
    assert result["worker"] in range(4)
    assert result["index"] == 9
    assert result["body"] == "x" * 10_000
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_replace_failure_keeps_original_and_cleans_unique_temp(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"original": true}', encoding="utf-8")
    original_replace = Path.replace

    def fail_replace(self, target):
        if self.suffix == ".tmp":
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        BrainstormerStore._atomic_json(path, {"new": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"original": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_temp_names_are_unique_and_in_destination_directory(tmp_path, monkeypatch):
    original = brainstormer_state.tempfile.NamedTemporaryFile
    created = []

    def record_temp(*args, **kwargs):
        handle = original(*args, **kwargs)
        created.append(Path(handle.name))
        return handle

    monkeypatch.setattr(brainstormer_state.tempfile, "NamedTemporaryFile", record_temp)
    destination = tmp_path / "state.json"
    BrainstormerStore._atomic_json(destination, {"revision": 1})
    BrainstormerStore._atomic_json(destination, {"revision": 2})
    assert len(created) == 2
    assert created[0] != created[1]
    assert all(path.parent == tmp_path for path in created)
    assert all(not path.exists() for path in created)


def test_windows_atomic_replace_retries_transient_sharing_failure(tmp_path, monkeypatch):
    destination = tmp_path / "state.json"
    destination.write_text('{"original": true}', encoding="utf-8")
    original_replace = Path.replace
    attempts, waits = [], []

    def sharing_failure_then_replace(self, target):
        attempts.append(self)
        if len(attempts) <= 2:
            error = PermissionError("Windows sharing conflict")
            error.winerror = 32
            raise error
        return original_replace(self, target)

    monkeypatch.setattr(brainstormer_state, "_WINDOWS_ATOMIC_REPLACE", True)
    monkeypatch.setattr(brainstormer_state.time, "sleep", waits.append)
    monkeypatch.setattr(Path, "replace", sharing_failure_then_replace)
    BrainstormerStore._atomic_json(destination, {"new": True})
    assert len(attempts) == 3
    assert len(set(attempts)) == 1
    assert waits == [0.01, 0.02]
    assert json.loads(destination.read_text(encoding="utf-8")) == {"new": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_windows_persistent_atomic_replace_failure_is_bounded(tmp_path, monkeypatch):
    destination = tmp_path / "state.json"
    destination.write_text('{"original": true}', encoding="utf-8")
    attempts, waits = [], []

    def persistent_access_failure(self, target):
        attempts.append(self)
        error = PermissionError("Windows access denied persists")
        error.winerror = 5
        raise error

    monkeypatch.setattr(brainstormer_state, "_WINDOWS_ATOMIC_REPLACE", True)
    monkeypatch.setattr(brainstormer_state.time, "sleep", waits.append)
    monkeypatch.setattr(Path, "replace", persistent_access_failure)
    with pytest.raises(PermissionError, match="access denied persists"):
        BrainstormerStore._atomic_json(destination, {"new": True})
    assert len(attempts) == 10
    assert len(waits) == 9
    assert sum(waits) <= 0.65
    assert json.loads(destination.read_text(encoding="utf-8")) == {"original": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_windows_atomic_replace_does_not_retry_unrelated_errors(tmp_path, monkeypatch):
    attempts = []

    def unrelated_failure(self, target):
        attempts.append(self)
        raise OSError("unrelated failure")

    monkeypatch.setattr(brainstormer_state, "_WINDOWS_ATOMIC_REPLACE", True)
    monkeypatch.setattr(Path, "replace", unrelated_failure)
    with pytest.raises(OSError, match="unrelated failure"):
        BrainstormerStore._atomic_json(tmp_path / "state.json", {"new": True})
    assert len(attempts) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_public_transaction_context_covers_nested_store_calls(tmp_path):
    first = BrainstormerStore(tmp_path, lock_timeout_seconds=0.2)
    second = BrainstormerStore(tmp_path, lock_timeout_seconds=0.2)
    with first.transaction() as transaction:
        assert transaction is first
        assert second.get_context("shared")["revision"] == 0
        proposal = _proposal(second, "question-context")
        first.commit_safe(proposal["proposal_id"], actor_id="brainstormer")
    assert second.get_context("shared")["revision"] == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and symlink creation")
def test_private_os_lock_metadata_has_strict_modes_and_leaves_domain_unchanged(tmp_path, monkeypatch):
    os_temp = tmp_path / "os-temp"
    os_temp.mkdir()
    monkeypatch.setattr(brainstormer_lock.tempfile, "gettempdir", lambda: str(os_temp))
    domain = tmp_path / "domain"
    store = BrainstormerStore(domain)
    before = sorted(path.relative_to(domain) for path in domain.rglob("*"))
    store.get_context("shared")
    assert sorted(path.relative_to(domain) for path in domain.rglob("*")) == before
    assert stat.S_IMODE(store._lock.lock_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store._lock.lock_path.stat().st_mode) == 0o600
    assert store._lock.lock_path == BrainstormerStore(domain / ".")._lock.lock_path


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and symlink creation")
def test_private_os_lock_rejects_symlink_file_and_directory(tmp_path, monkeypatch):
    os_temp = tmp_path / "os-temp"
    os_temp.mkdir()
    monkeypatch.setattr(brainstormer_lock.tempfile, "gettempdir", lambda: str(os_temp))
    store = BrainstormerStore(tmp_path / "domain")
    target = tmp_path / "untouched.txt"
    target.write_text("untouched", encoding="utf-8")
    store._lock.lock_path.symlink_to(target)
    with pytest.raises(PermissionError, match="links or reparse"):
        store.get_context("shared")
    assert target.read_text(encoding="utf-8") == "untouched"
    store._lock.lock_path.unlink()
    directory = store._lock.lock_path.parent
    directory.rmdir()
    target_dir = tmp_path / "target-dir"
    target_dir.mkdir(mode=0o700)
    directory.symlink_to(target_dir, target_is_directory=True)
    with pytest.raises(PermissionError, match="links or reparse"):
        BrainstormerStore(tmp_path / "another-domain")
    assert list(target_dir.iterdir()) == []
