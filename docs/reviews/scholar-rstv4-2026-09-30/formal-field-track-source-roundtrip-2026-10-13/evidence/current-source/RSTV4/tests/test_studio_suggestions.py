from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from rstv4.database import transaction
from rstv4.models import TrackFirstEvidenceInput
from rstv4.service import RevisionConflictError
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from test_writing_studio import complete_document, create_studio


def fixture(tmp_path: Path):
    service, track_id, manuscript_id = create_studio(tmp_path)
    evidence = [
        service.track_service.add_evidence(
            TrackFirstEvidenceInput(
                track_id=track_id,
                paper_id=f"run:suggestion-{index}",
                statement=f"Source {index}",
                excerpt=f"Original source excerpt {index}",
                location="page 1",
                confidence=0.8,
                relation="SUPPORTS",
                extractor_model="TEST_FIXTURE",
                prompt_version="TEST_FIXTURE",
            )
        )
        for index in [1, 2]
    ]
    document = complete_document(service.get_workspace(manuscript_id))
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought.update(
        text="Original 😀 author thought.",
        citation_mode="SELECTED",
        citations=[{"evidence_id": evidence[0]["evidence_id"], "selected": True}],
    )
    service.save_document(
        manuscript_id, base_revision=0, operation_id="suggestion-baseline", document=document
    )
    return service, manuscript_id, document, evidence


def proposal(document, kind="STRUCTURE"):
    paragraph = document["sections"][0]["paragraphs"][0]
    return {
        "kind": kind,
        "title": "Compare original choices",
        "rationale": "Preserve the author meaning",
        "changes": [
            {
                "action": "SET_FIELD",
                "target_type": "paragraph",
                "target_id": paragraph["id"],
                "field": "purpose",
                "value": "Clarify the boundary",
            },
            {
                "action": "INSERT_INTENT",
                "target_type": "paragraph",
                "target_id": paragraph["id"],
                "label": "Boundary condition",
            },
        ],
    }


def discuss(client, manuscript_id, raw):
    client.app.state.studio.gateway.analyze = lambda task, payload: {
        "answer": "Discussion, not an author thought.",
        "suggestions": raw,
        "_contract": {"prompt_version": "TEST_FIXTURE", "model": "TEST_FIXTURE"},
    }
    return client.post(
        f"/api/manuscripts/{manuscript_id}/chat",
        json={
            "content": "Source",
            "anchor_type": "thought",
            "anchor_id": "thought_author_1",
            "anchor_revision": 1,
            "quote": {"annotation": "Keep the original meaning"},
        },
    )


def request_for(
    agent, outcome="ACCEPT_ALL", *, decision_id="decision-original-001", revision=1, selected=None
):
    suggestion = agent["quoted"]["suggestions"][0]
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "decision_id": decision_id,
        "outcome": outcome,
        "base_revision": revision,
        "selected_change_ids": selected
        if selected is not None
        else [item["change_id"] for item in suggestion["changes"]],
        "confirmed_changed_ids": [],
        "comment_ids": [],
    }


def decision_url(manuscript_id, agent):
    return f"/api/manuscripts/{manuscript_id}/chat/{agent['message_id']}/decisions"


def counts(service):
    with transaction(service.db_path) as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "studio_operations",
                "studio_changes",
                "studio_suggestion_decisions",
                "studio_jobs",
            ]
        }


@pytest.mark.parametrize("partial", [False, True])
def test_explicit_adoption_preserves_author_ids_citations_and_reversible_history(
    tmp_path: Path, partial: bool
):
    service, manuscript_id, before, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        reply = discuss(client, manuscript_id, [proposal(before)])
        assert reply.status_code == 201, reply.text
        agent = reply.json()["agent"]
        assert service.get_workspace(manuscript_id)["document"] == before
        round_row = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
        comment = service.import_comments(
            round_row["review_round_id"], [{"text": "Clarify", "include": True}], source="PASTED"
        )[0]
        request = request_for(agent)
        if partial:
            request.update(
                outcome="ACCEPT_PARTIAL", selected_change_ids=request["selected_change_ids"][:1]
            )
        request["comment_ids"] = [comment["comment_id"]]
        accepted = client.post(decision_url(manuscript_id, agent), json=request)
        assert accepted.status_code == 201, accepted.text
        result = accepted.json()
        after = result["workspace"]["document"]
        original = before["sections"][0]["paragraphs"][0]
        paragraph = after["sections"][0]["paragraphs"][0]
        assert paragraph["purpose"] == "Clarify the boundary"
        assert paragraph["intents"][: len(original["intents"])] == original["intents"]
        if partial:
            assert paragraph["intents"] == original["intents"]
        else:
            assert paragraph["intents"][-1]["thoughts"] == []
            assert paragraph["intents"][-1]["label"] == "Boundary condition"
        assert result["workspace"]["document_revision"] == 2
        provenance = result["decision"]["provenance"]
        assert provenance["source"]["anchor_revision"] == 1
        assert provenance["source"]["anchor_id"] == "thought_author_1"
        assert provenance["model_contract"]["model"] == "TEST_FIXTURE"
        assert len(provenance["changes"]) == (1 if partial else 2)
        linked = service.list_comments(manuscript_id)[0]["changes"][0]
        assert linked["operation_id"] == request["decision_id"]
        assert json.loads(linked["before_json"]) == before
        assert json.loads(linked["after_json"]) == after
        service.archive_comment(comment["comment_id"])
        replay = client.post(decision_url(manuscript_id, agent), json=request)
        assert replay.status_code == 201 and replay.json()["idempotent_replay"]
        assert replay.json()["decision"] == result["decision"]
        changed = {**request, "outcome": "REJECT", "selected_change_ids": [], "comment_ids": []}
        assert client.post(decision_url(manuscript_id, agent), json=changed).status_code == 409
        service.save_document(
            manuscript_id,
            base_revision=2,
            operation_id="undo-suggestion-001",
            operation_kind="UNDO",
            document=before,
        )
        assert service.get_workspace(manuscript_id)["document"] == before
        service.save_document(
            manuscript_id,
            base_revision=3,
            operation_id="redo-suggestion-001",
            operation_kind="REDO",
            document=after,
        )
        assert service.get_workspace(manuscript_id)["document"] == after
        assert counts(service) == {
            "studio_operations": 4,
            "studio_changes": 4,
            "studio_suggestion_decisions": 1,
            "studio_jobs": 0,
        }
        reopened = StudioService(tmp_path)
        assert reopened.get_workspace(manuscript_id)["document"] == after
        preview = reopened.suggestion_preview(
            manuscript_id, agent["message_id"], request["suggestion_id"]
        )
        assert preview["decisions"][0] == result["decision"]
        assert (
            reopened.list_chat(manuscript_id)[1]["quoted"]["suggestions"]
            == agent["quoted"]["suggestions"]
        )


@pytest.mark.parametrize("partial", [False, True])
def test_wording_changes_apply_only_exact_utf16_ranges_not_the_agent_reply(tmp_path: Path, partial: bool):
    _service, manuscript_id, before, _ = fixture(tmp_path)
    raw = {
        "kind": "WORDING",
        "title": "Two wording edits",
        "rationale": "Keep the claim",
        "changes": [
            {
                "action": "REPLACE_TEXT",
                "target_type": "thought",
                "target_id": "thought_author_1",
                "field": "text",
                "value": replacement,
                "quote": {"text": text, "start": start, "end": end, "offset_unit": "utf16"},
            }
            for text, start, end, replacement in [("😀", 9, 11, "joy"), ("thought", 19, 26, "idea")]
        ],
    }
    with TestClient(create_app(tmp_path)) as client:
        reply = discuss(client, manuscript_id, [raw])
        assert reply.status_code == 201, reply.text
        agent = reply.json()["agent"]
        request = request_for(agent)
        if partial:
            request.update(outcome="ACCEPT_PARTIAL", selected_change_ids=request["selected_change_ids"][1:])
        accepted = client.post(decision_url(manuscript_id, agent), json=request)
        assert accepted.status_code == 201, accepted.text
        thought = accepted.json()["workspace"]["document"]["sections"][0]["paragraphs"][0][
            "intents"
        ][0]["thoughts"][0]
        assert thought["text"] == ("Original 😀 author idea." if partial else "Original joy author idea.")
        assert (
            thought["citations"]
            == before["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["citations"]
        )


def test_source_candidate_stays_unselected_and_does_not_uncheck_existing_author_choice(
    tmp_path: Path,
):
    _service, manuscript_id, before, evidence = fixture(tmp_path)
    raw = {
        "kind": "SOURCE",
        "title": "Relevant real sources",
        "rationale": "Source candidates need author selection",
        "changes": [
            {
                "action": "ADD_SOURCE",
                "target_type": "thought",
                "target_id": "thought_author_1",
                "evidence_id": row["evidence_id"],
            }
            for row in evidence
        ],
    }
    with TestClient(create_app(tmp_path)) as client:
        reply = discuss(client, manuscript_id, [raw])
        assert reply.status_code == 201, reply.text
        agent = reply.json()["agent"]
        accepted = client.post(decision_url(manuscript_id, agent), json=request_for(agent))
        assert accepted.status_code == 201, accepted.text
        thought = accepted.json()["workspace"]["document"]["sections"][0]["paragraphs"][0][
            "intents"
        ][0]["thoughts"][0]
        assert thought["text"] == "Original 😀 author thought."
        assert (
            thought["citations"][0]
            == before["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["citations"][0]
        )
        assert thought["citations"][1]["selected"] is False
        assert thought["citations"][1]["evidence_id"] == evidence[1]["evidence_id"]
        assert thought["citation_mode"] == "PENDING"
        assert (
            accepted.json()["decision"]["provenance"]["changes"][1]["evidence"]["excerpt"]
            == "Original source excerpt 2"
        )


@pytest.mark.parametrize(
    "damage",
    [
        "delete",
        "change",
        "stale",
        "archive-comment",
        "wrong-owner",
        "unknown-change",
        "partial-all",
        "full-missing",
        "reject-edit",
    ],
)
def test_invalid_adoption_writes_no_document_operation_or_decision(tmp_path: Path, damage: str):
    service, manuscript_id, before, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [proposal(before)]).json()["agent"]
        request = request_for(agent)
        url = decision_url(manuscript_id, agent)
        if damage in {"delete", "change", "stale"}:
            altered = deepcopy(before)
            if damage == "delete":
                altered["sections"][0]["paragraphs"] = []
            else:
                altered["sections"][0]["paragraphs"][0]["purpose"] = "New author purpose"
            service.save_document(
                manuscript_id, base_revision=1, operation_id="later-author-edit", document=altered
            )
            if damage != "stale":
                request["base_revision"] = 2
        elif damage == "archive-comment":
            round_row = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
            comment = service.import_comments(
                round_row["review_round_id"], [{"text": "Review", "include": True}], source="PASTED"
            )[0]
            service.archive_comment(comment["comment_id"])
            request["comment_ids"] = [comment["comment_id"]]
        elif damage == "wrong-owner":
            other = service.create_manuscript(
                service.get_workspace(manuscript_id)["manuscript"]["track_id"], "Other"
            )["manuscript"]["manuscript_id"]
            url = decision_url(other, agent)
        elif damage == "unknown-change":
            request["selected_change_ids"] = ["another-suggestion-change"]
        elif damage == "partial-all":
            request["outcome"] = "ACCEPT_PARTIAL"
        elif damage == "full-missing":
            request["selected_change_ids"] = request["selected_change_ids"][:1]
        else:
            request["outcome"] = "REJECT"
        snapshot, totals = service.get_workspace(manuscript_id), counts(service)
        failed = client.post(url, json=request)
        assert failed.status_code in {404, 409, 422}, failed.text
        assert service.get_workspace(manuscript_id) == snapshot
        assert counts(service) == totals


def test_changed_target_requires_current_comparison_and_explicit_confirmation(tmp_path: Path):
    service, manuscript_id, before, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [proposal(before)]).json()["agent"]
        altered = deepcopy(before)
        altered["sections"][0]["paragraphs"][0]["purpose"] = "Later author purpose"
        service.save_document(
            manuscript_id, base_revision=1, operation_id="author-later-purpose", document=altered
        )
        request = request_for(agent, revision=2)
        preview = service.suggestion_preview(
            manuscript_id, agent["message_id"], request["suggestion_id"]
        )
        assert preview["changes"][0]["before"] == before["sections"][0]["paragraphs"][0]["purpose"]
        assert preview["changes"][0]["current_before"] == "Later author purpose"
        assert preview["changes"][0]["target_changed"] is True
        request["confirmed_changed_ids"] = [preview["changes"][0]["change_id"]]
        accepted = client.post(decision_url(manuscript_id, agent), json=request)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["decision"]["provenance"]["author_revision_at_decision"] == 2


def test_partial_remainder_is_reviewable_but_a_new_decision_cannot_duplicate_an_adopted_change(
    tmp_path: Path,
):
    service, manuscript_id, before, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [proposal(before)]).json()["agent"]
        request = request_for(agent)
        first, second = request["selected_change_ids"]
        request.update(outcome="ACCEPT_PARTIAL", selected_change_ids=[first])
        assert client.post(decision_url(manuscript_id, agent), json=request).status_code == 201
        preview = service.suggestion_preview(
            manuscript_id, agent["message_id"], request["suggestion_id"]
        )
        assert [change["already_adopted"] for change in preview["changes"]] == [True, False]
        snapshot, totals = service.get_workspace(manuscript_id), counts(service)
        duplicate = {
            **request,
            "decision_id": "another-id-same-choice",
            "base_revision": 2,
            "confirmed_changed_ids": [first],
        }
        assert client.post(decision_url(manuscript_id, agent), json=duplicate).status_code == 422
        assert service.get_workspace(manuscript_id) == snapshot and counts(service) == totals
        remainder = {
            **request,
            "decision_id": "remaining-choice-001",
            "base_revision": 2,
            "selected_change_ids": [second],
        }
        assert client.post(decision_url(manuscript_id, agent), json=remainder).status_code == 201
        preview = service.suggestion_preview(
            manuscript_id, agent["message_id"], request["suggestion_id"]
        )
        assert all(change["already_adopted"] for change in preview["changes"])
        assert len(preview["decisions"]) == 2


@pytest.mark.parametrize("unavailable", ["range", "source"])
def test_changed_wording_range_or_deleted_source_cannot_be_adopted_even_with_confirmation(
    tmp_path: Path, unavailable: str
):
    service, manuscript_id, before, evidence = fixture(tmp_path)
    raw = {
        "kind": "WORDING",
        "title": "A wording edit",
        "rationale": "Preserve original meaning",
        "changes": [
            {
                "action": "REPLACE_TEXT",
                "target_type": "thought",
                "target_id": "thought_author_1",
                "field": "text",
                "value": "idea",
                "quote": {"text": "thought", "start": 19, "end": 26, "offset_unit": "utf16"},
            }
        ],
    }
    if unavailable == "source":
        raw.update(
            kind="SOURCE",
            changes=[
                {
                    "action": "ADD_SOURCE",
                    "target_type": "thought",
                    "target_id": "thought_author_1",
                    "evidence_id": evidence[1]["evidence_id"],
                }
            ],
        )
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [raw]).json()["agent"]
        request = request_for(agent)
        if unavailable == "range":
            altered = deepcopy(before)
            altered["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = (
                "New "
                + altered["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"]
            )
            service.save_document(
                manuscript_id,
                base_revision=1,
                operation_id="author-shifted-range",
                document=altered,
            )
            request["base_revision"] = 2
            preview = service.suggestion_preview(
                manuscript_id, agent["message_id"], request["suggestion_id"]
            )
            assert preview["changes"][0]["available"] is False
            assert preview["changes"][0]["range_changed"] is True
        else:
            with transaction(service.db_path) as conn:
                conn.execute(
                    "DELETE FROM evidence WHERE evidence_id=?", (evidence[1]["evidence_id"],)
                )
            preview = service.suggestion_preview(manuscript_id, agent["message_id"], request["suggestion_id"])
            assert preview["changes"][0]["available"] is False
            assert preview["changes"][0]["source_unavailable"] is True
        request["confirmed_changed_ids"] = request["selected_change_ids"]
        snapshot, totals = service.get_workspace(manuscript_id), counts(service)
        failed = client.post(decision_url(manuscript_id, agent), json=request)
        assert failed.status_code == 422, failed.text
        assert service.get_workspace(manuscript_id) == snapshot and counts(service) == totals


def test_reject_and_ordinary_discussion_leave_document_jobs_and_stage_unchanged(tmp_path: Path):
    service, manuscript_id, before, _ = fixture(tmp_path)
    snapshot = service.get_workspace(manuscript_id)
    with TestClient(create_app(tmp_path)) as client:
        ordinary = discuss(client, manuscript_id, [])
        assert ordinary.status_code == 201
        assert "suggestions" not in ordinary.json()["agent"]["quoted"]
        agent = discuss(client, manuscript_id, [proposal(before)]).json()["agent"]
        request = request_for(agent, "REJECT", selected=[])
        rejected = client.post(decision_url(manuscript_id, agent), json=request)
        assert rejected.status_code == 201, rejected.text
        assert rejected.json()["decision"]["operation_id"] is None
        assert (
            client.post(decision_url(manuscript_id, agent), json=request).json()[
                "idempotent_replay"
            ]
            is True
        )
        assert service.get_workspace(manuscript_id) == snapshot
        assert counts(service) == {
            "studio_operations": 1,
            "studio_changes": 1,
            "studio_suggestion_decisions": 1,
            "studio_jobs": 0,
        }


@pytest.mark.parametrize(
    "damage",
    [
        "made-up-source",
        "invented-thought",
        "missing-target",
        "overlap",
        "wrong-range",
        "wrong-kind",
    ],
)
def test_malformed_model_suggestions_preserve_failed_author_message_without_applying_anything(
    tmp_path: Path, damage: str
):
    service, manuscript_id, before, _ = fixture(tmp_path)
    raw = proposal(before)
    if damage == "made-up-source":
        raw.update(
            kind="SOURCE",
            changes=[
                {
                    "action": "ADD_SOURCE",
                    "target_type": "thought",
                    "target_id": "thought_author_1",
                    "evidence_id": "invented",
                }
            ],
        )
    elif damage == "invented-thought":
        raw["changes"][1]["thoughts"] = [{"text": "Agent-created claim"}]
    elif damage == "missing-target":
        raw["changes"][0]["target_id"] = "missing"
    elif damage in {"overlap", "wrong-range"}:
        change = {
            "action": "REPLACE_TEXT",
            "target_type": "thought",
            "target_id": "thought_author_1",
            "field": "text",
            "value": "Rephrase",
            "quote": {"text": "Original", "start": 0, "end": 8, "offset_unit": "utf16"},
        }
        raw.update(
            kind="WORDING", changes=[change, deepcopy(change)] if damage == "overlap" else [change]
        )
        if damage == "wrong-range":
            change["quote"]["end"] = 9
    else:
        raw["kind"] = "AUTHOR_CLAIM"
    with TestClient(create_app(tmp_path)) as client:
        snapshot, totals = service.get_workspace(manuscript_id), counts(service)
        failed = discuss(client, manuscript_id, [raw])
        assert failed.status_code == 422, failed.text
        assert service.get_workspace(manuscript_id) == snapshot
        assert counts(service) == totals
        assert len(service.list_chat(manuscript_id)) == 1
        assert service.list_chat(manuscript_id)[0]["status"] == "AGENT_FAILED"
        assert (
            service.list_chat(manuscript_id)[0]["quoted"]["annotation"]
            == "Keep the original meaning"
        )


def test_concurrent_retries_and_writers_never_apply_twice_or_overwrite_a_revision(tmp_path: Path):
    service, manuscript_id, before, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [proposal(before)]).json()["agent"]
    request = request_for(agent)
    barrier = Barrier(2)

    def adopt():
        barrier.wait(timeout=5)
        return service.decide_suggestion(manuscript_id, agent["message_id"], **request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: adopt(), range(2)))
    assert sorted(row["idempotent_replay"] for row in results) == [False, True]
    assert results[0]["decision"] == results[1]["decision"]
    assert counts(service)["studio_suggestion_decisions"] == 1
    assert service.get_workspace(manuscript_id)["document_revision"] == 2
    barrier = Barrier(2)

    def write(index):
        document = deepcopy(service.get_workspace(manuscript_id)["document"])
        document["title"] = f"Author choice {index}"
        barrier.wait(timeout=5)
        try:
            return service.save_document(
                manuscript_id,
                base_revision=2,
                operation_id=f"concurrent-{index}",
                document=document,
            )
        except RevisionConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert sum(row is not None for row in results) == 1
    assert service.get_workspace(manuscript_id)["document_revision"] == 3
    assert counts(service)["studio_operations"] == 3


def test_structure_can_append_empty_paragraph_without_replacing_existing_author_content(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    before = complete_document(service.get_workspace(manuscript_id))
    asset = service.store_asset(manuscript_id, "author-table.csv", "text/csv", b"label,value\nA,1\n")
    before["sections"][0]["paragraphs"][0].update(asset_ids=[asset["asset_id"]], formulas=[
        {"id": "author-formula", "latex": "E=mc^2", "caption": "Original formula"}])
    service.save_document(manuscript_id, base_revision=0, operation_id="structure-original-001", document=before)
    raw = {"kind": "STRUCTURE", "title": "Empty follow-up paragraph", "rationale": "The author supplies its thoughts",
           "changes": [{"action": "INSERT_PARAGRAPH", "target_type": "section", "target_id": before["sections"][0]["id"],
                        "purpose": "Boundary", "paradigm": "Conditions then scope", "intent_labels": ["Condition", "Scope"]}]}
    with TestClient(create_app(tmp_path)) as client:
        agent = discuss(client, manuscript_id, [raw]).json()["agent"]
        accepted = client.post(decision_url(manuscript_id, agent), json=request_for(agent))
        assert accepted.status_code == 201, accepted.text
        after = accepted.json()["workspace"]["document"]
        original = before["sections"][0]["paragraphs"]
        assert after["sections"][0]["paragraphs"][:len(original)] == original
        appended = after["sections"][0]["paragraphs"][-1]
        assert appended["purpose"] == "Boundary"
        assert [intent["label"] for intent in appended["intents"]] == ["Condition", "Scope"]
        assert all(intent["thoughts"] == [] for intent in appended["intents"])
        assert appended["asset_ids"] == appended["formulas"] == []
        assert {key: value for key, value in after.items() if key != "sections"} == {key: value for key, value in before.items() if key != "sections"}
