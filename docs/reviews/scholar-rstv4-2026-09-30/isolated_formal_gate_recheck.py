"""Recheck G-11 gates using real services and HTTP in a fresh isolated directory.

Run with RSTV4's Python environment. No production data, model calls or scientific
approvals are used. Approval messages below belong solely to test fixtures.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput,
    ExperimentPlanInput,
    FieldInput,
    TrackFirstManuscriptInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
)
from rstv4.service import RevisionConflictError
from rstv4.studio import StudioService
from rstv4.track_first import TrackFirstService


def approval(service: TrackFirstService, proposal: dict) -> None:
    assert capture_user_approval(
        service.root,
        profile="scholar",
        session_id="formal-gate-fixture-only",
        message_id=uuid4().hex,
        user_message=proposal["approval_phrase"],
    )


def decision(service: TrackFirstService, track_id: str, kind: str, **kwargs) -> dict:
    candidate = service.propose_decision(
        track_id,
        DecisionProposalInput(
            kind=kind,
            statement=f"Isolated {kind} {uuid4().hex}",
            rationale="Fixture approval only",
            **kwargs,
        ),
    )
    approval(service, candidate)
    return service.approve_decision(candidate["proposal_id"], 1)


def request(base: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def main() -> None:
    directory = Path(__file__).resolve().parent
    root = Path(tempfile.mkdtemp(prefix="scholar-formal-gates-"))
    service = TrackFirstService(root)
    field = service.create_field(FieldInput(name="Isolated field"))
    topic = service.create_topic(
        TrackFirstTopicInput(field_id=field["field_id"], name="Isolated topic")
    )
    track_id = service.create_track(
        TrackFirstTrackInput(
            field_id=field["field_id"],
            primary_topic_id=topic["topic_id"],
            title="Isolated track",
            research_type="conceptual_framework",
        )
    )["track_id"]
    method = decision(service, track_id, "method")
    claim = decision(service, track_id, "claim", upstream_node_ids=[method["node_id"]])
    indirect = decision(service, track_id, "claim", upstream_node_ids=[claim["node_id"]])
    manuscript = service.create_manuscript(
        TrackFirstManuscriptInput(
            track_id=track_id,
            title="Indirect fixture manuscript",
            node_ids=[indirect["node_id"]],
        )
    )
    marker = root / "old-method-must-not-run.txt"
    old_plan = service.propose_experiment_plan(
        track_id,
        ExperimentPlanInput(
            method_node_id=method["node_id"],
            argv=[sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
        ),
    )
    approval(service, old_plan)
    service.approve_experiment_plan(old_plan["plan_id"], 1)
    replacement = decision(service, track_id, "method", supersedes_node_id=method["node_id"])
    affected = service.impact_analysis(method["node_id"])
    assert len(affected) == 2 and all(row["status"] == "STALE" for row in affected)
    after = service.get_manuscript(manuscript["manuscript_id"])
    assert after["needs_scientific_review"] == 1
    assert after["nodes"] == manuscript["nodes"] and after["history"] == manuscript["history"]
    try:
        service.run_experiment(old_plan["plan_id"])
    except RevisionConflictError as exc:
        refusal = str(exc)
    else:
        raise AssertionError("Old method still executed")
    assert not marker.exists()
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 0
    new_plan = service.propose_experiment_plan(
        track_id,
        ExperimentPlanInput(
            method_node_id=replacement["node_id"],
            argv=[sys.executable, "-c", "print('ISOLATED_ACCEPTANCE_ONLY')"],
        ),
    )
    approval(service, new_plan)
    service.approve_experiment_plan(new_plan["plan_id"], 1)
    valid_run = service.run_experiment(new_plan["plan_id"])
    assert valid_run["exit_code"] == 0
    studio = StudioService(root)
    stage_cases = []
    for current, target in [
        ("DRAFTING", "WHOLE_PAPER_REVIEW"),
        ("WHOLE_PAPER_REVIEW", "FINALIZATION_SUBMISSION"),
        ("FINALIZATION_SUBMISSION", "REVISION"),
        ("FINALIZATION_SUBMISSION", "PUBLICATION"),
    ]:
        workspace = studio.create_manuscript(track_id, f"Zero versions {target}")
        manuscript_id = workspace["manuscript"]["manuscript_id"]
        with sqlite3.connect(service.db_path) as conn:
            conn.execute(
                "UPDATE manuscripts SET workflow_stage=? WHERE manuscript_id=?",
                (current, manuscript_id),
            )
        stage_cases.append((manuscript_id, current, target))
    studio._executor.shutdown(wait=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    code = (
        "import uvicorn; from rstv4.studio_api import create_app; "
        f"uvicorn.run(create_app({str(root)!r}), host='127.0.0.1', port={port}, log_level='warning')"
    )
    results = []
    with (root / "http-service.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    assert request(base, "/api/health")[0] == 200
                    break
                except (OSError, AssertionError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(
                            f"Isolated service failed; inspect {root / 'http-service.log'}"
                        )
                    time.sleep(0.1)
            for manuscript_id, current, target in stage_cases:
                _, before = request(base, f"/api/manuscripts/{manuscript_id}/workspace")
                status, response = request(
                    base,
                    f"/api/manuscripts/{manuscript_id}/stage",
                    {
                        "stage": target,
                        "expected_revision": before["manuscript"]["revision"],
                        "reason": "Isolated gate recheck",
                    },
                )
                assert status == 422 and "successful generated version" in response["detail"]
                _, restored = request(base, f"/api/manuscripts/{manuscript_id}/workspace")
                assert restored["workflow_stage"] == current
                assert restored["manuscript"]["revision"] == before["manuscript"]["revision"]
                assert restored["manuscript"]["history"] == before["manuscript"]["history"]
                results.append(
                    {
                        "from": current,
                        "requested": target,
                        "http_status": status,
                        "response": response,
                        "retained_stage": restored["workflow_stage"],
                    }
                )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    evidence = {
        "date": "2026-10-02",
        "isolated_root": str(root),
        "production_data_changed": False,
        "model_generation_exercised": False,
        "frontend_exercised": False,
        "upstream_supersession": {
            "dependants": affected,
            "needs_scientific_review": 1,
            "bindings_and_history_preserved": True,
        },
        "old_experiment": {"refused": True, "reason": refusal, "run_count_after_refusal": 0},
        "new_approved_experiment": valid_run,
        "real_http_stage_checks": results,
        "owned_http_service_stopped": process.poll() is not None,
    }
    target = directory / "formal-flow-gates-2026-10-02.json"
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(target), "http_cases": len(results), "passed": True}))


if __name__ == "__main__":
    main()
