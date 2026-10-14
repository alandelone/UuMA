from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rstv4.models import TrackFirstEvidenceInput
from rstv4.studio import DocumentValidationError, StudioService
from rstv4.studio_api import create_app
from test_studio_suggestions import counts, decision_url, request_for
from test_writing_studio import complete_document, create_studio, wait_for_job


def grouped_fixture(tmp_path: Path):
    service, track_id, manuscript_id = create_studio(tmp_path)
    document = complete_document(service.get_workspace(manuscript_id))
    first = document["sections"][0]["paragraphs"][0]
    for index in [2, 3]:
        paragraph = deepcopy(first)
        paragraph["id"] = f"paragraph-{index}"
        paragraph["intents"][0]["id"] = f"intent-{index}"
        paragraph["intents"][0]["thoughts"][0].update(
            id=f"thought-{index}", text=f"Author thought {index}."
        )
        document["sections"][0]["paragraphs"].append(paragraph)
    source = service.track_service.add_evidence(
        TrackFirstEvidenceInput(
            track_id=track_id,
            paper_id="run:group-fixture",
            statement="Group source fixture",
            excerpt="Exact original source",
            location="page 1",
            confidence=0.8,
            relation="SUPPORTS",
            extractor_model="TEST_FIXTURE",
            prompt_version="TEST_FIXTURE",
        )
    )
    first["intents"][0]["thoughts"][0].update(
        citation_mode="SELECTED",
        citations=[{"evidence_id": source["evidence_id"], "selected": True}],
    )
    asset = service.store_asset(manuscript_id, "group-table.csv", "text/csv", b"x,y\n1,2\n")
    first["asset_ids"] = [asset["asset_id"]]
    first["formulas"] = [{"id": "group-formula", "latex": "x=1", "caption": "Author formula"}]
    group = {
        "id": "group-author",
        "label": "Author grouping",
        "paragraph_ids": [first["id"], "paragraph-2"],
        "source_version": "author-fixture-v1",
    }
    document["sections"][0].update(
        paragraph_groups=[group], block_order=[group["id"], "paragraph-3"]
    )
    document["sections"].append(
        {"id": "section-empty", "title": "Empty destination", "role": "Custom", "paragraphs": []}
    )
    service.save_document(
        manuscript_id, base_revision=0, operation_id="group-initial", document=document
    )
    return service, manuscript_id, document


def test_group_move_round_trip_undo_redo_preserves_associations_and_links(tmp_path: Path):
    service, manuscript_id, before = grouped_fixture(tmp_path)
    review = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    comment = service.import_comments(
        review["review_round_id"], [{"text": "Regroup", "include": True}], source="PASTED"
    )[0]
    moved = deepcopy(before)
    source, destination = moved["sections"]
    group = source["paragraph_groups"].pop()
    members = [item for item in source["paragraphs"] if item["id"] in group["paragraph_ids"]]
    source["paragraphs"] = [item for item in source["paragraphs"] if item not in members]
    source["block_order"] = ["paragraph-3"]
    destination.update(paragraphs=members, paragraph_groups=[group], block_order=[group["id"]])
    changed = service._changed_block_ids(before, moved)
    assert {group["id"], *group["paragraph_ids"]}.issubset(changed)
    with TestClient(create_app(tmp_path)) as client:
        endpoint = f"/api/manuscripts/{manuscript_id}"
        for revision, (kind, document) in enumerate(
            [("MOVE_BLOCKS", moved), ("UNDO", before), ("REDO", moved)], 1
        ):
            saved = client.put(
                f"{endpoint}/document",
                json={
                    "base_revision": revision,
                    "operation_id": f"group-{kind}",
                    "operation_kind": kind,
                    "document": document,
                    "comment_ids": [comment["comment_id"]],
                },
            )
            assert saved.status_code == 200, saved.text
            assert StudioService(tmp_path).get_workspace(manuscript_id)["document"] == document
            assert (
                client.get(f"{endpoint}/document-revisions/{revision + 1}").json()["document"]
                == document
            )
        links = service.list_comments(manuscript_id)[0]["changes"]
        assert {item["operation_id"] for item in links} == {
            "group-MOVE_BLOCKS",
            "group-UNDO",
            "group-REDO",
        }
        assert client.get(f"{endpoint}/document-revisions/1").json()["document"] == before


@pytest.mark.parametrize(
    "defect",
    [
        "missing_order",
        "group_type",
        "order_type",
        "member_type",
        "duplicate_member",
        "foreign_member",
        "two_owners",
        "duplicate_order",
        "missing_root",
        "wrong_reading_order",
        "duplicate_id",
        "paper_id",
        "label_type",
    ],
)
def test_invalid_group_save_is_atomic(tmp_path: Path, defect: str):
    service, manuscript_id, original = grouped_fixture(tmp_path)
    document = deepcopy(original)
    section = document["sections"][0]
    group = section["paragraph_groups"][0]
    if defect == "missing_order":
        del section["block_order"]
    elif defect == "group_type":
        section["paragraph_groups"] = "not a list"
    elif defect == "order_type":
        section["block_order"] = "not a list"
    elif defect == "member_type":
        group["paragraph_ids"] = [True]
    elif defect == "duplicate_member":
        group["paragraph_ids"].append(group["paragraph_ids"][0])
    elif defect == "foreign_member":
        group["paragraph_ids"].append("other-section-paragraph")
    elif defect == "two_owners":
        section["paragraph_groups"].append({**group, "id": "group-other"})
        section["block_order"].append("group-other")
    elif defect == "duplicate_order":
        section["block_order"].append(group["id"])
    elif defect == "missing_root":
        section["block_order"].remove("paragraph-3")
    elif defect == "wrong_reading_order":
        section["paragraphs"].reverse()
    elif defect == "duplicate_id":
        group["id"] = "group-formula"
    elif defect == "paper_id":
        group["id"] = manuscript_id
    else:
        group["label"] = ["not author text"]
    before_counts = counts(service)
    with TestClient(create_app(tmp_path)) as client:
        response = client.put(
            f"/api/manuscripts/{manuscript_id}/document",
            json={"base_revision": 1, "operation_id": "group-invalid", "document": document},
        )
        assert response.status_code == 422, response.text
    assert counts(service) == before_counts
    assert service.get_workspace(manuscript_id)["document_revision"] == 1
    assert StudioService(tmp_path).get_workspace(manuscript_id)["document"] == original


@pytest.mark.parametrize("empty", [True, False])
def test_unresolved_group_can_save_but_cannot_be_silently_generated(tmp_path: Path, empty: bool):
    service, manuscript_id, document = grouped_fixture(tmp_path)
    document["sections"].pop()
    if empty:
        document["sections"][0]["paragraph_groups"].append(
            {"id": "group-reserved", "label": "Next purpose", "paragraph_ids": []}
        )
        document["sections"][0]["block_order"].append("group-reserved")
    else:
        document["sections"][0]["paragraph_groups"][0]["label"] = ""
    service.save_document(
        manuscript_id, base_revision=1, operation_id="group-unresolved", document=document
    )
    before = counts(service)
    with pytest.raises(DocumentValidationError) as failure:
        service.create_job(manuscript_id, "GENERATE", input_revision=2)
    expected = "group-reserved" if empty else "group-author"
    assert any(item["path"] == expected for item in failure.value.issues)
    assert counts(service) == before
    assert StudioService(tmp_path).get_workspace(manuscript_id)["document"] == document


def test_group_generation_uses_frozen_members_and_keeps_order_and_original_context(tmp_path: Path):
    service, manuscript_id, document = grouped_fixture(tmp_path)
    document["sections"].pop()
    service.save_document(
        manuscript_id, base_revision=1, operation_id="group-ready", document=document
    )
    calls = []

    def realize(task, payload):
        calls.append(deepcopy(payload))
        thought = payload["intents"][0]["thoughts"][0]
        citation = f" [@{thought['citations'][0]['evidence_id']}]" if thought["citations"] else ""
        return {
            "paragraph": thought["text"] + citation,
            "sentence_mappings": [{"sentence": 0, "thought_ids": [thought["id"]]}],
        }

    service.gateway.analyze = realize
    # Real artifact compiler; only the language model is a declared fixture.
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=2))
    assert job["status"] == "SUCCEEDED", job
    group = document["sections"][0]["paragraph_groups"][0]
    assert [item.get("paragraph_group") for item in calls] == [group, group, None]
    generated = service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])
    paragraphs = [item for item in generated["blocks"] if item["kind"] == "paragraph"]
    assert [item["object_id"] for item in paragraphs] == [
        item["id"] for item in document["sections"][0]["paragraphs"]
    ]
    assert [item.get("group_id") for item in paragraphs] == [group["id"], group["id"], None]
    assert paragraphs[0]["formulas"] == document["sections"][0]["paragraphs"][0]["formulas"]
    assert len(generated["references"]) == 1
    assert {item["artifact_kind"] for item in generated["artifacts"]} == {
        "MARKDOWN",
        "GENERATED_JSON",
        "TEX",
        "BIB",
        "PDF",
    }
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.studio.gateway.analyze = lambda task, payload: {
            "answer": "Discussion only"
        }
        endpoint = f"/api/manuscripts/{manuscript_id}"
        discussed = client.post(
            f"{endpoint}/chat",
            json={
                "content": "Annotate this original group",
                "anchor_type": "paragraph_group",
                "anchor_id": group["id"],
                "anchor_revision": 2,
                "quote": {"annotation": "Keep the original group"},
            },
        )
        assert discussed.status_code == 201, discussed.text
        agent = discussed.json()["agent"]
        changed = deepcopy(document)
        changed["sections"][0]["paragraph_groups"] = []
        changed["sections"][0]["block_order"] = [
            item["id"] for item in changed["sections"][0]["paragraphs"]
        ]
        service.save_document(
            manuscript_id, base_revision=2, operation_id="group-ungroup", document=changed
        )
        context = client.get(f"{endpoint}/chat/{agent['message_id']}/context").json()
        assert context["quote"]["source"]["anchor_revision"] == 2
        assert (
            context["quote"]["object_text"]
            == "The author decides the central scientific claim.\nAuthor thought 2."
        )
        assert (
            service.get_generated_version(manuscript_id, generated["generated_version_id"])
            == generated
        )


@pytest.mark.parametrize("target_type", ["section", "paragraph_group"])
def test_structural_adoption_preserves_explicit_group_and_reading_order(
    tmp_path: Path, target_type: str
):
    service, manuscript_id, document = grouped_fixture(tmp_path)
    section = document["sections"][0]
    target_id = section["id"] if target_type == "section" else "group-author"
    raw = {
        "kind": "STRUCTURE",
        "title": "Add author slot",
        "rationale": "Preserve original thoughts",
        "changes": [
            {
                "action": "INSERT_PARAGRAPH",
                "target_type": target_type,
                "target_id": target_id,
                "purpose": "New slot",
                "paradigm": "Author custom",
                "intent_labels": ["Author decides later"],
            }
        ],
    }
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.studio.gateway.analyze = lambda task, payload: {
            "answer": "Preview only",
            "suggestions": [raw],
        }
        endpoint = f"/api/manuscripts/{manuscript_id}"
        discussed = client.post(
            f"{endpoint}/chat",
            json={
                "content": "Discuss group",
                "anchor_type": "paragraph_group",
                "anchor_id": "group-author",
                "anchor_revision": 1,
            },
        )
        assert discussed.status_code == 201, discussed.text
        agent = discussed.json()["agent"]
        accepted = client.post(decision_url(manuscript_id, agent), json=request_for(agent))
        assert accepted.status_code == 201, accepted.text
        adopted = service.get_workspace(manuscript_id)["document"]
        new = next(
            item for item in adopted["sections"][0]["paragraphs"] if item["purpose"] == "New slot"
        )
        assert not new["intents"][0]["thoughts"]
        actual = adopted["sections"][0]
        if target_type == "paragraph_group":
            assert actual["block_order"] == section["block_order"]
            assert actual["paragraph_groups"][0]["paragraph_ids"] == [
                *section["paragraph_groups"][0]["paragraph_ids"],
                new["id"],
            ]
            assert actual["paragraphs"][-1]["id"] == "paragraph-3"
        else:
            assert actual["block_order"] == [*section["block_order"], new["id"]]
            assert actual["paragraph_groups"] == section["paragraph_groups"]
        assert [item for item in actual["paragraphs"] if item["id"] != new["id"]] == section[
            "paragraphs"
        ]
        assert StudioService(tmp_path).get_workspace(manuscript_id)["document"] == adopted


def test_moving_intent_or_thought_marks_actual_parent_links_as_changed(tmp_path: Path):
    service, _, document = grouped_fixture(tmp_path)
    before = deepcopy(document)
    first, second = document["sections"][0]["paragraphs"][:2]
    moved = first["intents"][0]["thoughts"].pop()
    second["intents"][0]["thoughts"].append(moved)
    changed = service._changed_block_ids(before, document)
    assert {moved["id"], first["intents"][0]["id"], second["intents"][0]["id"]}.issubset(changed)
    before = deepcopy(document)
    intent = first["intents"].pop()
    second["intents"].append(intent)
    changed = service._changed_block_ids(before, document)
    assert {intent["id"], first["id"], second["id"]}.issubset(changed)
