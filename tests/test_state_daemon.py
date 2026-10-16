from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from uuma.state_daemon import StateDaemon, app


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_daemon = StateDaemon(data_dir=tmp_path)
    monkeypatch.setattr("uuma.state_daemon.daemon", test_daemon)
    return TestClient(app)


def test_state_daemon_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "uuma-state-daemon"


def test_state_daemon_bind_and_context(client):
    # Context initially empty
    res = client.get("/api/v1/context/alice")
    assert res.status_code == 200
    assert res.json()["active"] is False

    # Bind alice to project
    res = client.post("/api/v1/bind", json={"user_id": "alice", "project_id": "proj-farm", "topic_id": "topic-soil"})
    assert res.status_code == 200

    res = client.get("/api/v1/context/alice")
    assert res.status_code == 200
    data = res.json()
    assert data["active"] is True
    assert data["project_id"] == "proj-farm"
    assert data["topic_id"] == "topic-soil"


def test_state_daemon_commit_and_graph(client):
    # 1. Propose structural changes (topic and assumption)
    tx = {
        "project_id": "proj-farm",
        "operations": [
            {
                "action": "CREATE",
                "kind": "topic",
                "target_id": "topic-irrigation",
                "expected_revision": 0,
                "values": {"title": "Irrigation Plan"},
            },
            {
                "action": "CREATE",
                "kind": "assumption",
                "target_id": "asm-water",
                "expected_revision": 0,
                "values": {"title": "Water source is 1000L tank", "topic_id": "topic-irrigation"},
            },
        ],
        "rationale": "Initial irrigation planning.",
        "source_refs": ["live:turn-1"],
    }

    # Even with auto_approve=True, structural change MUST mandate review
    res = client.post(
        "/api/v1/commit",
        json={
            "user_id": "alice",
            "project_id": "proj-farm",
            "topic_id": "topic-irrigation",
            "source": "live",
            "transaction": tx,
            "auto_approve": True,
            "turn_text": "Let's plan irrigation assuming 1000L tank",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending_review"
    assert data["review_required"] is True
    assert data["revision"] is None
    proposal_id = data["proposal_id"]

    # Graph shows pending proposal
    res = client.get("/api/v1/graph/proj-farm")
    assert res.status_code == 200
    graph = res.json()
    assert len(graph["pending_proposals"]) == 1
    assert graph["pending_proposals"][0]["proposal_id"] == proposal_id

    # 2. Explicit review approval by user
    review_res = client.post(
        "/api/v1/review",
        json={
            "proposal_id": proposal_id,
            "project_id": "proj-farm",
            "topic_id": "topic-irrigation",
            "approve": True,
            "actor_id": "user",
            "note": "User confirmed irrigation topic and assumption",
        },
    )
    assert review_res.status_code == 200
    review_data = review_res.json()
    assert review_data["status"] == "committed"
    assert review_data["revision"] == 1

    # 3. Decision graph now reflects committed nodes
    res = client.get("/api/v1/graph/proj-farm")
    assert res.status_code == 200
    graph = res.json()
    assert graph["project_id"] == "proj-farm"
    assert graph["revision"] == 1
    assert len(graph["pending_proposals"]) == 0
    node_ids = [n["id"] for n in graph["nodes"]]
    assert "topic-irrigation" in node_ids
    assert "asm-water" in node_ids


def test_state_daemon_reject_proposal(client):
    tx = {
        "project_id": "proj-farm",
        "operations": [
            {
                "action": "CREATE",
                "kind": "topic",
                "target_id": "topic-rejected",
                "expected_revision": 0,
                "values": {"title": "Rejected Topic"},
            }
        ],
        "rationale": "Testing rejection.",
    }
    res = client.post(
        "/api/v1/commit",
        json={"user_id": "alice", "project_id": "proj-farm", "transaction": tx},
    )
    assert res.status_code == 200
    prop_id = res.json()["proposal_id"]

    review_res = client.post(
        "/api/v1/review",
        json={
            "proposal_id": prop_id,
            "project_id": "proj-farm",
            "approve": False,
            "actor_id": "user",
            "note": "Rejected by user",
        },
    )
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "rejected"

    # Confirm it's not in the graph nodes
    res = client.get("/api/v1/graph/proj-farm")
    assert res.status_code == 200
    node_ids = [n["id"] for n in res.json()["nodes"]]
    assert "topic-rejected" not in node_ids


def test_state_daemon_cycle_rejection(client):
    # Setup project with q1 and q2
    init_tx = {
        "project_id": "proj-cycle",
        "operations": [
            {
                "action": "CREATE",
                "kind": "project",
                "target_id": "proj-cycle",
                "expected_revision": 0,
                "values": {"title": "Cycle Test Project"},
            },
            {
                "action": "CREATE",
                "kind": "question",
                "target_id": "q1",
                "expected_revision": 0,
                "values": {"title": "Question 1"},
            },
            {
                "action": "CREATE",
                "kind": "question",
                "target_id": "q2",
                "expected_revision": 0,
                "values": {"title": "Question 2"},
            },
            {
                "action": "LINK",
                "kind": "question",
                "target_id": "q1",
                "values": {"source_id": "q1", "target_id": "q2", "relation": "subquestion"},
            },
        ],
        "rationale": "Setup Q1 -> Q2.",
    }
    res = client.post(
        "/api/v1/commit",
        json={"user_id": "alice", "project_id": "proj-cycle", "transaction": init_tx},
    )
    assert res.status_code == 200
    prop_id = res.json()["proposal_id"]
    client.post(
        "/api/v1/review",
        json={"proposal_id": prop_id, "project_id": "proj-cycle", "approve": True, "actor_id": "user"},
    )

    # Now attempt to commit reverse link (q2 -> q1) causing a cycle
    cycle_tx = {
        "project_id": "proj-cycle",
        "operations": [
            {
                "action": "LINK",
                "kind": "question",
                "target_id": "q2",
                "values": {"source_id": "q2", "target_id": "q1"},
            }
        ],
        "rationale": "Adversarial reverse link.",
    }
    res_cycle = client.post(
        "/api/v1/commit",
        json={"user_id": "alice", "project_id": "proj-cycle", "transaction": cycle_tx},
    )
    assert res_cycle.status_code == 400
    assert "Cycle detected" in res_cycle.json()["detail"]


def test_state_daemon_evidence_and_active_question(client):
    tx = {
        "project_id": "proj-evidence",
        "operations": [
            {
                "action": "CREATE",
                "kind": "project",
                "target_id": "proj-evidence",
                "expected_revision": 0,
                "values": {"title": "Evidence and Progression Project"},
            },
            {
                "action": "CREATE",
                "kind": "topic",
                "target_id": "topic-water",
                "expected_revision": 0,
                "values": {"title": "Water Analysis"},
            },
            {
                "action": "CREATE",
                "kind": "question",
                "target_id": "q-root",
                "expected_revision": 0,
                "values": {"title": "Is water sufficient?", "topic_id": "topic-water"},
            },
            {
                "action": "CREATE",
                "kind": "question",
                "target_id": "q-sub",
                "expected_revision": 0,
                "values": {"title": "What is well output?", "topic_id": "topic-water"},
            },
            {
                "action": "CREATE",
                "kind": "evidence",
                "target_id": "evi-pump",
                "expected_revision": 0,
                "values": {"title": "Pump flow rate reading", "source": "sensors", "topic_id": "topic-water"},
            },
            {
                "action": "LINK",
                "kind": "question",
                "target_id": "q-root",
                "values": {"source_id": "q-root", "target_id": "q-sub", "relation": "subquestion"},
            },
            {
                "action": "LINK",
                "kind": "evidence",
                "target_id": "evi-pump",
                "values": {"source_id": "evi-pump", "target_id": "q-sub", "relation": "grounds"},
            },
        ],
        "rationale": "Setup questions and evidence.",
    }
    res = client.post(
        "/api/v1/commit",
        json={"user_id": "alice", "project_id": "proj-evidence", "transaction": tx},
    )
    assert res.status_code == 200
    prop_id = res.json()["proposal_id"]
    client.post(
        "/api/v1/review",
        json={"proposal_id": prop_id, "project_id": "proj-evidence", "approve": True, "actor_id": "user"},
    )

    # 1. Verify graph response structure
    graph_res = client.get("/api/v1/graph/proj-evidence")
    assert graph_res.status_code == 200
    graph = graph_res.json()
    assert "hierarchy" in graph
    assert "progression" in graph

    evi_node = next(n for n in graph["nodes"] if n["id"] == "evi-pump")
    assert evi_node["kind"] == "evidence"

    # Verify edge categories
    edges = graph["edges"]
    sub_edge = next(e for e in edges if e["source"] == "q-root" and e["target"] == "q-sub")
    assert sub_edge["category"] == "hierarchy"

    grounds_edge = next(e for e in edges if e["source"] == "evi-pump" and e["target"] == "q-sub")
    assert grounds_edge["category"] == "dependency"

    # 2. Set and get active question
    act_res = client.post(
        "/api/v1/active-question",
        json={"project_id": "proj-evidence", "question_id": "q-sub", "user_id": "alice"},
    )
    assert act_res.status_code == 200
    assert act_res.json()["active_question_id"] == "q-sub"

    get_act = client.get("/api/v1/active-question/proj-evidence")
    assert get_act.status_code == 200
    assert get_act.json()["active_question_id"] == "q-sub"

