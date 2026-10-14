"""Current Evidence reads bind exact originals without manuscript/model writes."""
import json

import pytest
from fastapi.testclient import TestClient
from rstv4.database import transaction
from rstv4.models import FieldInput
from rstv4.service import RSTV4Error
from rstv4.studio_api import create_app
from test_studio_source_context import source_studio


def test_live_source_reader_full_original_pdf_and_no_writes(tmp_path):
    service, ms, evidence, source, pdf, _document = source_studio(tmp_path)
    eid = evidence[1]["evidence_id"]
    before = service.db_path.read_bytes()
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(f"/api/manuscripts/{ms}/sources/{eid}")
        assert response.status_code == 200, response.text
        detail = response.json()
        context = detail["source_context"]
        assert context["unit"]["raw_text"] == evidence[1]["excerpt"]
        assert context["unit"]["page_idx"] == 2
        assert context["units"] == source["units"]
        assert len(context["parsed_blocks"]) == 6
        assert context["skeleton_id"] == source["skeleton_id"]
        assert context["parse_run_id"] == source["parse_run_id"]
        assert context["file_version_id"] == source["file_version_id"]
        assert "storage_path" not in json.dumps(detail)
        route = f"/api/manuscripts/{ms}/sources/{eid}/pdf"
        opened = client.get(route, params={"context_sha256": context["context_sha256"]})
        assert opened.status_code == 200 and opened.content == pdf.read_bytes()
        assert opened.headers["cache-control"] == "no-store"
        fixed_path = f"/api/manuscripts/{ms}/sources/{eid}/contexts/{context['context_sha256']}/pdf"
        assert client.get(fixed_path).content == pdf.read_bytes()
        assert client.get(route, params={"context_sha256": "foreign-context"}).status_code == 409
        assert client.get(route).status_code == 422
    assert service.db_path.read_bytes() == before


def test_live_source_reader_enforces_manuscript_field_scope(tmp_path):
    service, ms, evidence, _source, _pdf, _document = source_studio(tmp_path)
    field = service.track_service.create_field(FieldInput(name="Unrelated reader scope"))
    eid = evidence[0]["evidence_id"]
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE evidence SET scope_kind='FIELDKG',field_id=?,track_id=NULL WHERE evidence_id=?",
                     (field["field_id"], eid))
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/manuscripts/{ms}/sources/{eid}").status_code == 404
        assert client.get(f"/api/manuscripts/{ms}/sources/{eid}/pdf",
                          params={"context_sha256": "anything"}).status_code == 404
        assert client.get(f"/api/manuscripts/foreign-manuscript/sources/{evidence[1]['evidence_id']}").status_code == 404


@pytest.mark.parametrize("defect", ["skeleton_id", "unit_id", "unit_digest", "skeleton_digest", "page", "excerpt"])
def test_live_reader_rejects_changed_original_identity(tmp_path, defect):
    service, ms, evidence, _source, _pdf, _document = source_studio(tmp_path)
    eid = evidence[0]["evidence_id"]
    with transaction(service.db_path) as conn:
        if defect == "excerpt":
            conn.execute("UPDATE evidence SET excerpt='Invented source' WHERE evidence_id=?", (eid,))
        else:
            location = json.loads(evidence[0]["location_json"])
            location[defect] = 999 if defect == "page" else "changed-source"
            conn.execute("UPDATE evidence SET location_json=? WHERE evidence_id=?", (json.dumps(location), eid))
    with pytest.raises(RSTV4Error, match="source"):
        service.get_source(ms, eid)


def test_live_reader_missing_provenance_and_changed_pdf_are_not_latest_fallbacks(tmp_path):
    service, ms, evidence, _source, pdf, _document = source_studio(tmp_path)
    eid = evidence[0]["evidence_id"]
    original = service.get_source(ms, eid)
    pdf.write_bytes(b"%PDF-1.4 changed source")
    with pytest.raises(RSTV4Error, match="changed|integrity"):
        service.source_content(ms, eid, context_sha256=original["source_context"]["context_sha256"])
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE evidence SET location_json='{}' WHERE evidence_id=?", (eid,))
    unavailable = service.get_source(ms, eid)["source_context"]
    assert unavailable["available"] is False and "provenance" in unavailable["reason"]
    with pytest.raises(RSTV4Error, match="unavailable"):
        service.source_content(ms, eid, context_sha256="unknown")
