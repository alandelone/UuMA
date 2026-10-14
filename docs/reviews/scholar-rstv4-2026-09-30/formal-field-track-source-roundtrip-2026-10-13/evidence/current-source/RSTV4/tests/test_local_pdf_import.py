from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from rstv4.acquisition import AcquisitionService
from rstv4.local_pdf_import import LocalPdfImporter
from rstv4.models import LocalPdfImportInput


def _pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)


def test_local_pdf_intake_preserves_duplicate_provenance(tmp_path: Path) -> None:
    service = AcquisitionService(tmp_path / "rstv4")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _pdf(first / "Solar Forecasting Study.pdf")
    (second / "Copy of Solar Forecasting Study.pdf").write_bytes(
        (first / "Solar Forecasting Study.pdf").read_bytes()
    )
    payload = LocalPdfImportInput(directories=[str(first), str(second)], max_files=10)

    result = service.import_local_pdf_directories(payload)
    assert result["total"] == 2
    assert result["statuses"] == {"IMPORTED_NEEDS_REVIEW": 1, "ALREADY_CATALOGED": 1}
    assert len(service.list_papers()) == 1
    assert len(service.get_paper(service.list_papers()[0]["paper_id"])["files"]) == 1

    repeated = service.import_local_pdf_directories(payload)
    assert repeated["processed"] == 0
    assert repeated["total"] == 2


def test_parser_derivative_is_quarantined_without_deletion(tmp_path: Path) -> None:
    service = AcquisitionService(tmp_path / "rstv4")
    root = tmp_path / "papers"
    parser = root / "pdfparser"
    parser.mkdir(parents=True)
    derivative = parser / "Solar Study_layout.pdf"
    _pdf(derivative)
    importer = LocalPdfImporter(service)
    importer._stage(derivative, root, derivative.stat().st_size)
    importer._process(derivative)
    paper_id = service.list_papers()[0]["paper_id"]

    result = service.quarantine_local_pdf_parser_outputs(str(root))
    assert result == {"excluded_files": 1, "quarantined_papers": 1}
    assert service.list_papers() == []
    assert service.get_paper(paper_id)["catalog_status"] == "QUARANTINED"
    assert len(service.get_paper(paper_id)["files"]) == 1

    scan = service.import_local_pdf_directories(LocalPdfImportInput(directories=[str(root)]))
    assert scan["discovered"] == 0
    assert scan["statuses"] == {"EXCLUDED_DERIVATIVE": 1}
