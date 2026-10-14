"""Explicit, version-bound review actions; saved opinions never approve a file."""

from __future__ import annotations

import getpass
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .acquisition import AcquisitionService, digest, stable_id, utc_now
from .database import transaction
from .models import StrictModel
from .source_review import invalidate_source, source_impact


class ReviewWordSelection(StrictModel):
    page_number: int = Field(ge=1)
    word_start: int = Field(ge=0)
    word_end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered_range(self):
        if not self.word_start <= self.word_end <= self.word_start + 500:
            raise ValueError("Select one complete reference on one PDF page")
        return self


class ReviewActionInput(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    action: Literal["APPROVE_IDENTITY", "REOPEN_IDENTITY", "RECHECK_PARSE"]
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=4000)
    reference_selections: list[ReviewWordSelection] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def explicit_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Add the reason for this review action")
        if self.action != "RECHECK_PARSE" and self.reference_selections:
            raise ValueError("Identity approval does not modify parser references")
        return self


def file_integrity(file: dict[str, Any]) -> bool:
    path = Path(file["storage_path"])
    try:
        if path.stat().st_size != file["size_bytes"]:
            return False
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == file["sha256"]
    except OSError:
        return False


class CatalogReviewWorkflow:
    def __init__(self, service: AcquisitionService):
        self.service = service
        self.db_path = service.db_path

    def _candidate(self, job: dict[str, Any]) -> tuple[dict, dict | None]:
        review = json.loads(job.get("result_json") or "{}").get("review", {})
        candidate = review.get("candidate")
        if not isinstance(candidate, dict):
            return {"available": False}, None
        path = Path(str(candidate.get("path") or "")).resolve()
        if not path.is_relative_to(self.service.artifacts_root.resolve()):
            return {"available": False, "problem": "Candidate is outside managed artifacts"}, None
        try:
            raw = path.read_bytes()
            if len(raw) > 50_000_000 or hashlib.sha256(raw).hexdigest() != candidate.get("sha256"):
                return {"available": False, "problem": "Original candidate changed"}, None
            parsed = json.loads(raw)
        except (OSError, ValueError):
            return {"available": False, "problem": "Original candidate is unavailable"}, None
        quality = parsed.get("manifest", {}).get("quality", {})
        return {"available": True, "sha256": candidate["sha256"],
                "quality": quality, "parser": parsed.get("parser"),
                "body_blocks": len(parsed.get("blocks", [])),
                "reference_entries": len(parsed.get("references", []))}, parsed

    def _context(self, conn: sqlite3.Connection, case_id: str) -> dict[str, Any]:
        source = conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=?", (case_id,)).fetchone()
        job = None
        if source is None:
            row = conn.execute("SELECT * FROM acquisition_jobs WHERE job_id=? AND job_type='PARSE_PDF'", (case_id,)).fetchone()
            if row is None:
                raise LookupError("Review case not found")
            job = dict(row)
            file_id = json.loads(job["input_json"]).get("file_version_id")
            source = conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=? AND paper_id=?",
                                  (file_id, job["paper_id"])).fetchone()
        if source is None:
            raise ValueError("The stopped task has no matching original PDF")
        file = dict(source)
        paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (file["paper_id"],)).fetchone()
        if paper is None:
            raise LookupError("Catalog paper not found")
        integrity = file_integrity(file)
        annotations = [dict(row) for row in conn.execute(
            "SELECT * FROM catalog_review_annotations WHERE case_id=? ORDER BY rowid DESC", (file["file_version_id"],))]
        findings = [dict(row) for row in conn.execute(
            "SELECT * FROM catalog_review_findings WHERE case_id=? ORDER BY rowid DESC", (case_id,))]
        latest = {}
        for annotation in annotations:
            latest.setdefault(annotation["field_name"], annotation)
        blocked = []
        for row in conn.execute("SELECT * FROM acquisition_jobs WHERE paper_id=? AND status='NEEDS_HUMAN' ORDER BY job_id", (file["paper_id"],)):
            value = dict(row)
            inputs = json.loads(value["input_json"])
            stopped = json.loads(value.get("result_json") or "{}").get("review", {})
            if ((value["job_type"] == "PARSE_PDF" and inputs.get("file_version_id") == file["file_version_id"])
                    or (stopped.get("kind") == "PDF_IDENTITY" and stopped.get("file_version_id") == file["file_version_id"])):
                blocked.append({**{key: value[key] for key in ["job_id", "collection_id", "job_type", "status", "fencing_token", "updated_at"]},
                                "review_kind": stopped.get("kind")})
        memberships = [dict(row) for row in conn.execute(
            "SELECT c.collection_id,c.name,c.status,c.revision FROM collection_memberships m "
            "JOIN collections c ON c.collection_id=m.collection_id WHERE m.paper_id=? ORDER BY c.collection_id",
            (file["paper_id"],))]
        quarantined = bool(conn.execute("SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (file["paper_id"],)).fetchone())
        candidate = self._candidate(job)[0] if job else None
        history = [dict(row) for row in conn.execute(
            "SELECT * FROM catalog_review_actions WHERE case_id=? ORDER BY rowid DESC", (case_id,))]
        context = {"case_id": case_id, "workspace_id": digest(str(self.db_path.resolve())),
                   "kind": "PARSER" if job else "PDF_IDENTITY",
                   "file": {key: file[key] for key in ["file_version_id", "paper_id", "sha256", "size_bytes", "identity_status"]},
                   "paper": {key: paper[key] for key in ["paper_id", "title", "doi", "canonical_key", "updated_at"]},
                   "integrity_verified": integrity, "quarantined": quarantined,
                   "latest_annotations": latest, "findings": findings, "blocked_jobs": blocked,
                   "collections": memberships, "candidate": candidate,
                   "job": {key: job[key] for key in ["job_id", "collection_id", "paper_id", "job_type", "status", "fencing_token", "updated_at", "last_error_detail", "result_json"]} if job else None,
                   "last_action_id": history[0]["action_id"] if history else None}
        context["file"]["validation"] = json.loads(file["validation_json"])
        context["file"]["created_at"] = file["created_at"]
        context["source_impact"] = source_impact(conn, file) if job is None else None
        context["context_sha256"] = digest(context)
        context["history"] = [self._decode(row) for row in history]
        context["allowed_actions"] = []
        if not job and file["identity_status"] == "VERIFIED" and not quarantined:
            context["allowed_actions"] = ["REOPEN_IDENTITY"]
        if integrity and not quarantined:
            if job and job["status"] == "NEEDS_HUMAN" and file["identity_status"] == "VERIFIED":
                context["allowed_actions"] = ["RECHECK_PARSE"]
            elif not job and file["identity_status"] == "NEEDS_REVIEW" and latest.get("PDF", {}).get("decision") != "WRONG_PDF":
                context["allowed_actions"] = ["APPROVE_IDENTITY"]
        return context

    @staticmethod
    def _decode(row: dict) -> dict:
        return {**{key: value for key, value in row.items() if not key.endswith("_json")},
                "request": json.loads(row["request_json"]), "context": json.loads(row["context_json"]),
                "result": json.loads(row["result_json"])}

    def context(self, case_id: str) -> dict:
        with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            return self._context(conn, case_id)

    def act(self, case_id: str, payload: ReviewActionInput,
            words: Callable[[str, int], list[dict]] | None = None) -> dict:
        request_json = json.dumps({"case_id": case_id, **payload.model_dump()}, ensure_ascii=False, sort_keys=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT * FROM catalog_review_actions WHERE request_id=?", (payload.request_id,)).fetchone()
            if prior:
                if prior["request_json"] != request_json:
                    raise ValueError("Review request ID belongs to a different decision")
                return self._decode(dict(prior))
            context = self._context(conn, case_id)
            if context["context_sha256"] != payload.expected_context_sha256:
                raise ValueError("Review source or task changed; compare the current case before confirming")
            if payload.action not in context["allowed_actions"]:
                raise ValueError("This review action is not available for the current file and task")
            file = dict(conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=?",
                                     (context["file"]["file_version_id"],)).fetchone())
            action_id = stable_id("review_action", payload.request_id)
            now = utc_now()
            if payload.action == "REOPEN_IDENTITY":
                conn.execute("UPDATE source_file_versions SET identity_status='NEEDS_REVIEW' WHERE file_version_id=? AND identity_status='VERIFIED'",
                             (file["file_version_id"],))
                result = {"status": "IDENTITY_REOPENED", "file_version_id": file["file_version_id"],
                          **invalidate_source(conn, context["source_impact"], file, action_id, payload.reason, now),
                          "scientific_approval_restored": False}
            elif payload.action == "APPROVE_IDENTITY":
                validation = self.service._validate_pdf_identity(Path(file["storage_path"]), file["paper_id"])
                if not file_integrity(file):
                    raise ValueError("Original PDF changed while checking its identity")
                result = {"status": "IDENTITY_STILL_NEEDS_REVIEW", "validation": validation, "resumed_jobs": [], "parse_jobs": []}
                if validation["identity_status"] == "VERIFIED":
                    conn.execute("UPDATE source_file_versions SET identity_status='VERIFIED',validation_json=? WHERE file_version_id=? AND identity_status='NEEDS_REVIEW'",
                                 (json.dumps(validation, ensure_ascii=False, sort_keys=True), file["file_version_id"]))
                    for stopped in context["blocked_jobs"]:
                        if stopped["review_kind"] != "PDF_IDENTITY":
                            continue
                        job_row = conn.execute("SELECT result_json FROM acquisition_jobs WHERE job_id=?", (stopped["job_id"],)).fetchone()
                        old_review = json.loads(job_row[0] or "{}").get("review", {})
                        prior_status = old_review.get("previous_status")
                        status = prior_status if prior_status and prior_status not in {"READY", "RUNNING"} else "READY"
                        restored = old_review.get("previous_result", {"review": old_review})
                        conn.execute("UPDATE acquisition_jobs SET status=?,available_at=?,updated_at=?,last_error_code=?,last_error_detail=?,result_json=? WHERE job_id=? AND status='NEEDS_HUMAN' AND fencing_token=? AND updated_at=?",
                                     (status, now, now, old_review.get("previous_error_code") if status!='READY' else None,
                                      old_review.get("previous_error_detail") if status!='READY' else None,
                                      json.dumps(restored, ensure_ascii=False), stopped["job_id"], stopped["fencing_token"], stopped["updated_at"]))
                        if status == "READY":
                            result["resumed_jobs"].append(stopped["job_id"])
                    for collection in context["collections"]:
                        result["parse_jobs"].append(self.service._enqueue(conn, collection_id=collection["collection_id"], paper_id=file["paper_id"],
                            job_type="PARSE_PDF", queue_class="PARSER", payload={"file_version_id": file["file_version_id"]}, rule_version="parser-v1", priority=80))
                    result["status"] = "APPROVED_IDENTITY"
            else:
                job = dict(conn.execute("SELECT * FROM acquisition_jobs WHERE job_id=?", (case_id,)).fetchone())
                candidate_summary, _ = self._candidate(job)
                missing = candidate_summary.get("quality", {}).get("reference_page_alignment", {}).get("missing_source_numbered_references", [])
                corrections = []
                numbers = set()
                for selection in payload.reference_selections:
                    if words is None or not candidate_summary.get("available"):
                        raise ValueError("Original parser candidate and PDF words are required for a correction")
                    source_words = words(file["file_version_id"], selection.page_number)
                    if selection.word_end >= len(source_words):
                        raise ValueError("Reference selection is outside the original PDF page")
                    text = " ".join(str(word["text"]) for word in source_words[selection.word_start:selection.word_end + 1])
                    numbered = re.match(r"^\s*(?:\[(\d+)\]|(\d+)\.)\s", text)
                    number = int(next(value for value in numbered.groups() if value)) if numbered else None
                    if number not in missing or number in numbers:
                        raise ValueError("Select one of the original missing numbered references")
                    numbers.add(number)
                    corrections.append({"number": number, "raw_text": text, "page_number": selection.page_number,
                                        "location": {"source": "human_original_pdf_selection", "file_version_id": file["file_version_id"],
                                                     "pdf_sha256": file["sha256"], "review_action_id": action_id, **selection.model_dump()}})
                review = json.loads(job.get("result_json") or "{}").get("review", {})
                action_ids = list(review.get("correction_action_ids", []))
                if corrections:
                    action_ids.append(action_id)
                result = {"status": "PARSE_RECHECK_QUEUED", "job_id": case_id, "file_version_id": file["file_version_id"],
                          "pdf_sha256": file["sha256"], "corrections": corrections, "correction_action_ids": action_ids,
                          "quality_approved": False}
                conn.execute("UPDATE acquisition_jobs SET status='READY',available_at=?,updated_at=?,last_error_code=NULL,last_error_detail=NULL,result_json=? WHERE job_id=? AND status='NEEDS_HUMAN' AND fencing_token=? AND updated_at=?",
                             (now, now, json.dumps({"review": {**review, "correction_action_ids": action_ids}}, ensure_ascii=False),
                              case_id, job["fencing_token"], job["updated_at"]))
            if payload.action != "REOPEN_IDENTITY" and not file_integrity(file):
                raise ValueError("Original PDF changed before committing review")
            audit_context = {key: value for key, value in context.items() if key not in {"history", "allowed_actions"}}
            conn.execute("INSERT INTO catalog_review_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (action_id, payload.request_id, case_id, file["file_version_id"], payload.action, getpass.getuser(), payload.reason,
                          request_json, json.dumps(audit_context, ensure_ascii=False, sort_keys=True), json.dumps(result, ensure_ascii=False, sort_keys=True),
                          context["last_action_id"], now))
            return self._decode(dict(conn.execute("SELECT * FROM catalog_review_actions WHERE action_id=?", (action_id,)).fetchone()))
