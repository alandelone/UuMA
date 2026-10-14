from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rstv4.catalog_web import create_app
from rstv4.database import initialize_catalog


def seed_catalog(root: Path) -> None:
    db_path = root / "data" / "catalog.db"
    initialize_catalog(db_path)
    papers = [
        ("p1", "solar-a", "10.1/a", "solar energy a", "Solar Energy A", "[\"Ada\"]", 2021,
         "2026-09-20"),
        ("p2", "solar-b", "10.1/b", "solar energy b", "Solar Energy B", "[\"Ben\"]", 2024,
         "2026-09-22"),
        ("p3", "wind-c", None, "wind power c", "Wind Power C", "[\"Ada\"]", 2025,
         "2026-09-23"),
    ]
    pdf_path = root / "sample.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 14 Tf 30 330 Td (Solar Energy B Revised) Tj "
        b"0 -30 Td (DOI 10.1234/b) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(pdf_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT INTO papers(paper_id,canonical_key,doi,normalized_title,title,
               authors_json,published_year,abstract,landing_url,pdf_url,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)""",
            [row[:7] + ("2026-09-01", row[7]) for row in papers],
        )
        conn.execute(
            """INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("f2", "p2", hashlib.sha256(pdf_path.read_bytes()).hexdigest(), pdf_path.stat().st_size, "application/pdf",
             str(pdf_path), "LOCAL", None, "NEEDS_REVIEW",
             json.dumps({"doi_match": False, "title_token_ratio": 0.3}), "2026-09-21"),
        )


def test_research_overview_returns_track_owned_manuscripts_and_collection_jobs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "catalog.db"
    initialize_catalog(db_path)
    now = "2026-09-28T10:00:00Z"
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO research_fields VALUES(?,?,?,?,?,?)",
                     ("f1", "solar", "Solar", None, now, now))
        conn.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)",
                     ("t1", "nowcasting", "Nowcasting", None, now, now))
        conn.execute("INSERT INTO field_topics VALUES(?,?,?)", ("f1", "t1", now))
        conn.execute("""INSERT INTO research_tracks
                     (track_id,field_id,primary_topic_id,title,research_type,status,
                      mapping_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                     ("tr1", "f1", "t1", "All-sky", "EMPIRICAL", "ACTIVE", "MAPPED",
                      now, now))
        conn.execute("""INSERT INTO research_nodes
                     (node_id,track_id,node_type,status,statement,rationale,payload_json,
                      created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                     ("q1", "tr1", "research_question", "APPROVED", "Can images help?",
                      "", "{}", now, now))
        conn.execute("""INSERT INTO manuscripts
                     (manuscript_id,track_id,title,research_type,writing_status,
                      workflow_stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                     ("m1", "tr1", "Image paper", "EMPIRICAL", "DRAFT", "DRAFTING",
                      now, now))
        conn.execute("INSERT INTO manuscript_nodes VALUES(?,?,?,?)",
                     ("m1", "q1", None, 1))
        conn.execute("""INSERT INTO collections
                     (collection_id,field_id,track_id,name,scope_json,scope_version,status,
                      revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     ("c1", "f1", "tr1", "Seed papers", "{}", 1, "ACTIVE", 1, now, now))
        conn.execute("""INSERT INTO acquisition_jobs
                     (job_id,collection_id,job_type,queue_class,status,priority,
                      idempotency_key,input_json,input_digest,rule_version,available_at,
                      created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     ("j1", "c1", "FIND_PDF", "NETWORK", "READY", 1, "key-1", "{}",
                      "digest-1", "v1", now, now, now))
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/catalog/research-overview")
    assert response.status_code == 200
    data = response.json()
    assert data["fields"][0]["name"] == "Solar"
    assert data["tracks"][0]["primary_topic_id"] == "t1"
    assert data["questions"][0]["node_id"] == "q1"
    assert data["manuscripts"][0]["workflow_stage"] == "DRAFTING"
    assert data["manuscript_questions"] == [{"manuscript_id": "m1", "node_id": "q1"}]
    assert data["collection_jobs"] == [{
        "collection_id": "c1", "status": "READY", "count": 1, "latest_job_at": now,
    }]


def test_catalog_query_filters_all_rows_before_pagination_and_sorts(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/catalog/papers/query", json={
            "filter": {"type": "group", "operator": "and", "filters": [
                {"type": "group", "operator": "or", "filters": [
                    {"type": "rule", "field": "title", "operator": "contains",
                     "value": "solar"},
                    {"type": "rule", "field": "published_year", "operator": "after",
                     "value": 2024},
                ]},
                {"type": "rule", "field": "pdf_status", "operator": "is_not",
                 "value": "NO_PDF"},
            ]},
            "sorts": [{"field": "title", "direction": "desc"}],
            "page_size": 1,
        })
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert [row["paper_id"] for row in response.json()["items"]] == ["p2"]
        assert client.post("/api/catalog/papers/query", json={
            "sorts": [{"field": "authors", "direction": "asc"},
                      {"field": "title", "direction": "desc"}],
        }).json()["items"][0]["paper_id"] == "p3"


def test_catalog_review_banner_and_detail_are_real_database_views(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/catalog/summary").json() == {
            "papers": 3, "papers_with_pdf_review": 1,
            "pdf_review_cases": 1, "parser_review_cases": 0,
        }
        cases = client.get("/api/catalog/review/cases").json()
        assert [(case["kind"], case["paper_id"]) for case in cases] == [
            ("PDF_IDENTITY", "p2")
        ]
        detail = client.get("/api/catalog/papers/p2").json()
        assert detail["files"][0]["validation"]["title_token_ratio"] == 0.3
        pdf = client.get("/api/catalog/files/f2/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert client.get("/api/catalog/files/f2/pdf-info").json() == {
            "pages": 1, "page_sizes": [{"width": 300.0, "height": 400.0}]
        }
        assert client.get("/api/catalog/files/f2/pages/2.png").status_code in {404, 503}
        if shutil.which("pdftoppm"):
            preview = client.get("/api/catalog/files/f2/pages/1.png")
            assert preview.status_code == 200
            assert preview.headers["content-type"] == "image/png"
            assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")
        if shutil.which("pdftotext"):
            text_layer = client.get("/api/catalog/files/f2/pages/1/text")
            assert text_layer.status_code == 200
            assert text_layer.json()["width"] == 300
            assert any(word["text"] == "Solar" for word in text_layer.json()["words"])


def test_catalog_page_uses_browser_title_and_rejects_untrusted_filters(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "<title>Paper Catalog</title>" in page.text
        assert "RSTV4 / Library" not in page.text
        assert '<table aria-label="Paper Catalog">' in page.text
        assert 'id="view-label">研究总览</span>' in page.text
        assert 'data-view="overview">研究总览</button>' in page.text
        assert 'id="overview" aria-label="研究总览"' in page.text
        assert 'data-panel="filter"' in page.text
        assert 'data-panel="sort"' in page.text
        assert 'data-panel="columns"' in page.text
        assert 'data-view="review_queue">核对原文</button>' in page.text
        assert 'id="review" hidden aria-label="核对原文"' in page.text
        response = client.post("/api/catalog/papers/query", json={
            "filter": {"type": "rule", "field": "title; DROP TABLE papers",
                       "operator": "contains", "value": "solar"}
        })
        assert response.status_code == 422


def test_research_overview_and_collection_page_remain_discoverable(tmp_path: Path) -> None:
    initialize_catalog(tmp_path / "data" / "catalog.db")
    with TestClient(create_app(tmp_path)) as client:
        for route in ("/", "/?view=collect", "/?view=all", "/?view=review"):
            response = client.get(route)
            assert response.status_code == 200
        page = client.get("/").text
        assert 'id="overview" aria-label="研究总览"' in page
        assert 'id="overview-tree"' in page
        assert all(f'data-level="{level}"' in page for level in (
            "field", "topic", "track", "question", "paper",
        ))
        assert 'data-demo-collection="Solar Nowcasting"' in page
        assert 'id="collect" hidden aria-label="新建文献采集"' in page
        assert all(f'id="collect-{field}"' in page for field in (
            "scope", "dois", "bibtex", "queries", "check",
        ))
        assert 'id="collect-start" disabled>开始采集' in page
        assert '<script src="/catalog-collections.js"></script>' in page
        assert client.get('/catalog-collections.js').status_code == 200
        assert client.get("/api/catalog/research-overview").status_code == 200


def test_review_shows_authors_from_legacy_nested_json(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    encoded = json.dumps([json.dumps(json.dumps(["Ben", "Cory"]))])
    with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
        conn.execute("UPDATE papers SET authors_json=? WHERE paper_id='p2'", (encoded,))
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/catalog/papers/p2").json()["authors"] == ["Ben", "Cory"]
        listed = client.post("/api/catalog/papers/query", json={}).json()["items"]
        assert next(p for p in listed if p["paper_id"] == "p2")["authors"] == "Ben, Cory"


def test_parser_needs_human_case_is_visible_with_source_pdf(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
        conn.execute(
            """INSERT INTO collections(collection_id,field_id,name,scope_json,scope_version,
               status,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            ("c1", "field-1", "Review", "{}", 1, "ACTIVE", 1, "2026-09-01", "2026-09-01"),
        )
        conn.execute(
            """INSERT INTO acquisition_jobs(job_id,collection_id,paper_id,job_type,
               queue_class,status,priority,idempotency_key,input_json,input_digest,
               rule_version,available_at,last_error_detail,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("j1", "c1", "p2", "PARSE_PDF", "PARSER", "NEEDS_HUMAN", 80, "review-j1",
             '{"file_version_id":"f2"}', "digest-j1", "parser-v1", "2026-09-22",
             "Reference entries missing on page 4", "2026-09-22", "2026-09-22"),
        )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/catalog/summary").json()["parser_review_cases"] == 1
        cases = client.get("/api/catalog/review/cases").json()
        parser_case = next(case for case in cases if case["kind"] == "PARSER")
        assert parser_case["file_version_id"] == "f2"
        assert "Reference entries missing" in parser_case["detail"]


def test_human_corrections_are_saved_as_history_without_changing_catalog(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    url = "/api/catalog/review/cases/f2/findings"
    finding = {
        "submission_id": "submission-doi-1", "issue_type": "DOI",
        "assessment": "AUTO_CHECK_MISSED", "proposed_value": "10.1/b",
        "evidence_page": 1, "evidence_quote": "DOI 10.1/b",
        "note": "The DOI is visible in the original PDF.", "reviewer_label": "Reviewer A",
    }
    with TestClient(create_app(tmp_path)) as client:
        first = client.post(url, json=finding)
        assert first.status_code == 201
        assert client.post(url, json=finding).json()["finding_id"] == first.json()["finding_id"]
        revised = client.post(url, json={
            **finding, "submission_id": "submission-doi-2",
            "assessment": "CATALOG_CORRECTION", "proposed_value": "10.1/new",
        })
        assert revised.status_code == 201
        assert revised.json()["supersedes_finding_id"] == first.json()["finding_id"]
        title = client.post(url, json={
            **finding, "submission_id": "submission-title-1", "issue_type": "TITLE",
            "assessment": "CATALOG_CORRECTION", "proposed_value": "Correct solar title",
            "evidence_quote": "Correct solar title", "note": "The title differs on page 1.",
        })
        assert title.status_code == 201
        assert title.json()["supersedes_finding_id"] is None
        assert [row["issue_type"] for row in client.get(url).json()].count("TITLE") == 1
        assert client.get("/api/catalog/papers/p2").json()["doi"] == "10.1/b"
        assert client.get("/api/catalog/papers/p2").json()["title"] != "Correct solar title"
        assert client.get("/api/catalog/review/cases").json()[0]["kind"] == "PDF_IDENTITY"
        assert client.post(url, json={**finding, "submission_id": "submission-bad",
                                      "assessment": "CATALOG_CORRECTION",
                                      "proposed_value": ""}).status_code == 422
        assert client.post(url, json={**finding, "submission_id": "submission-other"},
                           headers={"Origin": "http://another-site.test"}).status_code == 403


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="Poppler text extractor unavailable")
def test_pdf_annotations_autocorrect_catalog_from_source_words(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
        conn.execute(
            """INSERT INTO paper_identities VALUES(
               'old-doi','p2','DOI','10.1/b','CONFIRMED','canonical','2026-09-01')"""
        )
    url = "/api/catalog/review/cases/f2/annotations"
    with TestClient(create_app(tmp_path)) as client:
        words = [item["text"] for item in client.get(
            "/api/catalog/files/f2/pages/1/text"
        ).json()["words"]]
        title_start = words.index("Solar")
        title_end = words.index("Revised")
        doi_index = words.index("10.1234/b")
        title = {
            "submission_id": "annotation-title-1", "field_name": "TITLE", "decision": "FOUND",
            "page_number": 1, "word_start": title_start, "word_end": title_end,
        }
        saved_title = client.post(url, json=title)
        assert saved_title.status_code == 201
        assert saved_title.json()["catalog_title"] == "Solar Energy B Revised"
        assert saved_title.json()["value_before"] == "Solar Energy B"
        doi = {
            "submission_id": "annotation-doi-1", "field_name": "DOI", "decision": "FOUND",
            "page_number": 1, "word_start": doi_index, "word_end": doi_index,
        }
        saved_doi = client.post(url, json=doi)
        assert saved_doi.status_code == 201
        assert saved_doi.json()["catalog_doi"] == "10.1234/b"
        assert client.post(url, json=doi).json()["annotation_id"] == saved_doi.json()[
            "annotation_id"
        ]
        commented = client.post(url, json={
            **doi, "submission_id": "annotation-doi-comment", "comment": "Visible on page one."
        })
        assert commented.status_code == 201
        assert commented.json()["supersedes_annotation_id"] == saved_doi.json()[
            "annotation_id"
        ]
        assert client.get("/api/catalog/papers/p2").json()["title"] == "Solar Energy B Revised"
        assert len(client.get(url).json()) == 3
        with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
            assert conn.execute(
                "SELECT canonical_key FROM papers WHERE paper_id='p2'"
            ).fetchone()[0] == "doi:10.1234/b"
            assert conn.execute(
                "SELECT status FROM paper_identities WHERE identity_id='old-doi'"
            ).fetchone()[0] == "SUPERSEDED"
            assert conn.execute(
                """SELECT status FROM paper_identities
                   WHERE normalized_value='10.1234/b'"""
            ).fetchone()[0] == "CONFIRMED"
        absent = client.post(url, json={
            "submission_id": "annotation-absent-after-doi", "field_name": "DOI",
            "decision": "ABSENT",
        })
        assert absent.status_code == 201
        assert absent.json()["catalog_doi"] == "10.1/b"
        wrong = client.post(url, json={
            "submission_id": "annotation-wrong-after-title", "field_name": "PDF",
            "decision": "WRONG_PDF",
        })
        assert wrong.status_code == 201
        assert wrong.json()["catalog_title"] == "Solar Energy B"
        latest = client.get(url).json()
        assert next(item for item in latest if item["field_name"] == "TITLE")[
            "decision"
        ] == "REVERTED"
        assert client.post(url, json={
            **title, "submission_id": "annotation-blocked-after-mismatch"
        }).status_code == 409
        reopened = client.post(url, json={
            "submission_id": "annotation-reopen-1", "field_name": "PDF",
            "decision": "REOPEN",
        })
        assert reopened.status_code == 201
        assert client.post(url, json={
            **title, "submission_id": "annotation-title-after-reopen"
        }).status_code == 201
    with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
        assert conn.execute(
            "SELECT canonical_key FROM papers WHERE paper_id='p2'"
        ).fetchone()[0] == "solar-b"
        assert conn.execute(
            "SELECT status FROM paper_identities WHERE identity_id='old-doi'"
        ).fetchone()[0] == "CONFIRMED"


def test_pdf_review_decisions_autosave_without_inventing_metadata(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    url = "/api/catalog/review/cases/f2/annotations"
    with TestClient(create_app(tmp_path)) as client:
        absent = client.post(url, json={
            "submission_id": "annotation-absent-1", "field_name": "DOI", "decision": "ABSENT"
        })
        wrong = client.post(url, json={
            "submission_id": "annotation-wrong-1", "field_name": "PDF", "decision": "WRONG_PDF"
        })
        assert absent.status_code == 201
        assert wrong.status_code == 201
        assert client.get("/api/catalog/papers/p2").json()["doi"] == "10.1/b"
        assert client.post(url, json={
            "submission_id": "annotation-bad-1", "field_name": "TITLE", "decision": "ABSENT"
        }).status_code == 422
        assert client.post(url, json={
            "submission_id": "annotation-cross-origin", "field_name": "DOI",
            "decision": "ABSENT"
        }, headers={"Origin": "http://other.test"}).status_code == 403


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="Poppler text extractor unavailable")
def test_pdf_doi_collision_does_not_mutate_either_paper(tmp_path: Path) -> None:
    seed_catalog(tmp_path)
    with sqlite3.connect(tmp_path / "data" / "catalog.db") as conn:
        conn.execute("UPDATE papers SET doi='10.1234/b',canonical_key='doi:10.1234/b' WHERE paper_id='p1'")
    url = "/api/catalog/review/cases/f2/annotations"
    with TestClient(create_app(tmp_path)) as client:
        words = [item["text"] for item in client.get(
            "/api/catalog/files/f2/pages/1/text"
        ).json()["words"]]
        index = words.index("10.1234/b")
        response = client.post(url, json={
            "submission_id": "annotation-collision", "field_name": "DOI", "decision": "FOUND",
            "page_number": 1, "word_start": index, "word_end": index,
        })
        assert response.status_code == 409
        assert client.get("/api/catalog/papers/p2").json()["doi"] == "10.1/b"
        assert client.get(url).json() == []
