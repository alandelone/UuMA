from __future__ import annotations

import json

import pytest

from uuma.brainstormer_state import (
    BrainstormerError,
    BrainstormerStore,
    CycleDetectedError,
    ObjectKind,
    RelationCategory,
    RevisionConflict,
    StateOperation,
    StateTransaction,
    TransactionAction,
)


def transaction(project_id: str, *operations: StateOperation) -> StateTransaction:
    return StateTransaction(
        project_id=project_id,
        operations=list(operations),
        rationale="Preserve discussion state for re-entry.",
        source_refs=["conversation:test"],
    )


def test_structure_requires_review_and_restores_context(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    proposal = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.PROJECT,
                target_id="uuma",
                expected_revision=0,
                values={"title": "UuMA", "objective": "Build the agent system"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.TOPIC,
                target_id="topic-memory",
                expected_revision=0,
                values={"title": "Discussion memory", "problem": "How should it persist?"},
            ),
        ),
        requested_by="brainstormer",
    )
    assert proposal["review_required"] is True
    with pytest.raises(PermissionError):
        store.commit_safe(proposal["proposal_id"], actor_id="brainstormer")

    reviewed = store.review(
        proposal["proposal_id"], actor_id="orchestrator", approve=True, note="User approved"
    )
    assert reviewed["status"] == "APPROVED"
    context = store.get_context("uuma", "topic-memory")
    assert context["objects"][0]["title"] == "Discussion memory"
    assert store.search_topics("discussion memory")[0]["id"] == "topic-memory"


def test_safe_checkpoint_commit_and_stale_revision(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    checkpoint = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.CHECKPOINT,
                kind=ObjectKind.CHECKPOINT,
                target_id="checkpoint-1",
                values={"title": "Pause", "current_understanding": "State is explicit"},
            ),
        ),
        requested_by="brainstormer",
    )
    assert checkpoint["review_required"] is False
    store.commit_safe(checkpoint["proposal_id"], actor_id="brainstormer")

    update = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.UPDATE,
                kind=ObjectKind.CHECKPOINT,
                target_id="checkpoint-1",
                expected_revision=1,
                values={"current_understanding": "Updated"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.commit_safe(update["proposal_id"], actor_id="brainstormer")
    stale = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.UPDATE,
                kind=ObjectKind.CHECKPOINT,
                target_id="checkpoint-1",
                expected_revision=1,
                values={"current_understanding": "Stale"},
            ),
        ),
        requested_by="brainstormer",
    )
    with pytest.raises(RevisionConflict):
        store.commit_safe(stale["proposal_id"], actor_id="brainstormer")

    state = json.loads((tmp_path / "projects" / "uuma" / "state.json").read_text("utf-8"))
    assert len(state["history"]) == 2
    assert state["objects"]["checkpoint-1"]["current_understanding"] == "Updated"


def test_identifiers_and_existing_object_kind_cannot_bypass_review(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    with pytest.raises(BrainstormerError):
        store.get_context("../outside")
    with pytest.raises(BrainstormerError):
        store.get_proposal("../outside")

    create = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.DECISION,
                target_id="decision-1",
                values={"title": "Persistence authority", "choice": "structured JSON"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.review(create["proposal_id"], actor_id="orchestrator", approve=True, note="approved")

    spoofed = store.propose(
        transaction(
            "uuma",
            StateOperation(
                action=TransactionAction.UPDATE,
                kind=ObjectKind.ASSUMPTION,
                target_id="decision-1",
                expected_revision=1,
                values={"choice": "unreviewed overwrite"},
            ),
        ),
        requested_by="brainstormer",
    )
    assert spoofed["review_required"] is True
    with pytest.raises(PermissionError):
        store.commit_safe(spoofed["proposal_id"], actor_id="brainstormer")
    with pytest.raises(BrainstormerError, match="kind mismatch"):
        store.review(
            spoofed["proposal_id"],
            actor_id="orchestrator",
            approve=True,
            note="adversarial test",
        )


def test_evidence_creation_and_safe_commit(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    # Propose project & topic
    init_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.PROJECT,
                target_id="farm",
                expected_revision=0,
                values={"title": "Experimental Farm"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.TOPIC,
                target_id="topic-irrigation",
                expected_revision=0,
                values={"title": "Irrigation system"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.review(init_prop["proposal_id"], actor_id="orchestrator", approve=True, note="approved")

    # Propose evidence node (factual telemetry)
    evi_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.EVIDENCE,
                target_id="evi-water-log",
                expected_revision=0,
                values={
                    "title": "Water source telemetry log",
                    "source": "sensor:well-01",
                    "data": {"flow_rate_lpm": 45, "tested_at": "2026-10-14"},
                    "topic_id": "topic-irrigation",
                },
            ),
        ),
        requested_by="brainstormer",
    )
    # Factual evidence does not require structural review
    assert evi_prop["review_required"] is False
    store.commit_safe(evi_prop["proposal_id"], actor_id="brainstormer")

    context = store.get_context("farm", "topic-irrigation")
    evi_node = next(obj for obj in context["objects"] if obj["id"] == "evi-water-log")
    assert evi_node["kind"] == "evidence"
    assert evi_node["source"] == "sensor:well-01"


def test_dag_cycle_detection_and_prevention(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    # Setup project and 3 questions
    setup_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.PROJECT,
                target_id="farm",
                expected_revision=0,
                values={"title": "Farm"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                expected_revision=0,
                values={"title": "Main Question: Soil or Hydro?"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q2",
                expected_revision=0,
                values={"title": "Subquestion: Maintenance time?"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q3",
                expected_revision=0,
                values={"title": "Subquestion: Water capacity?"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.review(setup_prop["proposal_id"], actor_id="orchestrator", approve=True, note="approved")

    # 1. Self-referential link is rejected immediately
    with pytest.raises(CycleDetectedError, match="Self-referential"):
        store.propose(
            transaction(
                "farm",
                StateOperation(
                    action=TransactionAction.LINK,
                    kind=ObjectKind.QUESTION,
                    target_id="q1",
                    values={"source_id": "q1", "target_id": "q1"},
                ),
            ),
            requested_by="brainstormer",
        )

    # 2. Add legitimate links: q1 -> q2, q2 -> q3
    link_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                values={"source_id": "q1", "target_id": "q2", "relation": "subquestion"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q2",
                values={"source_id": "q2", "target_id": "q3", "relation": "subquestion"},
            ),
        ),
        requested_by="brainstormer",
    )
    assert link_prop["review_required"] is False
    store.commit_safe(link_prop["proposal_id"], actor_id="brainstormer")

    # 3. Direct reverse link (q2 -> q1) MUST be rejected by cycle detection
    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        store.propose(
            transaction(
                "farm",
                StateOperation(
                    action=TransactionAction.LINK,
                    kind=ObjectKind.QUESTION,
                    target_id="q2",
                    values={"source_id": "q2", "target_id": "q1"},
                ),
            ),
            requested_by="brainstormer",
        )

    # 4. Indirect cycle (q3 -> q1) MUST be rejected by cycle detection
    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        store.propose(
            transaction(
                "farm",
                StateOperation(
                    action=TransactionAction.LINK,
                    kind=ObjectKind.QUESTION,
                    target_id="q3",
                    values={"source_id": "q3", "target_id": "q1"},
                ),
            ),
            requested_by="brainstormer",
        )


def test_decision_map_question_hierarchy_and_progression(tmp_path) -> None:
    store = BrainstormerStore(tmp_path)
    # Reproduce the exact user scenario:
    # Project: Farm -> Topic: Planting Method
    # Q1: Soil or Hydro?
    # Q2: Maintenance time? (subquestion of Q1)
    # Q3: Water capacity? (subquestion of Q1, depends on Q2)
    # A: 1hr daily maintenance (grounds Q2)
    # E: Water source telemetry (grounds Q3)
    # D: Soil planting phase 1 (decided by Q2 & Q3)
    init = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.PROJECT,
                target_id="farm",
                expected_revision=0,
                values={"title": "Experimental Farm"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.TOPIC,
                target_id="topic-planting",
                expected_revision=0,
                values={"title": "Planting Method"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                expected_revision=0,
                values={"title": "Soil or Hydro?", "topic_id": "topic-planting"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q2",
                expected_revision=0,
                values={"title": "Is maintenance time enough?", "topic_id": "topic-planting"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q3",
                expected_revision=0,
                values={"title": "Is water capacity enough?", "topic_id": "topic-planting"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.ASSUMPTION,
                target_id="asm-maintenance",
                expected_revision=0,
                values={"title": "Can maintain 1 hour daily", "topic_id": "topic-planting"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.EVIDENCE,
                target_id="evi-water",
                expected_revision=0,
                values={"title": "Water source telemetry", "source": "sensors", "topic_id": "topic-planting"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.review(init["proposal_id"], actor_id="orchestrator", approve=True, note="approved")

    # Connect relationships
    link_tx = store.propose(
        transaction(
            "farm",
            # Hierarchy: Topic -> Q1, Q1 -> Q2, Q1 -> Q3
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.TOPIC,
                target_id="topic-planting",
                values={"source_id": "topic-planting", "target_id": "q1", "relation": "contains"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                values={"source_id": "q1", "target_id": "q2", "relation": "subquestion"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                values={"source_id": "q1", "target_id": "q3", "relation": "subquestion"},
            ),
            # Dependency: Q3 depends on Q2 being resolved
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q3",
                values={"source_id": "q3", "target_id": "q2", "relation": "depends_on"},
            ),
            # Grounding: Assumption -> Q2, Evidence -> Q3
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.ASSUMPTION,
                target_id="asm-maintenance",
                values={"source_id": "asm-maintenance", "target_id": "q2", "relation": "grounds"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.EVIDENCE,
                target_id="evi-water",
                values={"source_id": "evi-water", "target_id": "q3", "relation": "grounds"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.commit_safe(link_tx["proposal_id"], actor_id="brainstormer")

    # Inspect decision map
    dmap = store.get_decision_map("farm")
    edges = dmap["edges"]

    # Verify link categories
    sub_edge = next(e for e in edges if e["source"] == "q1" and e["target"] == "q2")
    assert sub_edge["category"] == RelationCategory.HIERARCHY.value

    dep_edge = next(e for e in edges if e["source"] == "q3" and e["target"] == "q2")
    assert dep_edge["category"] == RelationCategory.DEPENDENCY.value

    grounds_edge = next(e for e in edges if e["source"] == "asm-maintenance" and e["target"] == "q2")
    assert grounds_edge["category"] == RelationCategory.DEPENDENCY.value

    # Verify Progression:
    # Q2 is READY, Q3 is BLOCKED by Q2
    prog = dmap["progression"]
    assert "q2" in prog["ready_questions"]
    blocked_q3 = next(b for b in prog["blocked_questions"] if b["id"] == "q3")
    assert "q2" in blocked_q3["blocked_by"]

    # Set active discussion question to Q2
    act = store.set_active_question("farm", "q2")
    assert act["active_question_id"] == "q2"

    dmap_after_active = store.get_decision_map("farm")
    q2_node = next(n for n in dmap_after_active["nodes"] if n["id"] == "q2")
    assert q2_node["is_current"] is True

    # Now resolve Q2
    res_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.RESOLVE,
                kind=ObjectKind.QUESTION,
                target_id="q2",
                expected_revision=1,
                values={"resolution": "1 hour per day is sufficient for automated drip"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.commit_safe(res_prop["proposal_id"], actor_id="brainstormer")

    # Q3 must now be unblocked and READY!
    dmap_res = store.get_decision_map("farm")
    prog_res = dmap_res["progression"]
    assert "q3" in prog_res["ready_questions"]
    assert not any(b["id"] == "q3" for b in prog_res["blocked_questions"])
    assert prog_res["recommended_next_question_id"] == "q3"

    # Finally propose Decision D grounded in Q2, Q3, and evidence
    dec_prop = store.propose(
        transaction(
            "farm",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.DECISION,
                target_id="dec-soil-phase1",
                expected_revision=0,
                values={"title": "Decision: Phase 1 adopts soil planting", "choice": "soil"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q2",
                values={"source_id": "q2", "target_id": "dec-soil-phase1", "relation": "grounds"},
            ),
            StateOperation(
                action=TransactionAction.LINK,
                kind=ObjectKind.QUESTION,
                target_id="q3",
                values={"source_id": "q3", "target_id": "dec-soil-phase1", "relation": "grounds"},
            ),
        ),
        requested_by="brainstormer",
    )
    assert dec_prop["review_required"] is True
    store.review(dec_prop["proposal_id"], actor_id="orchestrator", approve=True, note="user confirmed")

    final_map = store.get_decision_map("farm")
    dec_node = next(n for n in final_map["nodes"] if n["id"] == "dec-soil-phase1")
    assert "q2" in dec_node["grounding_ids"]
    assert "q3" in dec_node["grounding_ids"]


def test_mcp_worker_decision_map_and_active_question(monkeypatch, tmp_path) -> None:
    from uuma import mcp_worker

    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")

    store = BrainstormerStore(tmp_path / "brainstormer")
    prop = store.propose(
        transaction(
            "p1",
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.PROJECT,
                target_id="p1",
                expected_revision=0,
                values={"title": "Test Project", "objective": "Testing"},
            ),
            StateOperation(
                action=TransactionAction.CREATE,
                kind=ObjectKind.QUESTION,
                target_id="q1",
                expected_revision=0,
                values={"title": "Question 1"},
            ),
        ),
        requested_by="brainstormer",
    )
    store.review(prop["proposal_id"], actor_id="orchestrator", approve=True, note="approve")

    dmap = mcp_worker.brainstormer_get_decision_map("p1")
    assert dmap["project_id"] == "p1"
    assert len(dmap["nodes"]) >= 1

    act_res = mcp_worker.brainstormer_set_active_question("p1", "q1")
    assert act_res["active_question_id"] == "q1"

    updated_map = mcp_worker.brainstormer_get_decision_map("p1")
    assert updated_map["active_question_id"] == "q1"


