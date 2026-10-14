"""Software contracts: original author identity, explicit placement, history and context."""

import hashlib
import json
import sqlite3
from copy import deepcopy

import pytest
from test_studio_templates import fixture

from rstv4.studio import StudioService
from rstv4.studio_context import structure_object
from rstv4.studio_correspondence import realization_document, unresolved, validate
from rstv4.studio_structure import argument_context
from rstv4.studio_templates import apply_structure


def document():
    source = {"skeleton_id": "sk", "source_sha256": "fixed", "unit_id": "unit"}
    authors = [
        {
            "id": f"ap{n}",
            "purpose": f"Author purpose {n}",
            "paradigm": "Author Ω",
            "logical_relation": "Custom relation",
            "asset_ids": ["asset"] if n == 1 else [],
            "formulas": [{"id": "formula", "latex": "x=1", "caption": "Original"}]
            if n == 1
            else [],
            "intents": [
                {
                    "id": f"ai{n}",
                    "label": f"Original Intent {n}",
                    "thoughts": [
                        {
                            "id": f"at{n}",
                            "text": f"Exact original Ω {n}",
                            "citation_mode": "SELECTED",
                            "citations": [{"evidence_id": "e", "selected": True}],
                        }
                    ],
                }
            ],
        }
        for n in [1, 2]
    ]
    slots = [
        {
            "id": f"tp{n}",
            "purpose": "Structural purpose",
            "paradigm": "Source",
            "asset_ids": [],
            "intents": [
                {
                    "id": f"ti{n}",
                    "label": "Repeated target",
                    "template_source": deepcopy(source),
                    "thoughts": [],
                    "author_intent_ids": [f"ai{n}"],
                }
            ],
            **({"author_context_paragraph_ids": ["ap1"]} if n == 1 else {}),
        }
        for n in [1, 2]
    ]
    return {
        "schema_version": 1,
        "manuscript_id": "ms",
        "title": "Author",
        "abstract": "",
        "venue": "",
        "sections": [
            {
                "id": "target",
                "title": "Root",
                "role": "Source",
                "paragraphs": [slots[0]],
            },
            {
                "id": "target-child",
                "title": "Repeated",
                "role": "Source",
                "parent_section_id": "target",
                "paragraphs": [slots[1]],
            },
            {
                "id": "author",
                "title": "Original",
                "role": "Author",
                "placement_status": "UNPLACED",
                "paragraphs": authors,
                "paragraph_groups": [
                    {
                        "id": "group",
                        "label": "Exact original group",
                        "paragraph_ids": ["ap1", "ap2"],
                    }
                ],
                "block_order": ["group"],
            },
        ],
        "argument_relations": [
            {
                "id": "edge",
                "source_id": "ap1",
                "target_id": "at2",
                "relation": "Comparison Ω",
                "condition": "Exact original condition",
            }
        ],
    }


def test_projection_preserves_original_data_and_places_thoughts_and_context_once():
    raw = document()
    before = deepcopy(raw)
    StudioService._validate_document_shape("ms", raw)
    assert unresolved(raw) == []
    projected = realization_document(raw)
    assert raw == before
    assert projected["author_source_sections"] == [raw["sections"][2]]
    assert [s["id"] for s in projected["sections"]] == ["target", "target-child"]
    thoughts = [
        t
        for s in projected["sections"]
        for p in s["paragraphs"]
        for i in p["intents"]
        for t in i["thoughts"]
    ]
    assert thoughts == [
        i["thoughts"][0] for p in raw["sections"][2]["paragraphs"] for i in p["intents"]
    ]
    first, second = [s["paragraphs"][0] for s in projected["sections"]]
    assert first["formulas"] == raw["sections"][2]["paragraphs"][0]["formulas"]
    assert first["asset_ids"] == ["asset"] and second["asset_ids"] == []
    assert (
        first["author_contexts"][0]["source_group"]
        == raw["sections"][2]["paragraph_groups"][0]
    )
    assert (
        first["author_contexts"][0]["source_paragraph"]
        == raw["sections"][2]["paragraphs"][0]
    )
    assert (
        first["intents"][0]["template_source"]
        == raw["sections"][0]["paragraphs"][0]["intents"][0]["template_source"]
    )
    edges = argument_context(raw, first)
    assert edges[0]["condition"] == "Exact original condition"
    assert (
        edges[0]["source"]["id"] == "ap1"
        and edges[0]["target"]["author_text"] == "Exact original Ω 2"
    )
    assert structure_object(raw, "intent", "ti2")[1] == "Exact original Ω 2"
    assert structure_object(raw, "paragraph", "tp1")[1] == "Exact original Ω 1"
    assert structure_object(raw, "thought", "at1")[1] == "Exact original Ω 1"


@pytest.mark.parametrize(
    "defect",
    [
        "foreign",
        "duplicate",
        "double_owner",
        "wrong_type",
        "source_placed",
        "target_unplaced",
        "no_source",
        "empty_author",
        "self",
        "context_foreign",
        "context_duplicate",
        "context_double_owner",
        "context_unrelated",
        "context_wrong_type",
    ],
)
def test_invalid_correspondence_is_rejected_without_mutation(defect):
    raw = document()
    first = raw["sections"][0]["paragraphs"][0]
    second = raw["sections"][1]["paragraphs"][0]
    intent = first["intents"][0]
    if defect == "foreign":
        intent["author_intent_ids"] = ["foreign"]
    elif defect == "duplicate":
        intent["author_intent_ids"] *= 2
    elif defect == "double_owner":
        second["intents"][0]["author_intent_ids"].append("ai1")
    elif defect == "wrong_type":
        intent["author_intent_ids"] = "ai1"
    elif defect == "source_placed":
        raw["sections"][2].pop("placement_status")
    elif defect == "target_unplaced":
        raw["sections"][0]["placement_status"] = "UNPLACED"
    elif defect == "no_source":
        intent.pop("template_source")
    elif defect == "empty_author":
        raw["sections"][2]["paragraphs"][0]["intents"][0]["thoughts"] = []
    elif defect == "self":
        intent["author_intent_ids"] = ["ti1"]
    elif defect == "context_foreign":
        first["author_context_paragraph_ids"] = ["foreign"]
    elif defect == "context_duplicate":
        first["author_context_paragraph_ids"] *= 2
    elif defect == "context_double_owner":
        second["author_context_paragraph_ids"] = ["ap1"]
    elif defect == "context_unrelated":
        first["author_context_paragraph_ids"] = ["ap2"]
    elif defect == "context_wrong_type":
        first["author_context_paragraph_ids"] = "ap1"
    before = deepcopy(raw)
    with pytest.raises(ValueError):
        validate(raw)
    assert raw == before


def test_partial_mapping_and_missing_context_remain_explicit_generation_blockers():
    raw = document()
    raw["sections"][1]["paragraphs"][0]["intents"][0].pop("author_intent_ids")
    raw["sections"][0]["paragraphs"][0].pop("author_context_paragraph_ids")
    issues = unresolved(raw)
    assert {item["path"] for item in issues} == {"ai2", "ap1"}
    assert "explicit output position" in issues[0]["message"]


def test_legacy_flat_paragraph_source_is_read_without_rewriting_intent():
    raw = document()
    for section in raw["sections"][:2]:
        paragraph = section["paragraphs"][0]
        paragraph["template_source"] = paragraph["intents"][0].pop("template_source")
    before = deepcopy(raw)
    StudioService._validate_document_shape("ms", raw)
    projected = realization_document(raw)
    assert (
        projected["sections"][0]["paragraphs"][0]["author_contexts"][0][
            "template_source"
        ]
        == raw["sections"][0]["paragraphs"][0]["template_source"]
    )
    assert raw == before


def test_replacing_template_releases_references_and_keeps_canonical_author_tree_exact():
    raw = document()
    empty = [{"id": "new", "title": "New", "role": "Source", "paragraphs": []}]
    replaced = apply_structure(raw, empty, "paper", "ms", "REPLACE")
    assert (
        next(s for s in replaced["sections"] if s["id"] == "author")
        == raw["sections"][2]
    )
    assert all(
        not i.get("author_intent_ids")
        for s in replaced["sections"]
        for p in s["paragraphs"]
        for i in p["intents"]
    )
    assert replaced["argument_relations"] == raw["argument_relations"]
    assert {item["path"] for item in unresolved(replaced)}.issuperset({"ai1", "ai2"})


def mapped_fixture(tmp_path):
    service, manuscript_id, original, _, request = fixture(tmp_path)
    original["sections"] = original["sections"][:1]
    service.save_document(
        manuscript_id,
        base_revision=1,
        operation_id="remove-empty-fixture-placeholder",
        document=original,
    )
    request.update(base_revision=2, mode="REPLACE", replace_confirmed=True)
    adopted = service.apply_template(manuscript_id, request)["document"]
    mapped = deepcopy(adopted)
    slots = [
        p
        for s in mapped["sections"]
        if s.get("placement_status") != "UNPLACED"
        for p in s["paragraphs"]
    ]
    originals = [
        p
        for s in mapped["sections"]
        if s.get("placement_status") == "UNPLACED"
        for p in s["paragraphs"]
    ]
    for n, paragraph in enumerate(originals):
        target = slots[min(n, len(slots) - 1)]
        target["intents"][0].setdefault("author_intent_ids", []).append(
            paragraph["intents"][0]["id"]
        )
        if paragraph.get("asset_ids") or paragraph.get("formulas"):
            target.setdefault("author_context_paragraph_ids", []).append(
                paragraph["id"]
            )
    assert unresolved(mapped) == []
    service._check_generate_ready(manuscript_id, mapped)
    return service, manuscript_id, adopted, mapped, originals, slots


def test_actual_template_mapping_http_history_conflicts_and_undo(tmp_path):
    service, manuscript_id, adopted, mapped, originals, _slots = mapped_fixture(
        tmp_path
    )
    changed = service._changed_block_ids(adopted, mapped)
    assert {p["intents"][0]["id"] for p in originals}.issubset(changed)
    assert originals[0]["id"] in changed
    from fastapi.testclient import TestClient

    from rstv4.studio_api import create_app

    with TestClient(create_app(tmp_path)) as client:
        url = f"/api/manuscripts/{manuscript_id}/document"
        payload = {
            "base_revision": 3,
            "operation_id": "map-fixture",
            "operation_kind": "MAP_AUTHOR_INTENT",
            "document": mapped,
        }
        result = client.put(url, json=payload)
        assert result.status_code == 200, result.text
        digest = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
        assert client.put(url, json=payload).json()["idempotent_replay"] is True
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == digest
        forged = deepcopy(mapped)
        forged["sections"][0]["paragraphs"][0]["template_source"]["source_sha256"] = (
            "forged"
        )
        rejection = client.put(
            url,
            json={
                **payload,
                "base_revision": 4,
                "operation_id": "forged-map",
                "document": forged,
            },
        )
        assert rejection.status_code == 422, rejection.text
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == digest
        conflict = client.put(url, json={**payload, "operation_id": "stale-map"})
        assert conflict.status_code == 409
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == digest
        for revision, (kind, doc) in enumerate(
            [("UNDO", adopted), ("REDO", mapped)], 4
        ):
            response = client.put(
                url,
                json={
                    "base_revision": revision,
                    "operation_id": f"map-{kind}",
                    "operation_kind": kind,
                    "document": doc,
                },
            )
            assert response.status_code == 200, response.text
            assert (
                StudioService(tmp_path).get_workspace(manuscript_id)["document"] == doc
            )
        assert (
            client.get(f"/api/manuscripts/{manuscript_id}/document-revisions/3").json()[
                "document"
            ]
            == adopted
        )
    with sqlite3.connect(service.db_path) as conn:
        op = conn.execute(
            "SELECT payload_json,inverse_json FROM studio_operations WHERE operation_id='map-fixture'"
        ).fetchone()
        assert (
            json.loads(op[0])["document"] == mapped
            and json.loads(op[1])["document"] == adopted
        )
        assert conn.execute("SELECT count(*) FROM studio_jobs").fetchone()[0] == 0
        assert (
            conn.execute("SELECT count(*) FROM studio_model_calls").fetchone()[0] == 0
        )
    assert [s for s in mapped["sections"] if s.get("placement_status")] == [
        s for s in adopted["sections"] if s.get("placement_status")
    ]


def test_actual_generation_preserves_mapping_context_citations_and_real_artifacts(
    tmp_path,
):
    from pathlib import Path

    from test_writing_studio import wait_for_job

    service, manuscript_id, adopted, mapped, originals, slots = mapped_fixture(tmp_path)
    service.save_document(
        manuscript_id,
        base_revision=3,
        operation_id="map-for-generation",
        operation_kind="MAP_AUTHOR_INTENT",
        document=mapped,
    )
    captured = []

    def realize(task, payload):
        assert task == "paragraph_realization"
        captured.append(deepcopy(payload))
        thoughts = [t for intent in payload["intents"] for t in intent["thoughts"]]
        evidence_ids = list(
            dict.fromkeys(
                c["evidence_id"]
                for t in thoughts
                for c in t["citations"]
                if c["selected"]
            )
        )
        citation = "".join(f" [@{evidence}]" for evidence in evidence_ids)
        return {
            "paragraph": " ".join(t["text"] for t in thoughts) + citation,
            "sentence_mappings": [
                {"sentence": 0, "thought_ids": [t["id"] for t in thoughts]}
            ],
        }

    service.gateway.analyze = realize
    try:
        job = wait_for_job(
            service, service.create_job(manuscript_id, "GENERATE", input_revision=4)
        )
        assert job["status"] == "SUCCEEDED", job
        assert len(captured) == len(slots)
        expected_thoughts = [
            t for p in originals for i in p["intents"] for t in i["thoughts"]
        ]
        assert [
            t for call in captured for i in call["intents"] for t in i["thoughts"]
        ] == expected_thoughts
        contexts = [context for call in captured for context in call["author_contexts"]]
        assert [context["source_paragraph"] for context in contexts] == originals
        assert all(
            context["source_group"] == mapped["sections"][-1]["paragraph_groups"][0]
            for context in contexts[:2]
        )
        version = service.get_generated_version(
            manuscript_id, job["result"]["generated_version_id"]
        )
        assert {a["artifact_kind"] for a in version["artifacts"]} == {
            "MARKDOWN",
            "GENERATED_JSON",
            "TEX",
            "BIB",
            "PDF",
        }
        with sqlite3.connect(service.db_path) as conn:
            artifacts = conn.execute(
                "SELECT artifact_kind,storage_path FROM studio_artifacts WHERE job_id=?",
                (job["job_id"],),
            ).fetchall()
            recorded = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT input_json FROM studio_model_calls WHERE job_id=? ORDER BY started_at,rowid",
                    (job["job_id"],),
                )
            ]
        generated_path = next(
            Path(path) for kind, path in artifacts if kind == "GENERATED_JSON"
        )
        generated = json.loads(generated_path.read_text(encoding="utf-8"))
        assert generated["author_source_sections"] == [
            s for s in mapped["sections"] if s.get("placement_status") == "UNPLACED"
        ]
        assert [
            context
            for s in generated["sections"]
            for p in s["paragraphs"]
            for context in p["author_contexts"]
        ] == contexts
        assert [
            f
            for s in generated["sections"]
            for p in s["paragraphs"]
            for f in p["formulas"]
        ] == [f for p in originals for f in p.get("formulas", [])]
        assert [
            a
            for s in generated["sections"]
            for p in s["paragraphs"]
            for a in p["asset_ids"]
        ] == list(dict.fromkeys(a for p in originals for a in p["asset_ids"]))
        assert all(
            call["author_contexts"] == original["author_contexts"]
            for call, original in zip(recorded, captured, strict=True)
        )
        assert {ref["evidence_id"] for ref in version["references"]} == {
            c["evidence_id"]
            for t in expected_thoughts
            for c in t["citations"]
            if c["selected"]
        }
        assert (
            StudioService(tmp_path).get_workspace(manuscript_id)["document"] == mapped
        )
        assert service.get_document_revision(manuscript_id, 3)["document"] == adopted
    finally:
        service._executor.shutdown(wait=True)


def test_correspondence_comments_keep_original_and_target_ids_through_compensation(
    tmp_path,
):
    service, manuscript_id, adopted, mapped, originals, slots = mapped_fixture(tmp_path)
    round_row = service.create_review_round(
        manuscript_id, round_number=1, venue="Software fixture"
    )
    comment = service.import_comments(
        round_row["review_round_id"],
        [{"text": "Keep the original and chosen slot linked.", "include": True}],
        source="PASTED",
    )[0]
    comment_id = comment["comment_id"]
    for revision, kind, value in [
        (3, "MAP_AUTHOR_INTENT", mapped),
        (4, "UNDO", adopted),
        (5, "REDO", mapped),
    ]:
        service.save_document(
            manuscript_id,
            base_revision=revision,
            operation_id=f"comment-{kind}",
            operation_kind=kind,
            document=value,
            comment_ids=[comment_id],
        )
    linked = service.list_comments(manuscript_id)[0]
    assert linked["comment_id"] == comment_id
    assert {change["operation_id"] for change in linked["changes"]} == {
        "comment-MAP_AUTHOR_INTENT",
        "comment-UNDO",
        "comment-REDO",
    }
    expected = {i["id"] for p in originals + slots for i in p["intents"]} | {
        originals[0]["id"]
    }
    assert all(
        expected.issubset(
            service._changed_block_ids(
                json.loads(change["before_json"]), json.loads(change["after_json"])
            )
        )
        for change in linked["changes"]
    )
    service.archive_comment(comment_id)
    restored = service.archive_comment(comment_id, restore=True)
    assert restored["comment_id"] == comment_id and restored["archived_at"] is None
    assert service.list_comments(manuscript_id)[0]["changes"] == linked["changes"]


@pytest.mark.parametrize(
    "tamper",
    [
        "author_bank",
        "output_context",
        "formula",
        "asset",
        "call_context",
        "call_relation",
    ],
)
def test_mapped_generated_read_rejects_tampered_frozen_context(tmp_path, tamper):
    from test_writing_studio import wait_for_job

    from rstv4.service import RSTV4Error

    service, manuscript_id, _, mapped, _, _ = mapped_fixture(tmp_path)
    author_paragraphs = mapped["sections"][-1]["paragraphs"]
    mapped["argument_relations"] = [
        {
            "id": "mapped-context-edge",
            "source_id": author_paragraphs[0]["id"],
            "target_id": author_paragraphs[1]["intents"][0]["thoughts"][0]["id"],
            "relation": "Comparison Ω",
            "condition": "Only in the original author scope Ω",
        }
    ]
    service.save_document(
        manuscript_id, base_revision=3, operation_id="map-tamper-test", document=mapped
    )
    service.gateway.analyze = lambda task, payload: {
        "paragraph": " ".join(
            t["text"] for i in payload["intents"] for t in i["thoughts"]
        ),
        "sentence_mappings": [
            {
                "sentence": 0,
                "thought_ids": [
                    t["id"] for i in payload["intents"] for t in i["thoughts"]
                ],
            }
        ],
    }
    service._compile_artifacts = lambda job, generated: []
    try:
        job = wait_for_job(
            service, service.create_job(manuscript_id, "GENERATE", input_revision=4)
        )
        assert job["status"] == "SUCCEEDED", job
        version_id = job["result"]["generated_version_id"]
        assert service.get_generated_version(manuscript_id, version_id)
        with sqlite3.connect(service.db_path) as conn, conn:
            inputs = json.loads(
                conn.execute(
                    "SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?",
                    (version_id,),
                ).fetchone()[0]
            )
            paragraph = inputs["generated"]["sections"][0]["paragraphs"][0]
            if tamper == "author_bank":
                inputs["generated"]["author_source_sections"][0]["title"] = (
                    "Forged original"
                )
            elif tamper == "output_context":
                paragraph["author_contexts"][0]["source_paragraph"]["purpose"] = (
                    "Forged original"
                )
            elif tamper == "formula":
                paragraph["formulas"][0]["caption"] = "Forged original"
            elif tamper == "asset":
                paragraph["asset_ids"] = []
            else:
                call_id = paragraph["model_call_id"]
                request = json.loads(
                    conn.execute(
                        "SELECT input_json FROM studio_model_calls WHERE call_id=?",
                        (call_id,),
                    ).fetchone()[0]
                )
                if tamper == "call_relation":
                    request["argument_relations"][0]["condition"] = "Forged original"
                else:
                    request["author_contexts"][0]["source_group"]["label"] = (
                        "Forged original"
                    )
                raw = json.dumps(request, ensure_ascii=False)
                conn.execute(
                    "UPDATE studio_model_calls SET input_json=?,input_sha256=? WHERE call_id=?",
                    (raw, hashlib.sha256(raw.encode("utf-8")).hexdigest(), call_id),
                )
            if tamper not in {"call_context", "call_relation"}:
                conn.execute(
                    "UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?",
                    (json.dumps(inputs), version_id),
                )
        expected_guard = (
            "immutable version" if tamper == "formula" else "original author context"
        )
        with pytest.raises(RSTV4Error, match=expected_guard):
            service.get_generated_version(manuscript_id, version_id)
        assert service.get_workspace(manuscript_id)["document"] == mapped
    finally:
        service._executor.shutdown(wait=True)
