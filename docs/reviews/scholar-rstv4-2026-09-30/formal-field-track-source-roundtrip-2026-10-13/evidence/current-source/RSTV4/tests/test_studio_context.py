from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from rstv4.database import transaction
from rstv4.models import TrackFirstEvidenceInput
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from rstv4.studio_context import legacy_bibliography
from test_writing_studio import complete_document, create_studio, wait_for_job


def generated_fixture(service: StudioService, manuscript_id: str, *, compile_pdf=False):
    document = complete_document(service.get_workspace(manuscript_id))
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought["text"] = "Original 😀 author thought."
    service.save_document(manuscript_id, base_revision=0, operation_id="context-first", document=document)
    service.gateway.analyze = lambda task, payload: {
        "paragraph": "Original 😀 generated paragraph.",
        "sentence_mappings": [{"sentence": 0, "thought_ids": [thought["id"]]}],
    }
    if not compile_pdf:
        service._compile_artifacts = lambda job, generated: []
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job
    return service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])


def test_generated_and_structure_discussions_return_original_version_after_deletion(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    generated = generated_fixture(service, manuscript_id)
    block = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    with TestClient(create_app(tmp_path)) as client:
        calls = []
        client.app.state.studio.gateway.analyze = lambda task, payload: (
            calls.append(payload) or {"answer": "An unapplied suggestion."}
        )
        endpoint = f"/api/manuscripts/{manuscript_id}"
        first = client.post(f"{endpoint}/chat", json={
            "content": "Discuss this exact selection", "anchor_type": "generated_paragraph",
            "anchor_id": block["anchor_id"], "anchor_revision": 1,
            "quote": {"generated_version_id": generated["generated_version_id"],
                      "text": "😀", "start": 9, "end": 11, "offset_unit": "utf16",
                      "annotation": "Keep the author meaning."},
        })
        assert first.status_code == 201, first.text
        messages = first.json()
        assert messages["agent"]["quoted"] == {**messages["author"]["quoted"], "evidence_ids": []}
        assert messages["agent"]["quoted"]["text"] == "😀"
        assert calls[0]["document"] == service.get_document_revision(manuscript_id, 1)["document"]
        assert calls[0]["generated_version"]["generated_version_id"] == generated["generated_version_id"]
        structure = client.post(f"{endpoint}/chat", json={
            "content": "Discuss the original thought", "anchor_type": "thought",
            "anchor_id": "thought_author_1", "anchor_revision": 1,
        })
        assert structure.status_code == 201, structure.text
        # A sibling inserted before this paragraph and a new generated version
        # must keep the original discussion on its original immutable paragraph.
        reordered = deepcopy(service.get_workspace(manuscript_id)["document"])
        original_paragraph = reordered["sections"][0]["paragraphs"][0]
        sibling = deepcopy(original_paragraph)
        sibling["id"] = "new-sibling"
        sibling["intents"][0]["id"] = "new-intent"
        sibling["intents"][0]["thoughts"][0]["id"] = "new-thought"
        sibling["intents"][0]["thoughts"][0]["text"] = "A new sibling paragraph."
        original_paragraph["intents"][0]["thoughts"][0]["text"] = "A changed original paragraph."
        reordered["sections"][0]["paragraphs"].insert(0, sibling)
        service.save_document(manuscript_id, base_revision=1, operation_id="context-reorder", document=reordered)
        service.gateway.analyze = lambda task, payload: {
            "paragraph": payload["intents"][0]["thoughts"][0]["text"],
            "sentence_mappings": [{"sentence": 0, "thought_ids": [payload["intents"][0]["thoughts"][0]["id"]]}],
        }
        job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=2))
        assert job["status"] == "SUCCEEDED", job
        latest = service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])
        latest_paragraphs = [item for item in latest["blocks"] if item["kind"] == "paragraph"]
        assert [item["object_id"] for item in latest_paragraphs] == ["new-sibling", block["object_id"]]
        assert latest_paragraphs[1]["anchor_id"] != block["anchor_id"]
        # Deletion also never retargets the previous discussion to its neighbor.
        changed = deepcopy(service.get_workspace(manuscript_id)["document"])
        changed["sections"] = []
        service.save_document(manuscript_id, base_revision=2, operation_id="context-delete", document=changed)
        for message in [messages["author"], messages["agent"], structure.json()["author"]]:
            context = client.get(f"{endpoint}/chat/{message['message_id']}/context")
            assert context.status_code == 200, context.text
            original = context.json()
            assert original["quote"]["source"]["anchor_revision"] == 1
            assert "Original 😀" in original["quote"]["object_text"]
        assert client.get(f"{endpoint}/generated-versions/{generated['generated_version_id']}").json() == generated
        assert client.get(f"{endpoint}/document-revisions/0").json()["document"]["sections"]
        assert service.get_workspace(manuscript_id)["document_revision"] == 3
        assert service.get_workspace(manuscript_id)["document"] == changed


@pytest.mark.parametrize("wrong", ["range", "text", "object", "revision", "surrogate", "version"])
def test_invalid_quote_or_generated_anchor_is_atomic(tmp_path: Path, wrong: str):
    service, _, manuscript_id = create_studio(tmp_path)
    generated = generated_fixture(service, manuscript_id)
    block = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    request = {
        "content": "This must not enter history", "anchor_type": "generated_paragraph",
        "anchor_id": block["anchor_id"], "anchor_revision": 1,
        "quote": {"generated_version_id": generated["generated_version_id"],
                  "text": "😀", "start": 9, "end": 11, "offset_unit": "utf16"},
    }
    if wrong == "range":
        request["quote"]["end"] = 10000
    elif wrong == "text":
        request["quote"]["text"] = "Changed"
    elif wrong == "object":
        request["anchor_id"] = "neighbor-paragraph"
    elif wrong == "revision":
        request["anchor_revision"] = 2
    elif wrong == "surrogate":
        request["quote"]["end"] = 10
    else:
        other = service.create_manuscript(service.get_workspace(manuscript_id)["manuscript"]["track_id"], "Other")
        request["quote"]["generated_version_id"] = other["manuscript"]["manuscript_id"]
    with TestClient(create_app(tmp_path)) as client:
        def forbidden(*args, **kwargs):
            raise AssertionError("Invalid anchor must fail before invoking a model")
        client.app.state.studio.gateway.analyze = forbidden
        rejected = client.post(f"/api/manuscripts/{manuscript_id}/chat", json=request)
        assert rejected.status_code in {404, 422}, rejected.text
        assert service.list_chat(manuscript_id) == []


def test_agent_failure_preserves_exact_author_quote_without_document_change(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    generated = generated_fixture(service, manuscript_id)
    before = service.get_workspace(manuscript_id)["document"]
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.studio.gateway.analyze = lambda task, payload: {}
        response = client.post(f"/api/manuscripts/{manuscript_id}/chat", json={
            "content": "Unsent annotations must remain anchored", "anchor_type": "paper",
            "anchor_id": None, "anchor_revision": 1, "quote": {"annotation": "Author note"},
        })
        assert response.status_code == 422
        rows = service.list_chat(manuscript_id)
        assert len(rows) == 1
        assert rows[0]["status"] == "AGENT_FAILED"
        assert rows[0]["quoted"]["annotation"] == "Author note"
        assert service.get_workspace(manuscript_id)["document"] == before
        assert service.get_generated_version(manuscript_id, generated["generated_version_id"]) == generated


def test_real_numeric_citations_freeze_sources_and_preserve_underscore_keys(tmp_path: Path):
    service, track_id, manuscript_id = create_studio(tmp_path)
    evidence = [service.track_service.add_evidence(TrackFirstEvidenceInput(
        track_id=track_id, paper_id=f"run:test-{index}", statement=f"Frozen source {index}",
        excerpt=f"Original excerpt {index}", location="page 1", confidence=0.8,
        relation="SUPPORTS", extractor_model="TEST_FIXTURE", prompt_version="TEST_FIXTURE",
    )) for index in [1, 2]]
    document = complete_document(service.get_workspace(manuscript_id))
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought["citation_mode"] = "SELECTED"
    thought["citations"] = [{"evidence_id": row["evidence_id"], "selected": True} for row in evidence]
    service.save_document(manuscript_id, base_revision=0, operation_id="numeric-source", document=document)
    service.gateway.analyze = lambda task, payload: {
        "paragraph": f"First source [@{evidence[1]['evidence_id']}]. Next [@{evidence[0]['evidence_id']}]. Repeat [@{evidence[1]['evidence_id']}].",
        "sentence_mappings": [{"sentence": 0, "thought_ids": [thought["id"]]}],
    }
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job
    version_id = job["result"]["generated_version_id"]
    generated = service.get_generated_version(manuscript_id, version_id)
    assert generated["citation_style"] == "numeric_first_use"
    assert [item["evidence_id"] for item in generated["references"]] == [evidence[1]["evidence_id"], evidence[0]["evidence_id"]]
    paragraph = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    assert paragraph["display_text"] == "First source [1]. Next [2]. Repeat [1]."
    artifacts = {item["artifact_kind"]: item for item in service.get_workspace(manuscript_id)["artifacts"]}
    assert {item["artifact_id"] for item in generated["artifacts"]} == {item["artifact_id"] for item in artifacts.values()}
    tex = Path(artifacts["TEX"]["storage_path"]).read_text(encoding="utf-8")
    assert rf"\citep{{{evidence[1]['evidence_id']}}}" in tex
    assert r"\bibliographystyle{unsrtnat}" in tex
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(artifacts["PDF"]["storage_path"]).pages)
    assert "[1]" in pdf_text and "[2]" in pdf_text
    assert "Frozen source 1" in pdf_text and "Frozen source 2" in pdf_text
    # Historical reads must not depend on mutable live evidence or artifact bytes.
    service._evidence_by_ids = lambda ids: (_ for _ in ()).throw(AssertionError("Live metadata read"))
    Path(artifacts["GENERATED_JSON"]["storage_path"]).write_text("tampered", encoding="utf-8")
    assert service.get_generated_version(manuscript_id, version_id) == generated
    # Legacy versions use the actual registered artifact and fail on tampering.
    with transaction(service.db_path) as conn:
        row = conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?", (version_id,)).fetchone()
        inputs = json.loads(row[0])
        inputs.pop("generated")
        conn.execute("UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?", (json.dumps(inputs), version_id))
    with TestClient(create_app(tmp_path)) as client:
        artifact = client.get(f"/api/artifacts/{artifacts['GENERATED_JSON']['artifact_id']}")
        assert artifact.status_code == 410
        rejected = client.get(f"/api/manuscripts/{manuscript_id}/generated-versions/{version_id}")
        assert rejected.status_code == 422
        assert "integrity" in rejected.json()["detail"]
    # Read the genuine old-format mapping plus original BibTeX, never current sources.
    legacy = inputs.copy()
    original_generated = {
        "title": document["title"], "abstract": document["abstract"], "input_revision": 1,
        "sections": [{"section_id": document["sections"][0]["id"],
                      "title": document["sections"][0]["title"],
                      "paragraphs": [{"paragraph_id": paragraph["object_id"],
                                      "text": paragraph["text"], "thought_ids": [thought["id"]],
                                      "formulas": []}]}],
    }
    old_bytes = json.dumps(original_generated).encode()
    Path(artifacts["GENERATED_JSON"]["storage_path"]).write_bytes(old_bytes)
    import hashlib
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE studio_artifacts SET sha256=?,size_bytes=? WHERE artifact_id=?",
                     (hashlib.sha256(old_bytes).hexdigest(), len(old_bytes), artifacts["GENERATED_JSON"]["artifact_id"]))
        assert json.loads(conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?", (version_id,)).fetchone()[0]) == legacy
    original_view = service.get_generated_version(manuscript_id, version_id)
    assert original_view["structure_mapping_available"] is True
    assert original_view["citation_style"] == "legacy"
    assert original_view["blocks"] == generated["blocks"]
    assert [item["title"] for item in original_view["references"]] == ["Frozen source 2", "Frozen source 1"]
    assert all(item["reference_snapshot_source"] == "verified_bib_artifact" for item in original_view["references"])
    # UTF-16 selection is checked against the numbered reading text, not raw citation keys.
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.studio.gateway.analyze = lambda task, payload: {"answer": "A suggestion only"}
        discussed = client.post(f"/api/manuscripts/{manuscript_id}/chat", json={
            "content": "Discuss the citation position", "anchor_type": "generated_paragraph",
            "anchor_id": paragraph["anchor_id"], "anchor_revision": 1,
            "quote": {"generated_version_id": version_id, "text": "[1]", "start": 13,
                      "end": 16, "offset_unit": "utf16"},
        })
        assert discussed.status_code == 201, discussed.text
        assert discussed.json()["author"]["quoted"]["object_text"] == paragraph["display_text"]
        assert discussed.json()["author"]["quoted"]["raw_object_text"] == paragraph["text"]


def test_cross_field_source_cannot_be_realized_or_promoted(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path / "one")
    # A second field/track in the same catalog is outside this manuscript's source pane.
    from rstv4.models import FieldInput, TrackFirstTopicInput, TrackFirstTrackInput
    field = service.track_service.create_field(FieldInput(name="Unrelated field"))
    topic = service.track_service.create_topic(TrackFirstTopicInput(field_id=field["field_id"], name="Other"))
    track = service.track_service.create_track(TrackFirstTrackInput(
        field_id=field["field_id"], primary_topic_id=topic["topic_id"], title="Other track",
        research_type="conceptual_framework",
    ))
    evidence = service.track_service.add_evidence(TrackFirstEvidenceInput(
        track_id=track["track_id"], paper_id="run:other", statement="Outside source",
        excerpt="Outside original text", location="page 1", confidence=0.8,
        relation="SUPPORTS", extractor_model="TEST_FIXTURE", prompt_version="TEST_FIXTURE",
    ))
    document = complete_document(service.get_workspace(manuscript_id))
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought.update(citation_mode="SELECTED", citations=[{"evidence_id": evidence["evidence_id"], "selected": True}])
    service.save_document(manuscript_id, base_revision=0, operation_id="wrong-source", document=document)
    def forbidden(*args, **kwargs):
        raise AssertionError("Out-of-scope evidence must fail before realization")
    service.gateway.analyze = forbidden
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "FAILED"
    assert "outside" in job["error"]["message"]
    assert service.search_sources(manuscript_id, evidence["evidence_id"]) == []
    assert service.get_workspace(manuscript_id)["active_generated_version_id"] is None


def test_legacy_bibtex_decodes_only_the_original_compiler_metadata():
    evidence = [{"evidence_id": "evidence_source_1", "title": "A {literal} & under_score",
                 "authors": ["First Author", "Second Author"], "published_year": 2020,
                 "doi": "10.1234/test_1"}]
    original = legacy_bibliography(StudioService._bibtex(evidence))["evidence_source_1"]
    assert original["title"] == evidence[0]["title"]
    assert original["published_year"] == 2020
    assert original["doi"] == evidence[0]["doi"]
