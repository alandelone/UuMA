from __future__ import annotations

import json

import pytest

from uuma.brainstormer_state import (
    BrainstormerError,
    BrainstormerStore,
    ObjectKind,
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
