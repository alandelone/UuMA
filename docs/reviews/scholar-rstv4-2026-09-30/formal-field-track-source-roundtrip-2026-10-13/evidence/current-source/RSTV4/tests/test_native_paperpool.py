from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import (
    AcquisitionWorker,
    HumanWait,
    ResourceWait,
    instance_lock,
)
from rstv4.model_gateway import UnlimitedLLMGateway
from rstv4.models import (
    BrowserAcquisitionInput,
    BrowserAcquisitionReceiptInput,
    CollectionCreateInput,
    CollectionSearchInput,
    FieldInput,
    JournalMetricsImportInput,
    LegacyPaperMigrationInput,
    PdfRegistrationInput,
    SourceCandidate,
)
from rstv4.paperpool_evaluation import evaluate_records
from rstv4.sources import ProviderResult
from rstv4.track_first import TrackFirstService


def make_service(root: Path) -> tuple[AcquisitionService, str]:
    track_first = TrackFirstService(root)
    field = track_first.create_field(FieldInput(name="Native PaperPool Test Field"))
    return track_first.paperpool, field["field_id"]


def make_collection(service: AcquisitionService, field_id: str) -> dict:
    return service.create_collection(
        CollectionCreateInput(
            field_id=field_id,
            name="Seed collection",
            scope={
                "question": "How is the method validated?",
                "scopus_category": "Computer Science",
            },
            dois=["https://doi.org/10.1000/SEED"],
            bibtex="""@article{x, title={A second seed}, author={Doe, Jane}, year={2024}}""",
            idempotency_key="collection-test",
        )
    )


def test_collection_seed_import_is_idempotent(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    first = make_collection(service, field_id)
    second = make_collection(service, field_id)

    assert first["collection_id"] == second["collection_id"]
    assert len(second["seeds"]) == 2
    frontier = service.get_frontier(first["collection_id"])
    assert len(frontier) == 2
    assert all(job["status"] == "READY" for job in frontier)


def test_collection_search_uses_durable_queue_and_deduplicates_dois(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(
        CollectionCreateInput(
            field_id=field_id,
            name="Discovery test",
            bibtex="@article{x,title={Local Seed},author={Doe, Jane},year={2024}}",
            idempotency_key="discovery-test-collection",
        )
    )
    collection_id = collection["collection_id"]
    network = AcquisitionWorker(tmp_path, "network", worker_id="discovery-network")
    assert network.run_once()["status"] == "SUCCEEDED"  # local BibTeX seed
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM acquisition_jobs WHERE job_type='LOCATE_PDF'"
        ).fetchone()[0] == 0  # no futile OA lookup without a DOI
    request = CollectionSearchInput(
        query="solar irradiance nowcasting",
        providers=["crossref", "openalex"],
        limit_per_provider=5,
        idempotency_key="discovery-test-search",
    )
    first = service.request_collection_search(collection_id, request)
    assert service.request_collection_search(collection_id, request)["job_id"] == first["job_id"]

    def fake_search(query: str, *, providers: list[str], limit_per_provider: int) -> list:
        assert (query, providers, limit_per_provider) == (
            "solar irradiance nowcasting", ["crossref", "openalex"], 5
        )
        return [
            ProviderResult(
                "crossref", [SourceCandidate(
                    source_provider="crossref", external_id="10.1234/new",
                    doi="10.1234/new", title="Sky Image Nowcasting",
                    authors=["A Researcher"], published_year=2024,
                )],
            ),
            ProviderResult(
                "openalex", [
                    SourceCandidate(
                        source_provider="openalex", external_id="W123",
                        doi="https://doi.org/10.1234/new",
                        title="Sky Image Nowcasting indexed variant",
                        authors=["A Researcher"], published_year=2024,
                    ),
                    SourceCandidate(
                        source_provider="openalex", external_id="W456",
                        title="Forecasting Without a DOI", authors=["B Researcher"],
                        published_year=2023,
                    ),
                ],
            ),
        ]

    monkeypatch.setattr("rstv4.acquisition_worker.search_all", fake_search)
    completed = network.run_once()
    assert completed is not None and completed["status"] == "SUCCEEDED"
    result = json.loads(completed["result_json"])
    assert result["raw_candidates"] == 3
    assert result["unique_catalog_papers"] == 2
    assert result["new_collection_members"] == 2
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM collection_memberships WHERE collection_id=? "
            "AND discovery_kind='SEARCH'", (collection_id,)
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=? "
            "AND job_type='SCREEN'", (collection_id,)
        ).fetchone()[0] == 3  # seed plus two unique search papers
        assert conn.execute(
            "SELECT COUNT(*) FROM paper_sources WHERE provider IN ('crossref','openalex')"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT title FROM papers WHERE doi='10.1234/new'"
        ).fetchone()[0] == "Sky Image Nowcasting"

    model = AcquisitionWorker(
        tmp_path, "model", model_gateway=FakeGateway(), worker_id="discovery-model"
    )
    for _ in range(3):
        assert model.run_once()["status"] == "SUCCEEDED"
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM acquisition_jobs j JOIN papers p ON p.paper_id=j.paper_id
               WHERE j.collection_id=? AND j.job_type='LOCATE_PDF' AND p.doi=?""",
            (collection_id, "10.1234/new"),
        ).fetchone()[0] == 1


def test_search_observation_does_not_erase_existing_paper_metadata(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = make_collection(service, field_id)
    seed = next(item for item in collection["seeds"] if item["seed_type"] == "DOI")
    paper = service.resolve_seed(seed["seed_id"], {
        "doi": "10.1000/seed", "title": "Established Paper",
        "authors": ["Jane Doe"], "year": 2023, "abstract": "Established abstract",
    })
    service.publish_collection_search_results(
        collection["collection_id"], "established query", [ProviderResult(
            "openalex", [SourceCandidate(
                source_provider="openalex", doi="10.1000/seed",
                title="Noisy indexed title", authors=[], published_year=None, abstract="",
            )],
        )],
    )
    updated = service.get_paper(paper["paper_id"])
    assert updated["title"] == "Established Paper"
    assert updated["authors"] == ["Jane Doe"]
    assert updated["published_year"] == 2023
    assert updated["abstract"] == "Established abstract"


def test_doi_free_reference_lookup_is_bounded_and_links_confirmed_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(
        CollectionCreateInput(
            field_id=field_id, name="Reference lookup",
            bibtex="@article{x,title={Lookup Seed},author={Doe, Jane},year={2024}}",
            idempotency_key="reference-lookup-collection",
        )
    )
    collection_id = collection["collection_id"]
    network = AcquisitionWorker(tmp_path, "network", worker_id="reference-lookup-network")
    assert network.run_once()["status"] == "SUCCEEDED"
    paper = service.list_papers(collection_id)[0]
    pdf_dir = tmp_path / "data" / "paper-import"
    pdf_dir.mkdir(parents=True)
    pdf = pdf_dir / "lookup.pdf"
    pdf.write_bytes(b"%PDF-1.4\nLookup Seed full body\n%%EOF")
    file_version = service.register_pdf(
        collection_id,
        PdfRegistrationInput(
            paper_id=paper["paper_id"], path=str(pdf),
            acquisition_method="LOCAL_IMPORT", idempotency_key="lookup-source-pdf",
        ),
    )
    service.publish_parse_result(
        collection_id, paper["paper_id"], file_version["file_version_id"],
        parser_name="fixture", parser_version="1", config={}, manifest={},
        blocks=[{"page_number": 1, "section": "Body", "text": "Full body"}],
        references=[{"raw_text": (
            "Greenlee LF, Lawler DF. Reverse osmosis desalination: water sources, "
            "technology, and today's challenges. Water Res. 2009;43:2317-2348."
        ), "page_number": 1}],
    )
    queued = service.request_reference_lookups(collection_id, paper["paper_id"], limit=1)
    assert queued["queued"] == 1
    assert service.request_reference_lookups(
        collection_id, paper["paper_id"], limit=1
    )["queued"] == 0

    def fake_lookup(raw_text: str) -> ProviderResult:
        assert "Greenlee" in raw_text
        return ProviderResult("crossref_bibliographic", [SourceCandidate(
            source_provider="crossref", doi="10.1234/desalination",
            title="Reverse osmosis desalination: water sources, technology, and today's challenges",
            authors=["Lisa Greenlee"], published_year=2009,
        )])

    monkeypatch.setattr("rstv4.acquisition_worker.lookup_bibliographic_reference", fake_lookup)
    resolved = network.run_once()
    assert resolved is not None and resolved["status"] == "SUCCEEDED"
    assert json.loads(resolved["result_json"])["status"] == "RESOLVED"
    edges = service.get_citation_neighborhood(paper["paper_id"], collection_id=collection_id)
    assert len(edges["edges"]) == 1
    cited = service.get_paper(edges["edges"][0]["cited_paper_id"])
    assert cited["doi"] == "10.1234/desalination"


def test_network_reuses_catalog_pdf_across_collections_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, field_id = make_service(tmp_path)
    first = service.create_collection(CollectionCreateInput(
        field_id=field_id, name="Original collection", dois=["10.1000/seed"],
        idempotency_key="catalog-reuse-first",
    ))
    metadata = {"doi": "10.1000/seed", "title": "The Seed Paper", "authors": ["Jane Doe"]}
    paper = service.resolve_seed(first["seeds"][0]["seed_id"], metadata)
    import_dir = tmp_path / "data" / "paper-import"
    import_dir.mkdir(parents=True)
    pdf = import_dir / "seed.pdf"
    pdf.write_bytes(b"%PDF-1.4\nThe Seed Paper DOI 10.1000/seed\n%%EOF")
    registered = service.register_pdf(first["collection_id"], PdfRegistrationInput(
        paper_id=paper["paper_id"], path=str(pdf), acquisition_method="LOCAL_IMPORT",
        idempotency_key="catalog-reuse-pdf",
    ))
    assert registered["identity_status"] == "VERIFIED"

    second = service.create_collection(CollectionCreateInput(
        field_id=field_id, name="Second collection", dois=["10.1000/seed"],
        idempotency_key="catalog-reuse-second",
    ))
    same_paper = service.resolve_seed(second["seeds"][0]["seed_id"], metadata)
    assert same_paper["paper_id"] == paper["paper_id"]
    monkeypatch.setattr(
        "rstv4.acquisition_worker.locate_open_access_pdf",
        lambda _: pytest.fail("A registered PDF must not trigger a network lookup"),
    )
    worker = AcquisitionWorker(tmp_path, "network")
    job = {"collection_id": second["collection_id"], "paper_id": paper["paper_id"]}
    result, next_jobs = worker._handle_locate_pdf(job, {"doi": "10.1000/seed"})
    repeated, _ = worker._handle_locate_pdf(job, {"doi": "10.1000/seed"})
    assert result["status"] == "REUSED_CATALOG_PDF"
    assert result["file_version_id"] == registered["file_version_id"]
    assert repeated["parse_job_id"] == result["parse_job_id"]
    assert next_jobs == []
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=? AND job_type='PARSE_PDF'",
            (second["collection_id"],),
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM source_file_versions").fetchone()[0] == 1

    Path(registered["storage_path"]).write_bytes(b"%PDF-1.4\nCorrupted local copy\n%%EOF")
    assert service.reuse_registered_pdf(second["collection_id"], paper["paper_id"]) is None


def test_registered_pdf_needing_identity_review_does_not_redownload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(CollectionCreateInput(
        field_id=field_id, name="Review collection", dois=["10.1000/seed"],
        idempotency_key="catalog-review-collection",
    ))
    paper = service.resolve_seed(collection["seeds"][0]["seed_id"], {
        "doi": "10.1000/seed", "title": "The Seed Paper",
    })
    import_dir = tmp_path / "data" / "paper-import"
    import_dir.mkdir(parents=True)
    pdf = import_dir / "uncertain.pdf"
    pdf.write_bytes(b"%PDF-1.4\nUnrelated text\n%%EOF")
    registered = service.register_pdf(collection["collection_id"], PdfRegistrationInput(
        paper_id=paper["paper_id"], path=str(pdf), acquisition_method="LOCAL_IMPORT",
        idempotency_key="catalog-review-pdf",
    ))
    assert registered["identity_status"] == "NEEDS_REVIEW"
    monkeypatch.setattr(
        "rstv4.acquisition_worker.locate_open_access_pdf",
        lambda _: pytest.fail("A registered PDF awaiting review must not be redownloaded"),
    )
    worker = AcquisitionWorker(tmp_path, "network")
    with pytest.raises(HumanWait, match="REGISTERED_PDF_NEEDS_REVIEW"):
        worker._handle_locate_pdf(
            {"collection_id": collection["collection_id"], "paper_id": paper["paper_id"]},
            {"doi": "10.1000/seed"},
        )


def test_network_defers_concurrent_download_for_same_paper(tmp_path: Path) -> None:
    worker = AcquisitionWorker(tmp_path, "network")
    with instance_lock(tmp_path, "pdf", "paper_shared"), pytest.raises(
        ResourceWait, match="Another worker is acquiring this paper"
    ):
        worker._handle_locate_pdf({"paper_id": "paper_shared"}, {})


def test_verified_pdf_is_required_before_reference_expansion(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = make_collection(service, field_id)
    doi_seed = next(seed for seed in collection["seeds"] if seed["seed_type"] == "DOI")
    paper = service.resolve_seed(
        doi_seed["seed_id"],
        {
            "doi": "10.1000/seed",
            "title": "The Seed Paper",
            "authors": ["Jane Doe"],
            "year": 2023,
            "abstract": "A useful abstract.",
            "source": "test",
            "raw": {"ISSN": ["1234-5678"]},
        },
    )
    collection_id = collection["collection_id"]

    with pytest.raises(ValueError, match="identity-verified PDF"):
        service.publish_parse_result(
            collection_id,
            paper["paper_id"],
            "missing-file",
            parser_name="test",
            parser_version="1",
            config={},
            manifest={},
            blocks=[],
            references=[{"raw_text": "Cited work. doi:10.1000/cited", "page_number": 2}],
        )

    import_dir = tmp_path / "data" / "paper-import"
    import_dir.mkdir(parents=True)
    pdf = import_dir / "seed.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\nThe Seed Paper DOI 10.1000/seed\nfull body\n%%EOF"
    )
    file_version = service.register_pdf(
        collection_id,
        PdfRegistrationInput(
            paper_id=paper["paper_id"],
            path=str(pdf),
            acquisition_method="LOCAL_IMPORT",
            idempotency_key="local-seed-pdf",
        )
    )
    with pytest.raises(ValueError, match="no readable document blocks"):
        service.publish_parse_result(
            collection_id,
            paper["paper_id"],
            file_version["file_version_id"],
            parser_name="test",
            parser_version="1",
            config={"empty": True},
            manifest={},
            blocks=[],
            references=[],
        )
    parsed = service.publish_parse_result(
        collection_id,
        paper["paper_id"],
        file_version["file_version_id"],
        parser_name="test",
        parser_version="1",
        config={"fixture": True},
        manifest={"structured_path": "fixture.md"},
        blocks=[{"page_number": 1, "section": "Body", "text": "full body"}],
        references=[{"raw_text": "Cited work. doi:10.1000/cited", "page_number": 2}],
    )
    assert parsed["references"] == 1
    edges = service.get_citation_neighborhood(paper["paper_id"], collection_id=collection_id)
    assert len(edges["edges"]) == 1
    cited = service.get_paper(edges["edges"][0]["cited_paper_id"])
    assert cited["files"] == []
    assert all(job["job_type"] != "PARSE_PDF" for job in cited["processing"])
    metrics = import_dir / "scopus.csv"
    metrics.write_text(
        "ISSN,category,quartile,CiteScore\n1234-5678,Computer Science,Q1,9.2\n",
        encoding="utf-8",
    )
    imported_metrics = service.import_journal_metrics_csv(
        JournalMetricsImportInput(path=str(metrics), metric_year=2025)
    )
    assert imported_metrics["imported"] == 1
    ranked = service.get_core_candidates(collection_id)
    assert ranked
    seed_rank = next(item for item in ranked if item["paper_id"] == paper["paper_id"])
    assert seed_rank["quartile"] == "Q1"
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM core_rankings").fetchone()[0] == len(ranked)


def test_expired_lease_fencing_rejects_late_worker(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(
        CollectionCreateInput(
            field_id=field_id,
            name="Lease test",
            dois=["10.1000/lease"],
            idempotency_key="lease-collection",
        )
    )
    first = service.claim_job("worker-one", ["NETWORK"])
    assert first is not None
    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            "UPDATE acquisition_jobs SET lease_expires_at=? WHERE job_id=?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), first["job_id"]),
        )
    second = service.claim_job("worker-two", ["NETWORK"])
    assert second is not None
    assert second["job_id"] == first["job_id"]
    assert second["fencing_token"] > first["fencing_token"]
    with pytest.raises(ValueError, match="stale"):
        service.complete_job(
            first["job_id"], "worker-one", first["fencing_token"], {"late": True}
        )
    completed = service.complete_job(
        second["job_id"], "worker-two", second["fencing_token"], {"ok": True}
    )
    assert completed["status"] == "SUCCEEDED"
    assert service.get_collection(collection["collection_id"])["counts"]["jobs"] == 1
    assert service.get_usage(collection["collection_id"])["attempts"] == 2


def test_legacy_migration_excludes_semantics_and_references(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    legacy = tmp_path / "legacy.db"
    with sqlite3.connect(legacy) as conn:
        conn.execute(
            """CREATE TABLE paper(
               id INTEGER PRIMARY KEY,title TEXT,year TEXT,authors TEXT,file TEXT,DOI TEXT,
               Pp_abstract TEXT,Pp_minced_semantics TEXT,references_json TEXT)"""
        )
        conn.execute(
            "INSERT INTO paper VALUES(1,?,?,?,?,?,?,?,?)",
            (
                "Migrated basic record",
                "2020",
                json.dumps(["A. Author"]),
                None,
                "10.1000/migrated",
                "A source abstract",
                json.dumps([{"layer4": "Claim"}]),
                json.dumps(["old reference"]),
            ),
        )
    request = LegacyPaperMigrationInput(database_path=str(legacy), copy_files=False)
    first = service.migrate_legacy_paperpool(request)
    second = service.migrate_legacy_paperpool(request)
    assert first["imported"] == 1
    assert second["imported"] == 0
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM legacy_paper_mappings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM reference_entries").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM skeleton_runs").fetchone()[0] == 0
        observation = conn.execute(
            "SELECT payload_json FROM metadata_observations WHERE provider='LEGACY_PAPERPOOL'"
        ).fetchone()[0]
    assert "A source abstract" in observation
    assert "layer4" not in observation
    assert "old reference" not in observation


class FakeParser:
    def parse(self, pdf: str, output: str) -> dict:
        return {
            "parser": "fixture-parser",
            "parser_version": "1",
            "manifest": {"structured_path": str(Path(output) / "paper.md")},
            "blocks": [
                {
                    "page_number": 1,
                    "section": "Methods",
                    "text": "We validate the method on a public benchmark.",
                }
            ],
            "references": [],
        }


class FakeGateway:
    def analyze(self, task: str, payload: dict) -> dict:
        contract = {
            "task": task,
            "tier": "light" if task in {"screen", "quick_read"} else "standard",
            "prompt_version": f"{task}-fixture",
        }
        if task == "screen":
            return {"category": "DIRECT", "evidence_quotes": [], "_contract": contract}
        if task == "quick_read":
            return {
                "question": "Does it work?",
                "method": "Benchmark",
                "materials": "Public data",
                "author_contribution": "Validation",
                "results": "Supported",
                "limitations": "Small sample",
                "deep_read_reasons": ["CORE_VERIFICATION"],
                "evidence_quotes": [],
                "_contract": contract,
            }
        if task == "skeleton_layer_1":
            return {
                "atomic_sentences": [payload["raw_text"]],
                "triplets": [
                    {"subject": "method", "predicate": "validated on", "object": "benchmark"}
                ],
                "_contract": contract,
            }
        if task == "skeleton_layer_2":
            return {"discourse_relation": "Evidence", "_contract": contract}
        if task == "skeleton_layer_3":
            return {"intent": "Validate", "_contract": contract}
        if task == "skeleton_layer_4":
            return {"role": "Evidence_Result", "confidence": 0.9, "_contract": contract}
        return {"contribution": "Validation", "evidence_quotes": [], "_contract": contract}


def test_workers_resume_each_stage_and_publish_four_layer_skeleton(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(
        CollectionCreateInput(
            field_id=field_id,
            name="Worker pipeline",
            bibtex="""@article{x,title={Worker Test Paper},author={Doe, Jane},year={2024}}""",
            idempotency_key="worker-pipeline",
        )
    )
    network = AcquisitionWorker(tmp_path, "network", worker_id="network-test")
    assert network.run_once()["status"] == "SUCCEEDED"
    paper = service.list_papers(collection["collection_id"])[0]

    import_dir = tmp_path / "data" / "paper-import"
    import_dir.mkdir(parents=True, exist_ok=True)
    pdf = import_dir / "worker.pdf"
    pdf.write_bytes(b"%PDF-1.4\nWorker Test Paper benchmark full body\n%%EOF")
    service.register_pdf(
        collection["collection_id"],
        PdfRegistrationInput(
            paper_id=paper["paper_id"],
            path=str(pdf),
            acquisition_method="LOCAL_IMPORT",
            idempotency_key="worker-test-pdf",
        ),
    )
    parser_worker = AcquisitionWorker(
        tmp_path, "parser", parser=FakeParser(), worker_id="parser-test"
    )
    assert parser_worker.run_once()["status"] == "SUCCEEDED"

    model_worker = AcquisitionWorker(
        tmp_path, "model", model_gateway=FakeGateway(), worker_id="model-test"
    )
    for _ in range(4):
        completed = model_worker.run_once()
        assert completed is not None and completed["status"] == "SUCCEEDED"
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM skeleton_runs WHERE status='SUCCEEDED'"
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM skeleton_checkpoints").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM paper_skeletons").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM paper_assessments").fetchone()[0] == 3


def test_parser_missing_source_references_waits_for_review(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = service.create_collection(
        CollectionCreateInput(
            field_id=field_id,
            name="Reference quality gate",
            bibtex="@article{x,title={Reference Gate Paper},author={Doe, Jane},year={2024}}",
            idempotency_key="reference-gate",
        )
    )
    AcquisitionWorker(tmp_path, "network", worker_id="reference-network").run_once()
    paper = service.list_papers(collection["collection_id"])[0]
    pdf_dir = tmp_path / "data" / "paper-import"
    pdf_dir.mkdir(parents=True)
    pdf = pdf_dir / "reference-gate.pdf"
    pdf.write_bytes(b"%PDF-1.4\nReference Gate Paper full body\n%%EOF")
    service.register_pdf(
        collection["collection_id"],
        PdfRegistrationInput(
            paper_id=paper["paper_id"], path=str(pdf),
            acquisition_method="LOCAL_IMPORT", idempotency_key="reference-gate-pdf",
        ),
    )

    class MissingReferenceParser(FakeParser):
        def parse(self, pdf: str, output: str) -> dict:
            parsed = super().parse(pdf, output)
            parsed["manifest"]["quality"] = {
                "reference_page_alignment": {
                    "missing_source_numbered_references": [5],
                }
            }
            return parsed

    worker = AcquisitionWorker(
        tmp_path, "parser", parser=MissingReferenceParser(), worker_id="reference-parser"
    )
    result = worker.run_once()

    assert result is not None and result["status"] == "NEEDS_HUMAN"
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM parse_runs").fetchone()[0] == 0


def test_browser_receipt_is_scoped_and_registers_valid_output(tmp_path: Path) -> None:
    service, field_id = make_service(tmp_path)
    collection = make_collection(service, field_id)
    seed = next(item for item in collection["seeds"] if item["seed_type"] == "DOI")
    paper = service.resolve_seed(
        seed["seed_id"], {"doi": "10.1000/seed", "title": "Browser Paper"}
    )
    request = service.request_browser_acquisition(
        collection["collection_id"],
        BrowserAcquisitionInput(
            paper_id=paper["paper_id"], idempotency_key="browser-request-test"
        ),
    )
    target = Path(request["target_directory"])
    target.mkdir(parents=True)
    output = target / "paper.pdf"
    output.write_bytes(b"%PDF-1.4\nBrowser Paper 10.1000/seed full body\n%%EOF")
    with pytest.raises(PermissionError):
        service.submit_browser_acquisition_receipt(
            BrowserAcquisitionReceiptInput(
                request_id=request["request_id"], execution_id="execution-1",
                status="COMPLETED", output_paths=[str(tmp_path / "outside.pdf")],
            )
        )
    receipt = service.submit_browser_acquisition_receipt(
        BrowserAcquisitionReceiptInput(
            request_id=request["request_id"], execution_id="execution-1",
            action_id="copycat-acquire", action_version="1", status="COMPLETED",
            output_paths=[str(output)],
        )
    )
    assert receipt["registered_files"][0]["identity_status"] == "VERIFIED"


def test_model_gateway_uses_strict_router_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "model": "fixture-light-model",
                    "choices": [{"message": {"content": '{"category":"DIRECT"}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3},
                }
            ).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        observed.update(json.loads(request.data.decode()))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gateway = UnlimitedLLMGateway(tmp_path)
    result = gateway.analyze("screen", {"title": "Paper", "abstract": "Relevant"})
    assert observed["model"] == "light"
    assert result["_contract"]["tier"] == "light"
    assert result["_contract"]["actual_model"] == "fixture-light-model"


def test_model_benchmark_enforces_paper_split_and_release_gates() -> None:
    records = [
        {
            "paper_id": "p1", "split": "test", "task": "screen",
            "expected": {"category": "DIRECT"}, "prediction": {"category": "DIRECT"},
        },
        {
            "paper_id": "p1", "split": "test", "task": "provenance",
            "prediction": {"unsupported_claims": 0, "atomic_claims": 10},
        },
        {
            "paper_id": "p1", "split": "test", "task": "skeleton_layer_1",
            "expected": {"facts": ["a"]}, "prediction": {"facts": ["a"]},
        },
        *[
            {
                "paper_id": "p1", "split": "test", "task": f"skeleton_layer_{layer}",
                "expected": {"label": "A"}, "prediction": {"label": "A"},
            }
            for layer in (2, 3, 4)
        ],
    ]
    report = evaluate_records(records)
    assert report["passed"] is True
    with pytest.raises(ValueError, match="cross evaluation splits"):
        evaluate_records(
            [
                {"paper_id": "same", "split": "train", "task": "screen"},
                {"paper_id": "same", "split": "test", "task": "screen"},
            ]
        )
