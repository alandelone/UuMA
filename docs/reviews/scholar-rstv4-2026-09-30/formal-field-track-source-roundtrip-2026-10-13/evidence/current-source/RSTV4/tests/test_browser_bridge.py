from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rstv4.acquisition import browser_start_url
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.browser_bridge import BrowserBridgeServer, _safe_source_url
from rstv4.models import BrowserAcquisitionInput, CollectionCreateInput, FieldInput
from rstv4.sources import ProviderResult
from rstv4.track_first import TrackFirstService


def _paper_request(root: Path) -> tuple[TrackFirstService, str, str]:
    service = TrackFirstService(root)
    field = service.create_field(FieldInput(name="Browser bridge test field"))
    collection = service.paperpool.create_collection(CollectionCreateInput(
        field_id=field["field_id"], name="Browser bridge test",
        dois=["10.1000/browser"], idempotency_key="browser-bridge-collection",
    ))
    paper = service.paperpool.resolve_seed(collection["seeds"][0]["seed_id"], {
        "doi": "10.1000/browser", "title": "Browser Bridge Paper",
    })
    return service, collection["collection_id"], paper["paper_id"]


def _request(
    server: BrowserBridgeServer, path: str, *, token: str | None,
    payload: dict | None = None, origin: str = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
) -> dict:
    headers = {"Origin": origin}
    if token is not None:
        headers["X-RSTV4-Bridge-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _compressed_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        }),
    })
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 72 720 Td (Browser Bridge Paper) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(contents.flate_encode())
    with path.open("wb") as stream:
        writer.write(stream)


def test_browser_source_url_excludes_private_and_signed_locations() -> None:
    assert _safe_source_url("https://reader.elsevier.com/reader/sd/pii/123?token=secret") == (
        "https://reader.elsevier.com/reader/sd/pii/123"
    )
    assert _safe_source_url(
        "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=9364540&token=secret"
    ) == "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=9364540"
    assert _safe_source_url(
        "https://pdf.sciencedirectassets.com/271459/1-s2.0-S0038092X23X00048/"
        "1-s2.0-S0038092X23000683/main.pdf?X-Amz-Security-Token=secret"
    ) == (
        "https://pdf.sciencedirectassets.com/271459/1-s2.0-S0038092X23X00048/"
        "1-s2.0-S0038092X23000683/main.pdf"
    )
    assert _safe_source_url("http://127.0.0.1:8000/private.pdf") is None
    assert _safe_source_url("https://user:password@www.mdpi.com/a/pdf") is None
    assert _safe_source_url("https://unrelated.example/a.pdf") is None


def test_browser_start_url_accepts_only_supported_article_pages(tmp_path: Path) -> None:
    service, collection_id, paper_id = _paper_request(tmp_path)
    urls = [
        "https://ieeexplore.ieee.org/abstract/document/9364540",
        "https://www.mdpi.com/1996-1073/15/17/6100",
        "https://www.sciencedirect.com/science/article/pii/S0038092X23000683",
    ]
    for index, url in enumerate(urls):
        assert browser_start_url(url) == url
        request = service.paperpool.request_browser_acquisition(
            collection_id, BrowserAcquisitionInput(
                paper_id=paper_id, idempotency_key=f"direct-page-{index}", start_url=url,
            ),
        )
        assert json.loads(request["expected_identity_json"])["start_url"] == url
    for unsafe in ("http://127.0.0.1/private", "https://example.com/paper",
                   "https://www.mdpi.com/1996-1073/15/17/6100?token=secret"):
        assert browser_start_url(unsafe) is None


def test_network_fallback_is_claimed_and_chrome_pdf_is_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, collection_id, paper_id = _paper_request(tmp_path)
    monkeypatch.setattr(
        "rstv4.acquisition_worker.locate_open_access_pdf",
        lambda _: ProviderResult("unpaywall", [], error="No OA PDF"),
    )
    worker = AcquisitionWorker(tmp_path, "network")
    result, _ = worker._handle_locate_pdf(
        {"job_id": "locate-test", "collection_id": collection_id, "paper_id": paper_id},
        {"doi": "10.1000/browser"},
    )
    assert result["status"] == "BROWSER_QUEUED"

    downloads = tmp_path / "Downloads"
    bridge = BrowserBridgeServer(service.paperpool, port=0, download_root=downloads)
    thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as unauthenticated:
            _request(bridge, "/api/v1/next", token=None)
        assert unauthenticated.value.code == 403
        task = _request(bridge, "/api/v1/next", token=bridge.token)["task"]
        assert task["request_id"] == result["request_id"]
        assert task["expected_identity"]["start_url"] == "https://doi.org/10.1000/browser"
        assert _request(bridge, "/api/v1/next", token=bridge.token)["task"] is None

        outside = tmp_path / "unrelated.pdf"
        outside.write_bytes(b"%PDF-1.4\nBrowser Bridge Paper 10.1000/browser\n%%EOF")
        with pytest.raises(urllib.error.HTTPError) as unsafe_path:
            _request(bridge, "/api/v1/complete", token=bridge.token, payload={
                "request_id": task["request_id"], "execution_id": task["execution_id"],
                "filename": str(outside),
            })
        assert unsafe_path.value.code == 422

        assigned = downloads / "RSTV4" / task["request_id"]
        assigned.mkdir(parents=True)
        pdf = assigned / "source.pdf"
        _compressed_pdf(pdf)
        completed = _request(bridge, "/api/v1/complete", token=bridge.token, payload={
            "request_id": task["request_id"], "execution_id": task["execution_id"],
            "filename": str(pdf),
            "source_url": "https://www.mdpi.com/a/pdf?temporary_access=secret#page=1",
        })
        assert completed["result"]["registered_files"][0]["identity_status"] == "VERIFIED"
        assert completed["result"]["registered_files"][0]["evidence_source"] == (
            "pdf_text_and_raw_bytes"
        )
        canonical = Path(completed["result"]["registered_files"][0]["storage_path"])
        assert canonical.is_file()
        assert canonical.name == "source.pdf"
        assert canonical.parent.parent == service.paperpool.artifacts_root / paper_id
        assert not pdf.exists()
        with sqlite3.connect(service.paperpool.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM acquisition_jobs WHERE job_type='PARSE_PDF' AND paper_id=?",
                (paper_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT status FROM browser_acquisition_requests WHERE request_id=?",
                (task["request_id"],),
            ).fetchone()[0] == "COMPLETED"
            source_row = conn.execute(
                "SELECT source_url,acquisition_method FROM source_file_versions WHERE paper_id=?",
                (paper_id,),
            ).fetchone()
            assert source_row == ("https://www.mdpi.com/a/pdf", "chrome-network-worker")
            output_refs = conn.execute(
                "SELECT output_refs_json FROM browser_acquisition_requests WHERE request_id=?",
                (task["request_id"],),
            ).fetchone()[0]
            assert json.loads(output_refs) == [str(canonical)]
    finally:
        bridge.shutdown()
        bridge.server_close()
        thread.join(timeout=5)


def test_browser_request_pauses_and_resumes_only_with_current_execution(tmp_path: Path) -> None:
    service, collection_id, paper_id = _paper_request(tmp_path)
    worker = AcquisitionWorker(tmp_path, "network")
    queued = worker._queue_browser_acquisition(
        {"collection_id": collection_id, "paper_id": paper_id}, "test"
    )
    bridge = BrowserBridgeServer(service.paperpool, port=0, download_root=tmp_path / "Downloads")
    thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    thread.start()
    try:
        task = _request(bridge, "/api/v1/next", token=bridge.token)["task"]
        _request(bridge, "/api/v1/status", token=bridge.token, payload={
            "request_id": task["request_id"], "execution_id": task["execution_id"],
            "status": "WAITING_HUMAN", "error": {"reason": "login required"},
        })
        assert _request(bridge, "/api/v1/next", token=bridge.token)["task"] is None
        with pytest.raises(urllib.error.HTTPError) as stale:
            _request(bridge, "/api/v1/resume", token=bridge.token, payload={
                "request_id": task["request_id"], "execution_id": "wrong",
            })
        assert stale.value.code == 422
        resumed = _request(bridge, "/api/v1/resume", token=bridge.token, payload={
            "request_id": task["request_id"], "execution_id": task["execution_id"],
        })
        assert resumed["result"]["status"] == "QUEUED"
        next_task = _request(bridge, "/api/v1/next", token=bridge.token)["task"]
        assert next_task["request_id"] == queued["request_id"]
        assert next_task["execution_id"] != task["execution_id"]
    finally:
        bridge.shutdown()
        bridge.server_close()
        thread.join(timeout=5)


def test_waiting_browser_request_accepts_verified_human_pdf_upload(tmp_path: Path) -> None:
    service, collection_id, paper_id = _paper_request(tmp_path)
    worker = AcquisitionWorker(tmp_path, "network")
    worker._queue_browser_acquisition(
        {"collection_id": collection_id, "paper_id": paper_id}, "test"
    )
    bridge = BrowserBridgeServer(service.paperpool, port=0, download_root=tmp_path / "Downloads")
    thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    thread.start()
    try:
        task = _request(bridge, "/api/v1/next", token=bridge.token)["task"]
        pdf = tmp_path / "selected.pdf"
        _compressed_pdf(pdf)
        body = pdf.read_bytes()

        def upload(data: bytes, *, execution_id: str = task["execution_id"]) -> dict:
            request = urllib.request.Request(
                f"http://127.0.0.1:{bridge.server_port}/api/v1/upload",
                data=data,
                headers={
                    "Origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "X-RSTV4-Bridge-Token": bridge.token,
                    "X-RSTV4-Request-ID": task["request_id"],
                    "X-RSTV4-Execution-ID": execution_id,
                    "X-RSTV4-Article-URL": (
                        "https://www.sciencedirect.com/science/article/pii/"
                        "S0038092X23000683"
                    ),
                    "Content-Type": "application/pdf",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)

        with pytest.raises(urllib.error.HTTPError) as not_waiting:
            upload(body)
        assert not_waiting.value.code == 422
        _request(bridge, "/api/v1/status", token=bridge.token, payload={
            "request_id": task["request_id"], "execution_id": task["execution_id"],
            "status": "WAITING_HUMAN", "error": {"reason": "security verification"},
        })
        with pytest.raises(urllib.error.HTTPError) as stale:
            upload(body, execution_id="stale")
        assert stale.value.code == 422
        with pytest.raises(urllib.error.HTTPError) as html:
            upload(b"<html>Security verification</html>")
        assert html.value.code == 422

        result = upload(body)["result"]
        registered = result["registered_files"][0]
        assert registered["identity_status"] == "VERIFIED"
        canonical = Path(registered["storage_path"])
        assert canonical.is_file()
        assert canonical.read_bytes() == body
        assert canonical.name == "source.pdf"
        assert canonical.parent.parent == service.paperpool.artifacts_root / paper_id
        assert result["status"] == "COMPLETED"
        assert json.loads(result["output_refs_json"]) == [str(canonical)]
        with sqlite3.connect(service.paperpool.db_path) as conn:
            source = conn.execute(
                "SELECT source_url,acquisition_method FROM source_file_versions WHERE paper_id=?",
                (paper_id,),
            ).fetchone()
            assert source == (
                "https://www.sciencedirect.com/science/article/pii/S0038092X23000683",
                "chrome-human-assisted",
            )
    finally:
        bridge.shutdown()
        bridge.server_close()
        thread.join(timeout=5)
