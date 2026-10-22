"""Exercise the real Graph API and UuMA ledger on disposable databases."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from uuma.models import AgentDefinition, ResultContract, RunRegistration, VerificationDecision
from uuma.service import ConflictError, ControlPlane, PolicyDeniedError
from uuma.settings import Settings
from uuma.yonc_assignments import YoncAssignmentBridge


@pytest.fixture
def services(tmp_path, monkeypatch):
    graph_root = Path(__file__).resolve().parents[2] / "yonc_agent"
    if not (graph_root / "graph_app").is_dir():
        pytest.skip("The optional Yonc backend checkout is required for this integration contract")
    pytest.importorskip("sqlalchemy")
    sys.path.insert(0, str(graph_root))
    from fastapi.testclient import TestClient
    from graph_app.api import create_app

    monkeypatch.setenv("YONC_USER_REVIEW_TOKEN", "human-test")
    monkeypatch.setenv("YONC_ORCHESTRATOR_TOKEN", "control-test")
    monkeypatch.setenv("YONC_AGENT_COMMIT_TOKEN", "planner-test")
    monkeypatch.setattr("graph_app.frontend_builder.build_frontend", lambda **_: True)
    monkeypatch.setattr("graph_app.frontend_builder.start_frontend_watcher", lambda: None)
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "uuma.db",
        artifact_dir=tmp_path / "artifacts",
        ingest_spool_dir=tmp_path / "spool",
        hermes_executable=tmp_path / "unused-hermes.exe",
    )
    control = ControlPlane(settings)
    control.register_agent(
        AgentDefinition(
            agent_id="worker",
            display_name="Worker",
            description="Fixture worker",
            capabilities={"write_report"},
        ),
        actor_id="system",
    )
    with TestClient(create_app(tmp_path / "graph.db")) as graph:

        class Client:
            def request(self, path, payload=None):
                response = graph.request(
                    "POST" if payload is not None else "GET",
                    path,
                    json=payload,
                    headers={"Authorization": "Bearer control-test"},
                )
                assert response.status_code < 300, response.text
                return response.json()

        yield graph, control, YoncAssignmentBridge(control, Client())
    sys.path.remove(str(graph_root))


def allocation(graph):
    action = graph.post(
        "/api/v2/nodes",
        json={
            "title": "Write result report",
            "work_type": "ACTION",
            "done_when": "User accepts the report",
        },
    ).json()["node"]
    item = graph.post(
        f"/api/v2/nodes/{action['id']}/assignments",
        json={
            "operation_id": str(uuid4()),
            "expected_graph_version": graph.get("/api/v2/health").json()["graph_version"],
            "executor_id": "worker",
            "task_contract": {
                "objective": "Write the report",
                "required_capabilities": ["write_report"],
                "input_refs": ["docs://another-person/data"],
            },
        },
        headers={"Authorization": "Bearer planner-test"},
    ).json()["assignment"]
    response = graph.post(
        f"/api/v2/assignments/{item['id']}/approve",
        json={
            "operation_id": str(uuid4()),
            "expected_revision": item["revision"],
            "expected_graph_version": graph.get("/api/v2/health").json()["graph_version"],
        },
        headers={"Authorization": "Bearer human-test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["assignment"]


def test_real_handoff_delivery_and_user_acceptance_are_linked_and_retryable(services):
    graph, control, bridge = services
    item = allocation(graph)
    prepared = bridge.prepare(item["id"])
    assert prepared["execution_started"] is False
    assert bridge.prepare(item["id"])["task_id"] == prepared["task_id"]
    task_id = prepared["task_id"]
    task = control.require_task(task_id)
    assert task["contract"]["acceptance_authority"] == "USER"
    assert task["contract"]["external_task_ref"].endswith("/nodes/" + item["node_id"])
    registration = control.register_run(
        RunRegistration(
            task_id=task_id,
            agent_id="worker",
            execution_class="BACKGROUND",
            source="orchestrator",
        ),
        actor_id="orchestrator",
    )
    control.submit_result(
        ResultContract(
            task_id=task_id,
            run_id=registration.run_id,
            agent_id="worker",
            outcome="COMPLETED",
            summary="Report delivered",
            artifact_refs=["docs://report/v1"],
            structured_rationale=["Compared the supplied original data"],
        ),
        actor_id="worker",
    )
    context = control.verification_context(registration.run_id)
    with pytest.raises(PolicyDeniedError, match="actual user"):
        control.verify_result(
            VerificationDecision(
                task_id=task_id,
                run_id=registration.run_id,
                approved=True,
                acceptance_digest=context["acceptance_digest"],
                result_digest=context["result_digest"],
            ),
            actor_id="orchestrator",
        )
    detail = bridge.sync(item["id"])
    assert detail["assignment"]["state"] == "AWAITING_USER_REVIEW"
    assert len(bridge.sync(item["id"])["deliveries"]) == 1
    assert control.require_run(registration.run_id)["status"] == "REVIEW"
    assert graph.get(f"/api/v2/nodes/{item['node_id']}").json()["status"] != "DONE"
    delivered = detail["deliveries"][0]
    accepted = graph.post(
        f"/api/v2/assignments/{item['id']}/reviews",
        json={
            "operation_id": str(uuid4()),
            "expected_revision": detail["assignment"]["revision"],
            "expected_graph_version": detail["graph_version"],
            "delivery_id": delivered["id"],
            "result_digest": delivered["result_digest"],
            "decision": "accept",
            "note": "I reviewed and accept the delivered report",
        },
        headers={"Authorization": "Bearer human-test"},
    )
    assert accepted.status_code == 200, accepted.text
    bridge.sync(item["id"])
    bridge.sync(item["id"])
    assert control.require_run(registration.run_id)["status"] == "COMPLETED"
    verifications = control.verification_context(registration.run_id)["verifications"]
    assert len(verifications) == 1 and verifications[0]["verifier_id"] == "user"
    assert graph.get(f"/api/v2/nodes/{item['node_id']}").json()["status"] == "DONE"


def test_unqualified_executor_is_never_silently_replaced(services):
    graph, control, bridge = services
    item = allocation(graph)
    control.register_agent(
        AgentDefinition(
            agent_id="worker",
            display_name="Disabled worker",
            description="No longer available",
            capabilities={"write_report"},
            enabled=False,
        ),
        actor_id="system",
    )
    with pytest.raises(PolicyDeniedError):
        bridge.prepare(item["id"])
    current = graph.get(f"/api/v2/assignments/{item['id']}").json()["assignment"]
    assert current["state"] == "QUEUED" and current["uuma_task_id"] is None
    assert control.list_runs() == []


@pytest.mark.parametrize("response_was_lost", [False, True])
def test_interrupted_binding_reuses_the_original_task_without_starting_execution(
    services, monkeypatch, response_was_lost
):
    graph, control, bridge = services
    item = allocation(graph)
    original = bridge.client.request
    pending_failure = True

    def interrupted(path, payload=None):
        nonlocal pending_failure
        if path.endswith("/binding") and pending_failure:
            pending_failure = False
            if response_was_lost:
                original(path, payload)
            raise TimeoutError("Simulated handoff interruption")
        return original(path, payload)

    monkeypatch.setattr(bridge.client, "request", interrupted)
    with pytest.raises(TimeoutError):
        bridge.prepare(item["id"])
    prepared = bridge.prepare(item["id"])
    creations = [event for event in control.events.iter_events() if event.event_type == "TASK_CREATED"]
    assert len(creations) == 1
    assert prepared["task_id"] == creations[0].aggregate_id
    assert prepared["assignment"]["state"] == "ASSIGNED"
    assert prepared["execution_started"] is False
    assert control.list_runs() == []


def cancel(graph, assignment_id):
    detail = graph.get(f"/api/v2/assignments/{assignment_id}").json()
    response = graph.post(
        f"/api/v2/assignments/{assignment_id}/cancel",
        json={
            "operation_id": str(uuid4()),
            "expected_revision": detail["assignment"]["revision"],
            "expected_graph_version": detail["graph_version"],
            "note": "User cancels this work",
        },
        headers={"Authorization": "Bearer human-test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["assignment"]


def test_cancelled_unstarted_allocation_cannot_register_a_late_run(services):
    graph, control, bridge = services
    item = allocation(graph)
    prepared = bridge.prepare(item["id"])
    assert cancel(graph, item["id"])["state"] == "CANCEL_REQUESTED"
    detail = bridge.sync(item["id"])
    assert detail["assignment"]["state"] == "CANCELLED"
    assert control.require_task(prepared["task_id"])["status"] == "CANCELLED"
    with pytest.raises(ConflictError):
        control.register_run(
            RunRegistration(
                task_id=prepared["task_id"],
                agent_id="worker",
                execution_class="BACKGROUND",
                source="orchestrator",
            ),
            actor_id="orchestrator",
        )
    control.events.rebuild_projections()
    assert control.require_task(prepared["task_id"])["status"] == "CANCELLED"


def test_running_cancellation_keeps_allocation_reserved_until_worker_stops(services):
    graph, control, bridge = services
    item = allocation(graph)
    prepared = bridge.prepare(item["id"])
    run = control.register_run(
        RunRegistration(
            task_id=prepared["task_id"],
            agent_id="worker",
            execution_class="BACKGROUND",
            source="orchestrator",
        ),
        actor_id="orchestrator",
    )
    bridge.sync(item["id"])
    with pytest.raises(ConflictError):
        bridge.prepare(item["id"])
    cancel(graph, item["id"])
    pending = bridge.sync(item["id"])
    assert pending["assignment"]["state"] == "CANCEL_REQUESTED"
    assert control.require_run(run.run_id)["status"] == "CANCEL_REQUESTED"
    control.submit_result(
        ResultContract(
            task_id=prepared["task_id"],
            run_id=run.run_id,
            agent_id="worker",
            outcome="CANCELLED",
            summary="Stopped after cancellation",
        ),
        actor_id="worker",
    )
    assert bridge.sync(item["id"])["assignment"]["state"] == "CANCELLED"
