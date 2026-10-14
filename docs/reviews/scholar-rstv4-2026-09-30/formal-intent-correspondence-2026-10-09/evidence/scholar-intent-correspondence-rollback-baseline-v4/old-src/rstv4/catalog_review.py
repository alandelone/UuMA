"""Append-only human findings for Catalog PDF and parser review cases."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .database import CATALOG_REVIEW_SCHEMA, transaction


class ReviewFindingInput(BaseModel):
    submission_id: str = Field(min_length=8, max_length=100)
    issue_type: Literal["DOI", "TITLE", "PARSER"]
    assessment: Literal["AUTO_CHECK_MISSED", "CATALOG_CORRECTION", "PDF_MISMATCH", "UNSURE"]
    proposed_value: str | None = Field(default=None, max_length=500)
    evidence_page: int | None = Field(default=None, ge=1)
    evidence_quote: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=4000)
    reviewer_label: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_review(self) -> ReviewFindingInput:
        self.reviewer_label = self.reviewer_label.strip()
        self.proposed_value = self.proposed_value.strip() if self.proposed_value else None
        self.evidence_quote = self.evidence_quote.strip() if self.evidence_quote else None
        self.note = self.note.strip() if self.note else None
        if not self.reviewer_label:
            raise ValueError("Reviewer name is required")
        if self.assessment == "CATALOG_CORRECTION" and not self.proposed_value:
            raise ValueError("A corrected value is required for a Catalog correction")
        if not self.evidence_quote and not self.note:
            raise ValueError("Add an original-text quote or a note before saving")
        return self


def _case_target(conn: sqlite3.Connection, case_id: str) -> tuple[str, str | None, str]:
    file = conn.execute(
        """SELECT paper_id,file_version_id,identity_status FROM source_file_versions
           WHERE file_version_id=?""",
        (case_id,),
    ).fetchone()
    if file is not None:
        if file["identity_status"] != "NEEDS_REVIEW":
            raise ValueError("This PDF no longer needs review")
        return file["paper_id"], file["file_version_id"], "PDF_IDENTITY"
    job = conn.execute(
        """SELECT paper_id,status,input_json,job_type FROM acquisition_jobs WHERE job_id=?""",
        (case_id,),
    ).fetchone()
    if job is None:
        raise LookupError("Review case not found")
    if job["status"] != "NEEDS_HUMAN":
        raise ValueError("This parser job no longer needs a human")
    if job["job_type"] != "PARSE_PDF":
        raise ValueError("This task is not a parser review case")
    return job["paper_id"], json.loads(job["input_json"]).get("file_version_id"), "PARSER"


def list_review_findings(path: Path, case_id: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_review_findings'"
        ).fetchone()
        if not exists:
            return []
        return [dict(row) for row in conn.execute(
            """SELECT * FROM catalog_review_findings WHERE case_id=?
               ORDER BY created_at DESC, finding_id DESC""",
            (case_id,),
        )]


def record_review_finding(
    path: Path, case_id: str, finding: ReviewFindingInput
) -> dict[str, Any]:
    if not path.is_file():
        raise LookupError("Catalog database is unavailable")
    with transaction(path) as conn:
        conn.executescript(CATALOG_REVIEW_SCHEMA)
        prior_submission = conn.execute(
            "SELECT * FROM catalog_review_findings WHERE submission_id=?",
            (finding.submission_id,),
        ).fetchone()
        if prior_submission is not None:
            if prior_submission["case_id"] != case_id:
                raise ValueError("Submission ID belongs to another review case")
            if any(prior_submission[key] != value for key, value in finding.model_dump().items()):
                raise ValueError("Submission ID belongs to a different review finding")
            return dict(prior_submission)
        paper_id, file_version_id, case_kind = _case_target(conn, case_id)
        if case_kind == "PDF_IDENTITY" and finding.issue_type not in {"DOI", "TITLE"}:
            raise ValueError("PDF identity cases accept DOI or TITLE findings")
        if case_kind == "PARSER" and finding.issue_type != "PARSER":
            raise ValueError("Parser cases accept PARSER findings")
        if finding.evidence_page is not None and file_version_id is None:
            raise ValueError("This case has no PDF page to cite")
        prior = conn.execute(
            """SELECT finding_id FROM catalog_review_findings
               WHERE case_id=? AND issue_type=? ORDER BY created_at DESC, finding_id DESC LIMIT 1""",
            (case_id, finding.issue_type),
        ).fetchone()
        finding_id = f"review_finding_{uuid4().hex}"
        conn.execute(
            """INSERT INTO catalog_review_findings(
               finding_id,submission_id,case_id,paper_id,file_version_id,issue_type,
               assessment,proposed_value,evidence_page,evidence_quote,note,reviewer_label,
               supersedes_finding_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                finding_id, finding.submission_id, case_id, paper_id, file_version_id,
                finding.issue_type, finding.assessment, finding.proposed_value,
                finding.evidence_page, finding.evidence_quote, finding.note,
                finding.reviewer_label, prior["finding_id"] if prior else None,
                datetime.now(UTC).isoformat(),
            ),
        )
        return dict(conn.execute(
            "SELECT * FROM catalog_review_findings WHERE finding_id=?", (finding_id,)
        ).fetchone())
