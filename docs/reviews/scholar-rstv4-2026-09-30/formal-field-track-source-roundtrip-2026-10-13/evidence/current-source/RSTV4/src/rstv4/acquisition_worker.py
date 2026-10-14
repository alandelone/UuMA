from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from .acquisition import AcquisitionService, digest
from .catalog_review_workflow import file_integrity
from .collection_runtime import CollectionBudgetExceeded
from .database import transaction
from .external_fulltext import FALLBACK_ADAPTERS
from .model_gateway import ContextBudgetExceeded, UnlimitedLLMGateway
from .models import BrowserAcquisitionInput, PdfRegistrationInput
from .paper_parser import MinerUParser
from .parser_quality import _align_reference_pages
from .reference_parser import GrobidReferenceParser
from .sources import (
    locate_open_access_pdf,
    lookup_bibliographic_reference,
    resolve_doi,
    search_all,
)

ROLE_QUEUES = {
    "network": ["NETWORK"],
    "parser": ["PARSER"],
    "model": ["MODEL_SCREEN", "MODEL_READ", "MODEL_SKELETON", "MODEL_ASSESS"],
}


class ResourceWait(RuntimeError):
    def __init__(self, message: str, retry_after: int = 3600):
        self.retry_after = retry_after
        super().__init__(message)


class HumanWait(RuntimeError):
    def __init__(self, message: str, retry_after: int = 86400, *, review: dict[str, Any] | None = None):
        self.retry_after = retry_after
        self.review = review
        super().__init__(message)


class LockBusy(RuntimeError):
    pass


@contextmanager
def instance_lock(root: Path, role: str, slot: str):
    """Hold an exclusive cross-process lock for a worker slot or paper acquisition."""
    lock_dir = root / ".rstv4-local" / "workers"
    lock_dir.mkdir(parents=True, exist_ok=True)
    stream = (lock_dir / f"{role}-{slot}.lock").open("a+b")
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise LockBusy(f"Lock is already held: {role}-{slot}") from exc
    try:
        yield
    finally:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


class LeaseHeartbeat:
    def __init__(self, service: AcquisitionService, job: dict[str, Any], worker_id: str) -> None:
        self.service = service
        self.job = job
        self.worker_id = worker_id
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop_event.wait(20):
            if not self.service.renew_lease(
                self.job["job_id"], self.worker_id, self.job["fencing_token"]
            ):
                return


class AcquisitionWorker:
    def __init__(
        self,
        root: str | Path,
        role: str,
        *,
        model_gateway: Any | None = None,
        parser: Any | None = None,
        worker_id: str | None = None,
    ) -> None:
        if role not in ROLE_QUEUES:
            raise ValueError(f"Unknown worker role: {role}")
        self.root = Path(root).resolve()
        self.role = role
        self.service = AcquisitionService(self.root)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{role}"
        self.model = model_gateway
        self.parser = parser or MinerUParser(self.root)
        self.reference_parser = GrobidReferenceParser()
        self._presence_instance = uuid4().hex
        self._presence_job: str | None = None
        self._presence_thread: threading.Thread | None = None
        self._presence_stop = threading.Event()

    def _report_presence(self, state: str) -> None:
        self.service.report_worker_presence(self.worker_id, self._presence_instance, self.role,
                                            socket.gethostname(), os.getpid(), state, self._presence_job)

    @contextmanager
    def _worker_presence(self):
        owned = self._presence_thread is None
        if owned:
            self._presence_stop.clear()
            self._report_presence("IDLE")

            def pulse():
                while not self._presence_stop.wait(15):
                    self._report_presence("RUNNING" if self._presence_job else "IDLE")

            self._presence_thread = threading.Thread(target=pulse, daemon=True)
            self._presence_thread.start()
        try:
            yield
        finally:
            if owned:
                self._presence_stop.set()
                self._presence_thread.join(timeout=5)
                self._presence_thread = None
                self._presence_job = None
                self._report_presence("STOPPED")

    def run_once(self) -> dict[str, Any] | None:
        with self._worker_presence():
            try:
                return self._run_once()
            finally:
                self._presence_job = None
                self._report_presence("IDLE")

    def _run_once(self) -> dict[str, Any] | None:
        job = self.service.claim_job(self.worker_id, ROLE_QUEUES[self.role])
        if job is None:
            return None
        self._presence_job = job["job_id"]
        self._report_presence("RUNNING")
        with LeaseHeartbeat(self.service, job, self.worker_id):
            try:
                result, next_jobs = self._execute(job)
                return self.service.complete_job(
                    job["job_id"],
                    self.worker_id,
                    job["fencing_token"],
                    result,
                    next_jobs,
                )
            except CollectionBudgetExceeded as exc:
                return self.service.defer_job(
                    job["job_id"], self.worker_id, job["fencing_token"],
                    status="RESOURCE_WAIT", error_code="COLLECTION_BUDGET", detail=str(exc),
                    retry_after_seconds=1,
                )
            except ContextBudgetExceeded as exc:
                return self.service.fail_job(
                    job["job_id"], self.worker_id, job["fencing_token"],
                    error_code="CONTEXT_SPLIT_REQUIRED", detail=str(exc), terminal=True,
                )
            except ResourceWait as exc:
                return self.service.defer_job(
                    job["job_id"], self.worker_id, job["fencing_token"],
                    status="RESOURCE_WAIT", error_code="RESOURCE_WAIT", detail=str(exc),
                    retry_after_seconds=exc.retry_after,
                )
            except HumanWait as exc:
                return self.service.defer_job(
                    job["job_id"], self.worker_id, job["fencing_token"],
                    status="NEEDS_HUMAN", error_code="NEEDS_HUMAN", detail=str(exc),
                    retry_after_seconds=exc.retry_after,
                    review_context=exc.review,
                )
            except Exception as exc:  # noqa: BLE001 - preserve durable failure classification
                retry_after = getattr(exc, "retry_after", None)
                error_code = "TEMPORARY_FAILURE"
                delay = int(retry_after or 30)
                if isinstance(exc, (FileNotFoundError, PermissionError)):
                    error_code, delay = "NEEDS_CONFIGURATION", 3600
                return self.service.fail_job(
                    job["job_id"], self.worker_id, job["fencing_token"],
                    error_code=error_code, detail=str(exc), retry_after_seconds=delay,
                )

    def run_forever(self, idle_seconds: float = 2.0, stop_event: threading.Event | None = None) -> None:
        with self._worker_presence():
            while stop_event is None or not stop_event.is_set():
                if self.run_once() is None:
                    if stop_event is None:
                        time.sleep(idle_seconds)
                    else:
                        stop_event.wait(idle_seconds)

    def _execute(self, job: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        payload = json.loads(job["input_json"])
        handler = getattr(self, f"_handle_{job['job_type'].casefold()}", None)
        if handler is None:
            raise RuntimeError(f"No handler for {job['job_type']}")
        return handler(job, payload)

    def _handle_resolve_seed(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        identity = payload["identity"]
        if identity.get("doi"):
            with transaction(self.service.db_path) as conn:
                existing = conn.execute("SELECT * FROM papers WHERE doi=?", (identity["doi"],)).fetchone()
            if existing:
                metadata = {**dict(existing), "authors": json.loads(existing["authors_json"]),
                            "source_provider": "catalog-reuse"}
            else:
                provider = resolve_doi(identity["doi"])
                if not provider.candidates:
                    raise RuntimeError(provider.error or "DOI not found")
                metadata = provider.candidates[0].model_dump()
        else:
            metadata = {
                "title": identity.get("title"),
                "authors": identity.get("author", "").split(" and "),
                "year": identity.get("year"),
                "abstract": identity.get("abstract"),
                "source_provider": "bibtex",
            }
        paper = self.service.resolve_seed(payload["seed_id"], metadata)
        return {"paper_id": paper["paper_id"]}, []

    def _handle_search_literature(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        started = time.perf_counter()
        results = search_all(
            payload["query"], providers=payload["providers"],
            limit_per_provider=payload["limit_per_provider"],
        )
        searched = time.perf_counter()
        if all(result.error for result in results):
            raise RuntimeError(
                "Every literature provider failed: "
                + "; ".join(f"{result.provider}: {result.error}" for result in results)
            )
        published = self.service.publish_collection_search_results(
            job["collection_id"], payload["query"], results
        )
        published["provider_search_elapsed_s"] = round(searched - started, 3)
        published["catalog_publish_elapsed_s"] = round(time.perf_counter() - searched, 3)
        return published, []

    def _handle_resolve_reference(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with transaction(self.service.db_path) as conn:
            reference = conn.execute(
                "SELECT * FROM reference_entries WHERE reference_entry_id=?",
                (payload["reference_entry_id"],),
            ).fetchone()
        if reference is None:
            raise ValueError("Unknown reference")
        if reference["target_paper_id"]:
            return {"status": "ALREADY_RESOLVED"}, []
        result = lookup_bibliographic_reference(reference["raw_text"])
        if result.error:
            raise RuntimeError(result.error)
        if not result.candidates:
            return {"status": "NO_CONFIDENT_MATCH"}, []
        published = self.service.publish_bibliographic_reference_match(
            job["collection_id"], reference["reference_entry_id"], result.candidates[0]
        )
        return {"status": "RESOLVED", **published}, []

    def _handle_resolve_paper(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        provider = resolve_doi(payload["doi"])
        if not provider.candidates:
            raise RuntimeError(provider.error or "DOI not found")
        metadata = provider.candidates[0].model_dump()
        paper = self.service.enrich_paper_metadata(job["paper_id"], metadata)
        next_jobs = [
            {
                "paper_id": job["paper_id"], "job_type": "SCREEN", "queue_class": "MODEL_SCREEN",
                "payload": {"scope_version": 1},
                "rule_version": "screen-v1-scope-1",
                "priority": 40,
            },
            {
                "paper_id": job["paper_id"], "job_type": "LOCATE_PDF", "queue_class": "NETWORK",
                "payload": {"doi": paper["doi"]}, "rule_version": "fulltext-v1", "priority": 30,
            },
        ]
        return {"paper_id": paper["paper_id"], "provider": provider.provider}, next_jobs

    def _handle_locate_pdf(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if payload.get("screen_context_sha256") and digest(self.service.screening_context(job["collection_id"], job["paper_id"])) != payload["screen_context_sha256"]:
            raise HumanWait("The selected paper or Collection scope changed before file reuse")
        try:
            with instance_lock(self.root, "pdf", job["paper_id"]):
                return self._acquire_or_reuse_pdf(job, payload)
        except LockBusy as exc:
            raise ResourceWait("Another worker is acquiring this paper", retry_after=30) from exc

    def _acquire_or_reuse_pdf(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        registered = self.service.reuse_registered_pdf(
            job["collection_id"], job["paper_id"]
        )
        if registered is not None:
            if registered["status"] == "CATALOG_QUARANTINED":
                raise HumanWait("Paper is quarantined in the Catalog")
            if registered["status"] == "REGISTERED_PDF_NEEDS_REVIEW":
                raise HumanWait(
                    f"Catalog PDF requires identity review: {registered['status']}",
                    review={"kind": "PDF_IDENTITY", "file_version_id": registered["file_version_id"]},
                )
            return registered, []
        doi = payload.get("doi")
        if not doi:
            raise HumanWait("Paper has no DOI for automated OA lookup; provide its lawful source PDF")
        self.service.import_root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.service.import_root).free < 10 * 1024**3:
            raise ResourceWait("Available disk is below the 10 GiB safety threshold")
        located = locate_open_access_pdf(doi)
        if not located.candidates:
            located_error = located.error or "No open full text found"
            fallback_dir = self.service.import_root / "fallback" / job["job_id"]
            for adapter in FALLBACK_ADAPTERS:
                try:
                    acquired = adapter.acquire(doi, fallback_dir / f"{adapter.name}.pdf")
                except (OSError, RuntimeError, ValueError) as exc:
                    located_error += f"; {adapter.name}: {exc}"
                    continue
                if acquired:
                    registered = self.service.register_pdf(
                        job["collection_id"],
                        PdfRegistrationInput(
                            paper_id=job["paper_id"], path=str(acquired),
                            acquisition_method=adapter.name,
                            idempotency_key=f"fallback-{adapter.name}-{job['job_id']}",
                        ),
                    )
                    if registered["identity_status"] == "VERIFIED":
                        return registered, []
            return self._queue_browser_acquisition(job, located_error), []
        candidate = located.candidates[0]
        target_dir = self.service.import_root / "network" / job["job_id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        partial = target_dir / "source.partial"
        final = target_dir / "source.pdf"
        request = urllib.request.Request(
            candidate.pdf_url, headers={"User-Agent": "RSTV4/0.1 (research assistant)"}
        )
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as output:
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > 100 * 1024 * 1024:
                        raise ValueError("PDF exceeds the 100 MiB default limit")
                    output.write(block)
            partial.replace(final)
            registered = self.service.register_pdf(
                job["collection_id"],
                PdfRegistrationInput(
                    paper_id=job["paper_id"], path=str(final), acquisition_method=located.provider,
                    source_url=candidate.pdf_url, idempotency_key=f"oa-{job['job_id']}",
                ),
            )
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            partial.unlink(missing_ok=True)
            return self._queue_browser_acquisition(job, f"OA PDF failed: {exc}"), []
        if registered["identity_status"] != "VERIFIED":
            raise HumanWait("Downloaded PDF requires identity review", review={
                "kind": "PDF_IDENTITY", "file_version_id": registered["file_version_id"]})
        return registered, []

    def _queue_browser_acquisition(
        self, job: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        request = self.service.request_browser_acquisition(
            job["collection_id"], BrowserAcquisitionInput(
                paper_id=job["paper_id"],
                idempotency_key=f"browser-fallback-{job['collection_id']}-{job['paper_id']}",
            ),
        )
        return {"status": "BROWSER_QUEUED", "request_id": request["request_id"],
                "reason": reason}

    def _handle_parse_pdf(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with transaction(self.service.db_path) as conn:
            source = conn.execute(
                "SELECT * FROM source_file_versions WHERE file_version_id=?",
                (payload["file_version_id"],),
            ).fetchone()
        if source is None:
            raise HumanWait("Parser source PDF is unavailable")
        if source["paper_id"] != job["paper_id"]:
            raise HumanWait("Parser source does not belong to its Catalog paper")
        if source["identity_status"] != "VERIFIED" or not file_integrity(dict(source)):
            raise HumanWait("Parser requires the original identity-verified PDF", review={
                "kind": "PDF_IDENTITY", "file_version_id": source["file_version_id"]})
        previous_review = json.loads(job.get("result_json") or "{}").get("review", {})
        correction_ids = previous_review.get("correction_action_ids", [])
        output = self.service.artifacts_root / job["paper_id"] / source["sha256"] / "parse"
        try:
            parsed = self.parser.parse(source["storage_path"], output)
        except (ValueError, TypeError) as error:
            raise HumanWait(str(error), review={"kind": "PARSE_QUALITY",
                "file_version_id": source["file_version_id"], "pdf_sha256": source["sha256"],
                "correction_action_ids": correction_ids}) from error
        corrections = []
        with transaction(self.service.db_path) as conn:
            for action_id in correction_ids:
                action = conn.execute("SELECT * FROM catalog_review_actions WHERE action_id=? AND case_id=? AND file_version_id=? AND action_kind='RECHECK_PARSE'",
                                      (action_id, job["job_id"], source["file_version_id"])).fetchone()
                if action is None:
                    raise HumanWait("Original parser correction is unavailable")
                result = json.loads(action["result_json"])
                if result["pdf_sha256"] != source["sha256"]:
                    raise HumanWait("Parser correction belongs to another PDF version")
                corrections.extend(result.get("corrections", []))
        if corrections:
            existing = {entry["raw_text"] for entry in parsed["references"]}
            for entry in corrections:
                if entry["raw_text"] not in existing:
                    parsed["references"].append(entry)
                    existing.add(entry["raw_text"])
            quality = parsed["manifest"].setdefault("quality", {})
            quality["reference_page_alignment"] = _align_reference_pages(parsed["references"], source["storage_path"])
            quality["reference_entries"] = len(parsed["references"])
            parsed["manifest"]["review_correction_action_ids"] = correction_ids
        candidate_dir = self.service.artifacts_root / job["paper_id"] / source["sha256"] / "review" / f"{job['job_id']}-{job['fencing_token']}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = candidate_dir / "candidate.json"
        raw = json.dumps(parsed, ensure_ascii=False, sort_keys=True).encode()
        with candidate_path.open("xb") as handle:
            handle.write(raw)
        review = {"kind": "PARSE_QUALITY", "file_version_id": source["file_version_id"], "pdf_sha256": source["sha256"],
                  "candidate": {"path": str(candidate_path), "sha256": hashlib.sha256(raw).hexdigest()},
                  "correction_action_ids": correction_ids}
        missing_references = (
            parsed.get("manifest", {}).get("quality", {})
            .get("reference_page_alignment", {}).get("missing_source_numbered_references", [])
        )
        if missing_references:
            raise HumanWait(
                f"Parser omitted numbered references present in PDF: {missing_references}", review=review,
            )
        if not parsed["references"] and self.reference_parser.available:
            parsed["references"] = self.reference_parser.extract(source["storage_path"])
            parsed["manifest"]["reference_fallback"] = "GROBID"
        if not file_integrity(dict(source)):
            raise HumanWait("Original PDF changed during parsing", review=review)
        published = self.service.publish_parse_result(
            job["collection_id"], job["paper_id"], source["file_version_id"],
            parser_name=parsed["parser"], parser_version=parsed["parser_version"],
            config={"method": "auto", "bridge": "v4"}, manifest=parsed["manifest"],
            blocks=parsed["blocks"], references=parsed["references"],
            job_id=job["job_id"], worker_id=self.worker_id, fencing_token=job["fencing_token"],
        )
        return published, []

    def _gateway(self) -> Any:
        if self.model is None:
            self.model = UnlimitedLLMGateway(self.root)
        return self.model

    def _handle_screen(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        paper = self.service.get_paper(job["paper_id"])
        collection = self.service.get_collection(job["collection_id"])
        frozen = self.service.screening_context(job["collection_id"], job["paper_id"])
        paper = {**paper, **frozen["paper"]}
        collection = {**collection, **frozen["collection"]}
        context_sha = digest(frozen)
        if payload.get("scope_version", frozen["collection"]["scope_version"]) != frozen["collection"]["scope_version"] or payload.get("screen_context_sha256", context_sha) != context_sha:
            raise HumanWait("Screening input changed after this task was requested")
        model_result = self._analyze(
            job, "screen",
            {"scope": collection["scope"], "title": paper["title"], "abstract": paper["abstract"]},
        )
        contract = model_result.pop("_contract")
        self.service.record_assessment(
            job["collection_id"], job["paper_id"], "SCREEN", model_result,
            model_result.get("evidence_quotes", []), rule_version=job["rule_version"],
            input_digest=job["input_digest"], model_tier="light",
            prompt_version=contract["prompt_version"], model_name=contract.get("actual_model"),
            job_id=job["job_id"], worker_id=self.worker_id, fencing_token=job["fencing_token"],
            expected_screen_context_sha256=context_sha,
        )
        self.service.release_deferred_references(job["collection_id"])
        next_jobs = []
        with transaction(self.service.db_path) as conn:
            membership = conn.execute(
                """SELECT discovery_kind FROM collection_memberships
                   WHERE collection_id=? AND paper_id=?""",
                (job["collection_id"], job["paper_id"]),
            ).fetchone()
        if membership is not None and membership["discovery_kind"] in {"CATALOG_SELECTION", "SEARCH"} and model_result.get("category") != "IRRELEVANT":
            next_jobs.append({"job_type": "LOCATE_PDF", "queue_class": "NETWORK",
                              "payload": {"doi": paper["doi"], "screen_context_sha256": context_sha},
                              "rule_version": "catalog-file-reuse-v1", "priority": 30})
        return {"assessment": model_result, "contract": contract, "screening_input": frozen}, next_jobs

    def _analyze(self, job, task, payload, parse_run_id=None):
        from .acquisition_model_calls import ModelSourceChanged, analyze
        from .durable_model_delivery import ModelRunPending, ModelRunStopped
        try:
            return analyze(self.service, self._gateway(), job, self.worker_id, task, payload, parse_run_id)
        except ModelRunPending as error:
            raise ResourceWait(str(error), retry_after=error.retry_after) from error
        except ModelRunStopped as error:
            raise HumanWait(str(error), review={'kind': 'MODEL_EXECUTION', 'router_run_id': error.run_id}) from error
        except ModelSourceChanged as error:
            with transaction(self.service.db_path) as conn:
                file = conn.execute("SELECT file_version_id FROM parse_runs WHERE parse_run_id=?", (parse_run_id,)).fetchone()
            raise HumanWait(str(error), review={"kind":"PDF_IDENTITY", "file_version_id":file[0] if file else None}) from error

    def _parse_blocks(self, parse_run_id: str, paper_id: str | None = None) -> list[dict[str, Any]]:
        with transaction(self.service.db_path) as conn:
            try:
                self.service._require_parse_source(conn, parse_run_id, paper_id)
            except ValueError as error:
                file = conn.execute("SELECT file_version_id FROM parse_runs WHERE parse_run_id=?", (parse_run_id,)).fetchone()
                raise HumanWait(str(error), review={"kind": "PDF_IDENTITY", "file_version_id": file[0] if file else None}) from error
            rows = conn.execute(
                "SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence",
                (parse_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _handle_quick_read(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        blocks = self._parse_blocks(payload["parse_run_id"], job["paper_id"])
        excerpts = [
            {"block_id": row["block_id"], "section": row["section"], "text": row["text"]}
            for row in blocks
        ]
        result = self._analyze(job, "quick_read", {"blocks": excerpts}, payload["parse_run_id"])
        contract = result.pop("_contract")
        self.service.record_assessment(
            job["collection_id"], job["paper_id"], "QUICK_READ", result,
            result.get("evidence_quotes", []), rule_version=job["rule_version"],
            input_digest=job["input_digest"], model_tier="light",
            prompt_version=contract["prompt_version"], model_name=contract.get("actual_model"),
            parse_run_id=payload["parse_run_id"], job_id=job["job_id"], worker_id=self.worker_id,
            fencing_token=job["fencing_token"],
        )
        next_jobs = []
        if result.get("deep_read_reasons"):
            next_jobs.append(
                {
                    "job_type": "SKELETON", "queue_class": "MODEL_SKELETON",
                    "payload": {
                        "parse_run_id": payload["parse_run_id"],
                        "reasons": result["deep_read_reasons"],
                    },
                    "rule_version": "skeleton-v1", "priority": 50,
                }
            )
        return {"card": result, "contract": contract}, next_jobs

    def _handle_skeleton(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        parse_run_id = payload.get("parse_run_id")
        if not parse_run_id:
            with transaction(self.service.db_path) as conn:
                row = conn.execute(
                    """SELECT pr.parse_run_id FROM parse_runs pr JOIN source_file_versions sf
                       ON sf.file_version_id=pr.file_version_id WHERE sf.paper_id=?
                       AND pr.status='SUCCEEDED' ORDER BY pr.completed_at DESC LIMIT 1""",
                    (job["paper_id"],),
                ).fetchone()
            if row is None:
                raise RuntimeError("Deep read requires a completed parse")
            parse_run_id = row["parse_run_id"]
        units = []
        for block in self._parse_blocks(parse_run_id, job["paper_id"]):
            unit: dict[str, Any] = {
                "block_id": block["block_id"], "page_number": block["page_number"],
                "section": block["section"], "raw_text": block["text"],
            }
            for layer in range(1, 5):
                task = f"skeleton_layer_{layer}"
                result = self._analyze(
                    job, task,
                    {
                        "raw_text": block["text"],
                        **{
                            f"layer{n}": unit[f"layer{n}"]
                            for n in range(1, layer)
                        },
                    },
                    parse_run_id,
                )
                unit.setdefault("layer_contracts", {})[str(layer)] = result.pop("_contract")
                if layer == 3:
                    from .skeleton_intent import INTENT_VERSION, validate_intent
                    if unit["layer_contracts"]["3"]["prompt_version"] == INTENT_VERSION:
                        validate_intent(result, block["text"])
                unit[f"layer{layer}"] = result
            units.append(unit)
        published = self.service.publish_skeleton_result(
            parse_run_id, units,
            prompt_version="paper-skeleton-v2-located-intent" if units and all(
                u["layer_contracts"]["3"]["prompt_version"] == "skeleton-l3-v2-located-intent"
                for u in units
            ) else "paper-skeleton-v1",
            model_name=next(iter({c.get("actual_model") for u in units for c in u["layer_contracts"].values()})) if len({c.get("actual_model") for u in units for c in u["layer_contracts"].values()}) == 1 else None, job_id=job["job_id"], worker_id=self.worker_id,
            fencing_token=job["fencing_token"],
        )
        return published, [
            {
                "job_type": "ASSESS", "queue_class": "MODEL_ASSESS",
                "payload": {
                    "parse_run_id": parse_run_id,
                    "skeleton_run_id": published["skeleton_run_id"],
                },
                "rule_version": "assessment-v1", "priority": 40,
            }
        ]

    def _handle_assess(
        self, job: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        blocks = self._parse_blocks(payload["parse_run_id"], job["paper_id"])
        result = self._analyze(
            job, "assessment", {"blocks": [{"id": b["block_id"], "text": b["text"]} for b in blocks]}, payload["parse_run_id"]
        )
        contract = result.pop("_contract")
        self.service.record_assessment(
            job["collection_id"], job["paper_id"], "CONTENT", result,
            result.get("evidence_quotes", []), rule_version=job["rule_version"],
            input_digest=job["input_digest"], model_tier="standard",
            prompt_version=contract["prompt_version"], model_name=contract.get("actual_model"),
            parse_run_id=payload["parse_run_id"], job_id=job["job_id"], worker_id=self.worker_id,
            fencing_token=job["fencing_token"],
        )
        return {"assessment": result, "contract": contract}, []


def main() -> None:
    parser = argparse.ArgumentParser(description="RSTV4 durable PaperPool worker")
    parser.add_argument("--root", default=os.environ.get("RSTV4_ROOT", "."))
    parser.add_argument("--role", choices=sorted(ROLE_QUEUES), required=True)
    parser.add_argument("--slot", default="1")
    parser.add_argument("--browser-bridge-port", type=int, default=8876)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    with instance_lock(root, args.role, args.slot):
        worker = AcquisitionWorker(root, args.role)
        if args.once:
            result = worker.run_once()
            print(json.dumps(result, ensure_ascii=False, default=str))
        else:
            bridge = None
            if args.role == "network" and args.slot == "1":
                from .browser_bridge import BrowserBridgeServer

                bridge = BrowserBridgeServer(worker.service, port=args.browser_bridge_port)
                threading.Thread(target=bridge.serve_forever, daemon=True).start()
            try:
                worker.run_forever()
            finally:
                if bridge is not None:
                    bridge.shutdown()
                    bridge.server_close()


if __name__ == "__main__":
    main()
