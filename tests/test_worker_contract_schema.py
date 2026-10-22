import asyncio
import json

import pytest
from pydantic import ValidationError

from uuma import mcp_worker
from uuma.models import ResultContract, RunProgress


def test_real_mcp_schema_exposes_strict_result_and_progress_contracts():
    tools = asyncio.run(mcp_worker.mcp.list_tools())
    schemas = {tool.name: tool.inputSchema for tool in tools}
    for name, argument, contract in (
        ("submit_result", "result_json", "ResultContract"),
        ("report_progress", "progress_json", "RunProgress"),
    ):
        schema = schemas[name]
        choices = schema["properties"][argument]["anyOf"]
        assert {"type": "string"} in choices  # Existing callers remain supported.
        assert {"$ref": f"#/$defs/{contract}"} in choices
        definition = schema["$defs"][contract]
        assert definition["additionalProperties"] is False
        assert {"run_id", "task_id", "agent_id"} <= set(definition["required"])
    assert "partial_state" in schemas["submit_result"]["$defs"]["ResultContract"]["properties"]


@pytest.mark.parametrize("legacy", [True, False])
def test_result_and_progress_keep_existing_validation(monkeypatch, legacy):
    calls = []

    class Control:
        def submit_result(self, result, *, actor_id):
            calls.append(("result", result, actor_id))
            return "RESULT_SUBMITTED"

        def report_progress(self, progress, *, actor_id):
            calls.append(("progress", progress, actor_id))

    monkeypatch.setattr(mcp_worker, "_control_plane", lambda: Control())
    monkeypatch.setattr(mcp_worker, "_agent_id", lambda: "brainstormer")
    result = ResultContract(run_id="run", task_id="task", agent_id="brainstormer",
                            outcome="COMPLETED", summary="Read snapshot",
                            partial_state={"project_id": "project", "object_count": 7})
    progress = RunProgress(run_id="run", task_id="task", agent_id="brainstormer",
                           status="RUNNING")
    result_arg = result.model_dump_json() if legacy else result
    progress_arg = progress.model_dump_json() if legacy else progress
    assert mcp_worker.submit_result(result_arg)["event_type"] == "RESULT_SUBMITTED"
    assert mcp_worker.report_progress(progress_arg)["status"] == "RUNNING"
    assert calls == [("result", result, "brainstormer"),
                     ("progress", progress, "brainstormer")]
    with pytest.raises(ValidationError):
        mcp_worker.submit_result(json.dumps({**result.model_dump(mode="json"), "output": {}}))
    assert len(calls) == 2  # A rejected envelope must not reach control.
