from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_track_first_fieldkg import create_hierarchy

from rstv4.approval import capture_user_approval
from rstv4.catalog_web import create_app
from rstv4.database import transaction
from rstv4.experiment_workspace import ExperimentWorkspace
from rstv4.models import DecisionProposalInput
from rstv4.track_first import TrackFirstService


@pytest.fixture
def fixture(tmp_path):
    service = TrackFirstService(tmp_path)
    _, _, track, project = create_hierarchy(service)
    proposal = service.propose_decision(
        track["track_id"],
        DecisionProposalInput(
            kind="method", statement="Software execution contract", rationale="Isolated fixture"
        ),
    )
    capture_user_approval(
        tmp_path,
        profile="scholar",
        session_id="software-fixture",
        message_id="method",
        user_message=proposal["approval_phrase"],
    )
    method = service.approve_decision(proposal["proposal_id"], 1)
    work = tmp_path / "projects" / project["slug"]
    work.mkdir(parents=True)
    script = work / "script.py"
    script.write_text(
        "import json, os\nfrom pathlib import Path\n"
        "p=Path('count.txt')\np.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
        "print('full output '+ 'x'*2200)\n"
        "Path('metrics.json').write_text(json.dumps({'value':int(Path('input.txt').read_text()),'env':os.environ.get('SELECTED_ENV')}))\n",
        encoding="utf-8",
    )
    (work / "input.txt").write_text("7", encoding="utf-8")
    selected = {
        "project_id": project["project_id"],
        "plan": {
            "method_node_id": method["node_id"],
            "argv": [sys.executable, "script.py"],
            "script_path": "script.py",
            "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "metrics_json_path": "metrics.json",
            "timeout_seconds": 5,
        },
        "input_files": ["input.txt"],
        "artifact_paths": ["count.txt"],
        "environment": {"SELECTED_ENV": "reviewed"},
    }
    app = create_app(tmp_path)
    with TestClient(app) as client:
        yield client, service, track, project, method, work, selected


def context(client, track):
    r = client.get(f"/api/catalog/tracks/{track['track_id']}/experiments")
    assert r.status_code == 200, r.text
    return r.json()


def action(client, track, operation, **kwargs):
    return {
        "operation": operation,
        "request_id": "request-" + uuid4().hex,
        "track_id": track["track_id"],
        "confirmed": True,
        "expected_context_sha256": context(client, track)["context_sha256"],
        **kwargs,
    }


def post(client, body, status=200):
    result = client.post("/api/catalog/experiment-actions", json=body)
    assert result.status_code == status, result.text
    return result.json()


def propose(fixture):
    client, _, track, _, _, _, selected = fixture
    response = client.post(
        f"/api/catalog/tracks/{track['track_id']}/experiment-manifest", json=selected
    )
    assert response.status_code == 200, response.text
    body = action(
        client,
        track,
        "PROPOSE_PLAN",
        **selected,
        expected_manifest_sha256=response.json()["manifest_sha256"],
    )
    result = post(client, body)
    return result["object_id"], body, result


def approve(fixture, plan_id):
    client, service, track, *_ = fixture
    plan = next(p for p in context(client, track)["plans"] if p["plan_id"] == plan_id)
    capture_user_approval(
        service.root,
        profile="scholar",
        session_id="software-fixture",
        message_id=uuid4().hex,
        user_message=plan["approval_phrase"],
    )
    return post(client, action(client, track, "APPLY_PLAN", plan_id=plan_id, expected_revision=1))


def test_manifest_approval_real_execution_exact_retry_and_result_evidence(fixture, monkeypatch):
    client, _, track, project, _, work, _ = fixture
    monkeypatch.setenv("AMBIENT_SECRET_SENTINEL", "never-store-this-value")
    before = context(client, track)
    plan_id, proposal_request, original = propose(fixture)
    assert post(client, proposal_request) == original
    assert original["manifest"]["inputs"][0]["sha256"] == hashlib.sha256(b"7").hexdigest()
    post(client, action(client, track, "APPLY_PLAN", plan_id=plan_id, expected_revision=1), 403)
    assert context(client, track)["science"]["nodes"] == before["science"]["nodes"]
    approve(fixture, plan_id)
    body = action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1)
    result = post(client, body)
    assert result["run"]["status"] == "COMPLETED"
    assert result["run"]["project_id"] == project["project_id"]
    assert result["run"]["detail"]["metrics"] == {"value": 7, "env": "reviewed"}
    assert len(result["run"]["detail"]["stdout"]) > 2200
    assert "never-store-this-value" not in json.dumps(result)
    assert result["run"]["detail"]["environment"]["explicit_environment"] == {
        "SELECTED_ENV": "reviewed"
    }
    retry = post(client, body)
    assert retry["object_id"] == result["object_id"] and (work / "count.txt").read_text() == "1"
    post(client, action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1), 409)
    evidence_body = action(
        client,
        track,
        "RECORD_RESULT",
        run_id=result["object_id"],
        statement="Observed software result",
        metric_key="value",
    )
    evidence = post(client, evidence_body)
    assert post(client, evidence_body) == evidence
    assert len(context(client, track)["science"]["evidence"]) == 1
    assert not any(n["node_type"] == "claim" for n in context(client, track)["science"]["nodes"])


@pytest.mark.parametrize("change", ["input", "script", "method", "upstream"])
def test_reviewed_plan_rejects_changed_files_or_recursive_method(fixture, change):
    client, service, track, _, method, work, _ = fixture
    if change == "upstream":
        upstream = service.propose_decision(
            track["track_id"],
            DecisionProposalInput(
                kind="hypothesis", statement="Software upstream", rationale="Fixture"
            ),
        )
        capture_user_approval(
            service.root,
            profile="scholar",
            session_id="fixture",
            message_id="upstream",
            user_message=upstream["approval_phrase"],
        )
        upstream = service.approve_decision(upstream["proposal_id"], 1)
        with transaction(service.db_path) as conn:
            conn.execute(
                "INSERT INTO research_edges VALUES(?,?,?,?,?,?)",
                (
                    "edge-fixture",
                    track["track_id"],
                    upstream["node_id"],
                    method["node_id"],
                    "DEPENDS_ON",
                    "fixture",
                ),
            )
    plan_id, _, _ = propose(fixture)
    approve(fixture, plan_id)
    if change in {"input", "script"}:
        (work / ("input.txt" if change == "input" else "script.py")).write_text("changed")
    else:
        with transaction(service.db_path) as conn:
            conn.execute(
                "UPDATE research_nodes SET status='STALE' WHERE node_id=?",
                ((upstream if change == "upstream" else method)["node_id"],),
            )
    post(client, action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1), 409)
    assert not (work / "count.txt").exists()
    assert not context(client, track)["runs"]


def test_preview_to_save_file_change_and_wrong_owner_are_atomic(fixture):
    client, _, track, _, _, work, selected = fixture
    preview = client.post(
        f"/api/catalog/tracks/{track['track_id']}/experiment-manifest", json=selected
    ).json()
    (work / "input.txt").write_text("8")
    body = action(
        client,
        track,
        "PROPOSE_PLAN",
        **selected,
        expected_manifest_sha256=preview["manifest_sha256"],
    )
    post(client, body, 409)
    selected["project_id"] = "wrong-project"
    assert (
        client.post(
            f"/api/catalog/tracks/{track['track_id']}/experiment-manifest", json=selected
        ).status_code
        == 404
    )
    assert not context(client, track)["plans"]


def test_manifest_escape_and_origin_are_rejected(fixture):
    client, _, track, _, _, _, selected = fixture
    selected["input_files"] = ["../escape.txt"]
    assert (
        client.post(
            f"/api/catalog/tracks/{track['track_id']}/experiment-manifest", json=selected
        ).status_code
        == 409
    )
    body = action(client, track, "START_PLAN", plan_id="unused", expected_revision=1)
    assert (
        client.post(
            "/api/catalog/experiment-actions", json=body, headers={"origin": "http://evil.test"}
        ).status_code
        == 403
    )


def test_concurrent_retries_and_midrun_source_invalidation(fixture, monkeypatch):
    client, service, track, _, method, work, _ = fixture
    plan_id, _, _ = propose(fixture)
    approve(fixture, plan_id)
    from rstv4.experiment import ExperimentRunner

    original = ExperimentRunner.run_script
    entered, release = threading.Event(), threading.Event()

    def wait_then_run(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(ExperimentRunner, "run_script", wait_then_run)
    body = action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1)
    responses = []
    thread = threading.Thread(target=lambda: responses.append(post(client, body)))
    thread.start()
    assert entered.wait(5)
    retry = post(client, body)
    assert retry["run"]["status"] == "RUNNING"
    with transaction(service.db_path) as conn:
        conn.execute(
            "UPDATE research_nodes SET status='STALE' WHERE node_id=?", (method["node_id"],)
        )
    release.set()
    thread.join(10)
    assert not thread.is_alive() and responses[0]["run"]["status"] == "SOURCE_INVALIDATED"
    assert (work / "count.txt").read_text() == "1"
    post(
        client,
        action(client, track, "RECORD_RESULT", run_id=retry["object_id"], statement="Invalid"),
        409,
    )


def test_result_artifact_change_blocks_evidence_and_stale_request(fixture):
    client, _, track, _, _, work, _ = fixture
    plan_id, body, _ = propose(fixture)
    altered = {**body, "project_id": None}
    post(client, altered, 409)
    approve(fixture, plan_id)
    result = post(client, action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1))
    (work / "metrics.json").write_text('{"value":999}')
    post(
        client,
        action(
            client, track, "RECORD_RESULT", run_id=result["object_id"], statement="Changed artifact"
        ),
        409,
    )


def test_project_metadata_preserved_and_read_context_does_not_mutate_database(fixture):
    client, service, track, *_ = fixture
    payload = {
        "track_id": track["track_id"],
        "slug": "second-project",
        "title": "Second",
        "type_payload": {
            "requirements": {},
            "system_design": {},
            "implementation": {},
            "validation": {},
            "goals": "Goal",
            "location": "Site",
            "data_description": "Data",
            "time": "2026-10",
        },
    }
    body = action(client, track, "CREATE_PROJECT", project=payload)
    result = post(client, body)
    assert post(client, body) == result
    project = service.get_project(result["object_id"])
    assert project["type_payload"] == payload["type_payload"]
    before = service.db_path.read_bytes()
    workspace = ExperimentWorkspace(service.db_path)
    workspace.context(track["track_id"])
    assert service.db_path.read_bytes() == before


def test_lost_execution_response_reconciles_reserved_run_without_rerunning(fixture, monkeypatch):
    from rstv4.experiment import ExperimentRunner

    client, _, track, _, _, work, _ = fixture
    plan_id, _, _ = propose(fixture)
    approve(fixture, plan_id)
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(kwargs["prepared_run_id"])
        raise RuntimeError("Worker response disappeared after reservation")

    monkeypatch.setattr(ExperimentRunner, "run_script", interrupted)
    body = action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1)
    with pytest.raises(RuntimeError, match="Worker response disappeared"):
        post(client, body)
    recovered = post(client, body)
    assert recovered["object_id"] == calls[0] and recovered["run"]["status"] == "RUNNING"
    assert len(calls) == 1 and not (work / "count.txt").exists()
    post(client, action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1), 409)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows executable search contract")
def test_selected_path_executes_reviewed_python_environment(fixture):
    client, _, track, _, _, work, selected = fixture
    script = work / "script.py"
    script.write_text(
        "import json,sys\nfrom pathlib import Path\nPath('metrics.json').write_text(json.dumps({'executable':sys.executable,'prefix':sys.prefix}))\nPath('count.txt').write_text('1')\n"
    )
    selected["plan"]["script_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    selected["plan"]["argv"] = ["python", "script.py"]
    selected["environment"] = {"PATH": str(Path(sys.executable).parent)}
    plan_id, _, original = propose(fixture)
    assert Path(original["manifest"]["executable"]["path"]) == Path(sys.executable).resolve()
    approve(fixture, plan_id)
    result = post(client, action(client, track, "START_PLAN", plan_id=plan_id, expected_revision=1))
    assert result["run"]["status"] == "COMPLETED"
    assert (
        Path(result["run"]["detail"]["metrics"]["executable"]).resolve()
        == Path(sys.executable).resolve()
    )
    observer = result['run']['detail']['environment']
    assert observer['observer_python_version'] == sys.version
    assert observer['observer_executable'] == sys.executable
    assert 'python_version' not in observer
