import asyncio

import pytest

from uuma.a2a_node import DispatchCoordinator, execution_projection
from uuma.node_journal import NodeJournal


@pytest.mark.parametrize(
    ("uuma", "runtime", "state", "accepted"),
    [
        ("REVIEW", "failed", "FAILED", False),
        ("REVIEW", "running", "INPUT_REQUIRED", False),
        ("REVIEW", "completed", "COMPLETED", False),
        ("COMPLETED", "failed", "FAILED", True),
        ("COMPLETED", "completed", "COMPLETED", True),
        ("RUNNING", "completed", "INPUT_REQUIRED", False),
        ("RUNNING", "cancelled", "INPUT_REQUIRED", False),
        ("RUNNING", "stopping", "WORKING", False),
        ("RUNNING", "unknown", "INPUT_REQUIRED", False),
        ("CANCELLED", "stopping", "CANCELED", False),
        ("BLOCKED", "running", "INPUT_REQUIRED", False),
    ],
)
def test_runtime_and_acceptance_are_independent(uuma, runtime, state, accepted):
    observation = {
        "uuma_status": uuma,
        "runtime_status": runtime,
        "accepted": uuma == "COMPLETED",
    }
    assert execution_projection(observation)[0] == state
    assert observation["accepted"] is accepted


def test_observation_preserves_receipt_and_never_launches_or_accepts(tmp_path):
    class Control:
        def require_run(self, run_id):
            assert run_id == "run"
            return {"status": "REVIEW", "execution_epoch": 3}

    class Adapter:
        runtime_status = "running"

        async def get(self, reference):
            assert reference == "native"
            return {"status": self.runtime_status, "output": "not for transport metadata"}

        async def start(self, *args):
            pytest.fail("Observation must never relaunch the submitted execution")

    journal = NodeJournal(tmp_path / "node.db")
    record = {
        "agent_id": "brainstormer",
        "run_id": "run",
        "execution_epoch": 3,
        "runtime_ref": "native",
        "revision": "fixed-release",
        "phase": "ACCEPTED",
    }
    key = "dispatch:brainstormer:run:3"
    journal.reserve(key, {}, record)
    adapter = Adapter()
    coordinator = DispatchCoordinator(Control(), journal, {"brainstormer": adapter})
    active = asyncio.run(coordinator.observe(record))
    assert execution_projection(active)[0] == "INPUT_REQUIRED"
    adapter.runtime_status = "failed"
    failed = asyncio.run(coordinator.observe(record))
    assert execution_projection(failed) == ("FAILED", "runtime_failed")
    assert failed["uuma_status"] == "REVIEW"
    assert failed["accepted"] is False
    assert failed["runtime_ref"] == "native"
    assert failed["revision"] == "fixed-release"
    assert "output" not in failed
    assert journal.get(key) == failed


def test_cancel_request_and_query_failure_do_not_prove_runtime_stopped(tmp_path):
    class Control:
        def require_run(self, run_id):
            return {"status": "RUNNING", "execution_epoch": 1}

    class Adapter:
        async def get(self, reference):
            raise TimeoutError("private transport detail")

    journal = NodeJournal(tmp_path / "node.db")
    record = {
        "agent_id": "brainstormer",
        "run_id": "run",
        "execution_epoch": 1,
        "runtime_ref": "native",
        "phase": "ACCEPTED",
    }
    key = "dispatch:brainstormer:run:1"
    journal.reserve(key, {}, record)
    journal.update(key, {**record, "phase": "CANCEL_REQUESTED"})
    coordinator = DispatchCoordinator(Control(), journal, {"brainstormer": Adapter()})
    observation = asyncio.run(coordinator.observe(record))
    assert observation["cancel_requested"] is True
    assert observation["runtime_status"] == "unknown"
    assert observation["runtime_reachable"] is False
    assert execution_projection(observation)[0] == "INPUT_REQUIRED"
    assert "private transport detail" not in str(observation)


def test_superseded_execution_cannot_publish_current_completion():
    record = {"uuma_status": "COMPLETED", "runtime_status": "completed", "superseded": True}
    assert execution_projection(record) == ("FAILED", "superseded_execution")


def test_lost_stop_response_retains_cancel_intent_and_execution_reference(tmp_path):
    class Adapter:
        async def cancel(self, reference):
            assert reference == "native"
            raise TimeoutError("stop acknowledgment lost")

    journal = NodeJournal(tmp_path / "node.db")
    record = {
        "agent_id": "brainstormer",
        "run_id": "run",
        "execution_epoch": 1,
        "runtime_ref": "native",
        "phase": "ACCEPTED",
    }
    key = "dispatch:brainstormer:run:1"
    journal.reserve(key, {}, record)
    journal.update(key, {**record, "uuma_status": "RUNNING", "runtime_status": "running"})
    coordinator = DispatchCoordinator(None, journal, {"brainstormer": Adapter()})
    with pytest.raises(TimeoutError):
        asyncio.run(coordinator.request_cancel(record))
    persisted = journal.get(key)
    assert persisted["phase"] == "CANCEL_REQUESTED"
    assert persisted["runtime_ref"] == "native"
    assert persisted["runtime_status"] == "running"
    assert persisted["uuma_status"] == "RUNNING"
