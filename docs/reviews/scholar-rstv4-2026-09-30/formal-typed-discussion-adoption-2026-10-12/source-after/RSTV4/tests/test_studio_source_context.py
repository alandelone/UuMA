"""Exact software source provenance; these fixtures approve no scientific claims."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_acquisition_deep_read import setup
from test_writing_studio import complete_document, create_studio, wait_for_job

from rstv4.database import transaction
from rstv4.models import TrackFirstEvidenceInput
from rstv4.research_views import skeleton_source
from rstv4.service import RSTV4Error
from rstv4.studio_api import create_app


def source_studio(root: Path, *, compile_pdf=False):
    acquisition, collection_id, db, pdf = setup(root)
    blocks = []
    original_pdf = PdfWriter()
    for index in range(3):
        heading, text = f"Software source section {index + 1}", f"Original software source body {index + 1}."
        page = original_pdf.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): original_pdf._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 740 Td ({heading}) Tj 0 -30 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = original_pdf._add_object(stream)
        blocks.extend([
            {"text": heading, "block_type": "HEADING", "page_number": index + 1,
             "section": heading, "location": {"heading_level": 1, "bbox": [72, 90, 420, 110]}},
            {"text": text, "block_type": "TEXT", "page_number": index + 1,
             "section": heading, "location": {"bbox": [72, 120, 420, 140]}},
        ])
    original_pdf.write(str(pdf))
    with transaction(db) as conn:
        conn.execute("UPDATE source_file_versions SET sha256=?,size_bytes=? WHERE file_version_id='existing-file'",
                     (hashlib.sha256(pdf.read_bytes()).hexdigest(), pdf.stat().st_size))
    parsed = acquisition.publish_parse_result(
        collection_id, "existing", "existing-file", parser_name="TEST_FIXTURE_SOURCE",
        parser_version="1", config={}, manifest={"software_only": True}, blocks=blocks, references=[],
    )
    with transaction(db) as conn:
        units = [{"block_id": row["block_id"], "page_number": row["page_number"],
                  "section": row["section"], "raw_text": row["text"],
                  "layer1": {"triplets": []}, "layer2": {}, "layer3": {"intent": "Software_Test"},
                  "layer4": {"role": "Software_Test"}}
                 for row in conn.execute("SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence",
                                         (parsed["parse_run_id"],)) if row["block_type"] == "TEXT"]
    published = acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE_SOURCE")
    with transaction(db) as conn:
        source = skeleton_source(conn, published["skeleton_id"])
    service, track_id, manuscript_id = create_studio(root)
    evidence = []
    for unit in source["units"][:2]:
        evidence.append(service.track_service.add_evidence(TrackFirstEvidenceInput(
            track_id=track_id, paper_id="existing", statement=unit["raw_text"], excerpt=unit["raw_text"],
            location="Explicit software source", location_data={
                "skeleton_id": source["skeleton_id"], "skeleton_digest": source["content_digest"],
                "unit_id": unit["unit_id"], "unit_digest": unit["content_digest"],
                "page": unit["page_idx"], "section": unit["section"], "sequence": unit["seq_idx"],
            }, confidence=0.8, relation="SUPPORTS", extractor_model="TEST_FIXTURE_SOURCE", prompt_version="1",
        )))
    document = complete_document(service.get_workspace(manuscript_id))
    document["title"] = "Fixed citation source - software acceptance"
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought.update(text="Check original sources only; no scientific claim is asserted.", citation_mode="SELECTED",
                   citations=[{"evidence_id": row["evidence_id"], "selected": True} for row in evidence])
    service.save_document(manuscript_id, base_revision=0, operation_id="fixed-source-initial", document=document)
    service.gateway.analyze = lambda task, payload: {
        "paragraph": f"First source [@{evidence[1]['evidence_id']}]. Next [@{evidence[0]['evidence_id']}]. Repeat [@{evidence[1]['evidence_id']}].",
        "sentence_mappings": [{"sentence": 0, "thought_ids": [thought["id"]]}],
        "_contract": {"actual_model": "TEST_FIXTURE_SOURCE", "task": task},
    }
    if not compile_pdf:
        service._compile_artifacts = lambda job, generated: []
    return service, manuscript_id, evidence, source, pdf, document


def generate(service, manuscript_id):
    revision = service.get_workspace(manuscript_id)["document_revision"]
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=revision))
    assert job["status"] == "SUCCEEDED", job
    return service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])


def test_original_context_and_pdf_survive_metadata_refresh_and_regeneration(tmp_path):
    service, ms, evidence, source, pdf, document = source_studio(tmp_path)
    first = generate(service, ms)
    context = first["references"][0]["source_context"]
    assert context["unit"]["raw_text"] == evidence[1]["excerpt"]
    assert [u["raw_text"] for u in context["units"]] == [u["raw_text"] for u in source["units"]]
    assert context["parse_run_id"] == source["parse_run_id"]
    assert context["file_version"]["sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert len(context["parsed_blocks"]) == 6
    assert "storage_path" not in json.dumps(context)
    calls = service.list_model_calls(ms)
    assert len(calls) == 1
    assert "Original software source body 3." not in json.dumps(calls[0]["input"])
    assert calls[0]["input"]["selected_evidence"][1]["source_context"]["context_sha256"] == context["context_sha256"]
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE papers SET title='Refreshed live title' WHERE paper_id='existing'")
        conn.execute("UPDATE evidence SET statement='Refreshed live statement' WHERE evidence_id=?", (evidence[1]["evidence_id"],))
    document = deepcopy(document)
    document["sections"][0]["paragraphs"][0]["purpose"] = "A different author purpose"
    service.save_document(ms, base_revision=1, operation_id="fixed-source-regenerate", document=document)
    second = generate(service, ms)
    assert second["generated_version_id"] != first["generated_version_id"]
    assert second["references"][0]["title"] == "Refreshed live title"
    assert service.get_generated_version(ms, first["generated_version_id"]) == first
    assert first["blocks"][-1]["display_text"] == "First source [1]. Next [2]. Repeat [1]."
    assert service.generated_source_content(ms, first["generated_version_id"], evidence[1]["evidence_id"]) == pdf.read_bytes()


@pytest.mark.parametrize("defect", ["paper", "skeleton", "unit", "excerpt", "page", "unit_digest", "skeleton_digest"])
def test_explicit_foreign_or_changed_source_rejects_before_model_execution(tmp_path, defect):
    service, ms, evidence, _source, _pdf, _document = source_studio(tmp_path)
    with transaction(service.db_path) as conn:
        if defect == "paper":
            conn.execute("UPDATE evidence SET paper_id='other' WHERE evidence_id=?", (evidence[0]["evidence_id"],))
        elif defect == "excerpt":
            conn.execute("UPDATE evidence SET excerpt='Invented original text' WHERE evidence_id=?", (evidence[0]["evidence_id"],))
        else:
            location = json.loads(evidence[0]["location_json"])
            key = {"skeleton": "skeleton_id", "unit": "unit_id"}.get(defect, defect)
            location[key] = 999 if defect == "page" else "foreign-or-changed"
            conn.execute("UPDATE evidence SET location_json=? WHERE evidence_id=?", (json.dumps(location), evidence[0]["evidence_id"]))
    calls = []
    service.gateway.analyze = lambda *args: calls.append(args)
    job = wait_for_job(service, service.create_job(ms, "GENERATE", input_revision=1))
    assert job["status"] == "FAILED", job
    assert calls == []
    assert service.get_workspace(ms)["active_generated_version_id"] is None


def test_fixed_pdf_route_rejects_foreign_reference_and_changed_original_bytes(tmp_path):
    service, ms, evidence, _source, pdf, _document = source_studio(tmp_path)
    first = generate(service, ms)
    route = f"/api/manuscripts/{ms}/generated-versions/{first['generated_version_id']}/sources/{evidence[1]['evidence_id']}/pdf"
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(route)
        assert response.status_code == 200 and response.content == pdf.read_bytes()
        assert client.get(route.replace(evidence[1]["evidence_id"], "foreign-reference")).status_code == 404
        pdf.write_bytes(b"%PDF-1.4 changed original")
        response = client.get(route)
        assert response.status_code == 422 and "integrity" in response.json()["detail"]
        assert service.get_generated_version(ms, first["generated_version_id"]) == first


def test_generated_reference_cannot_override_original_validated_source_snapshot(tmp_path):
    service, ms, _evidence, _source, _pdf, _document = source_studio(tmp_path)
    first = generate(service, ms)
    with transaction(service.db_path) as conn:
        row = conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?", (first["generated_version_id"],)).fetchone()
        inputs = json.loads(row[0])
        inputs["generated"]["references"][0]["source_context"]["unit"]["raw_text"] = "Invented historical source"
        conn.execute("UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?", (json.dumps(inputs), first["generated_version_id"]))
    with pytest.raises(RSTV4Error, match="source snapshot"):
        service.get_generated_version(ms, first["generated_version_id"])


def test_unknown_source_provenance_remains_explicit_without_latest_source_guess(tmp_path):
    service, ms, evidence, _source, _pdf, _document = source_studio(tmp_path)
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE evidence SET location_json='{}' WHERE evidence_id=?", (evidence[1]["evidence_id"],))
    first = generate(service, ms)
    assert first["references"][0]["source_context"]["available"] is False
    assert "provenance" in first["references"][0]["source_context"]["reason"]
    with pytest.raises(RSTV4Error, match="unavailable"):
        service.generated_source_content(ms, first["generated_version_id"], evidence[1]["evidence_id"])
