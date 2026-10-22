from __future__ import annotations

import json
import multiprocessing
import os
import time

from uuma.brainstormer_state import BrainstormerStore


def _propose_topic(root, ready, start, output):
    # Authenticate the fake caller without connecting to the production control API.
    os.environ["UUMA_DATA_DIR"] = root
    from uuma import mcp_worker

    class SlowCheckStore(BrainstormerStore):
        def find_pending_topic_proposal(self, project_id, topic_id):
            result = super().find_pending_topic_proposal(project_id, topic_id)
            if result is None:
                # Widen the check/create gap; the outer transaction must retain
                # ownership across it rather than locking only individual calls.
                time.sleep(0.1)
            return result

    store = SlowCheckStore(root, lock_timeout_seconds=10)
    mcp_worker._require_brainstormer = lambda: "brainstormer"
    mcp_worker._brainstormer_store = lambda: store
    ready.put(True)
    assert start.wait(15)
    result = mcp_worker.brainstormer_propose_project_topic(
        project_title="Shared Project", project_objective="Preserve the objective",
        topic_title="Shared Topic", topic_problem="Preserve the discussion",
        source_ref="conversation:concurrent-fixture",
    )
    output.put({key: result[key] for key in (
        "proposal_id", "status", "review_required", "requested_by"
    )})


def test_independent_mcp_processes_reuse_one_pending_topic_proposal(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, output, start = context.Queue(), context.Queue(), context.Event()
    processes = [context.Process(target=_propose_topic,
                                 args=(str(tmp_path), ready, start, output)) for _ in range(4)]
    try:
        for process in processes:
            process.start()
        assert all(ready.get(timeout=20) for _ in processes)
        start.set()
        for process in processes:
            process.join(20)
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        results = [output.get(timeout=5) for _ in processes]
        assert len({result["proposal_id"] for result in results}) == 1
        assert all(result["status"] == "PROPOSED" for result in results)
        assert all(result["review_required"] is True for result in results)
        assert all(result["requested_by"] == "brainstormer" for result in results)
        proposals = list((tmp_path / "proposals").glob("*.json"))
        assert len(proposals) == 1
        proposal = json.loads(proposals[0].read_text(encoding="utf-8"))
        assert proposal["transaction"]["source_refs"] == ["conversation:concurrent-fixture"]
        assert [operation["kind"] for operation in proposal["transaction"]["operations"]] == [
            "project", "topic"
        ]
        assert not list((tmp_path / "projects").glob("*/state.json"))
        assert not list(tmp_path.rglob("*.tmp"))
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
