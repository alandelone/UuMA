"""Source-anchored human annotations that correct Catalog identity fields."""

from __future__ import annotations

import getpass
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .acquisition import normalize_doi, normalize_title
from .database import CATALOG_REVIEW_SCHEMA, transaction

DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s]+", re.IGNORECASE)


class ReviewAnnotationInput(BaseModel):
    submission_id: str = Field(min_length=8, max_length=100)
    field_name: Literal["DOI", "TITLE", "PDF"]
    decision: Literal["FOUND", "ABSENT", "WRONG_PDF", "REOPEN"]
    page_number: int | None = Field(default=None, ge=1)
    word_start: int | None = Field(default=None, ge=0)
    word_end: int | None = Field(default=None, ge=0)
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> ReviewAnnotationInput:
        self.comment = self.comment.strip()
        if self.decision == "FOUND":
            if self.field_name not in {"DOI", "TITLE"}:
                raise ValueError("A selected passage must be marked as DOI or TITLE")
            if self.page_number is None or self.word_start is None or self.word_end is None:
                raise ValueError("A selected passage needs its page and word positions")
            if self.word_end < self.word_start or self.word_end - self.word_start > 100:
                raise ValueError("Selected word range is invalid or too long")
        elif self.decision == "ABSENT":
            if self.field_name != "DOI":
                raise ValueError("Only DOI can be marked absent from the PDF")
        elif self.field_name != "PDF":
            raise ValueError("PDF identity decisions apply to the complete file")
        if self.decision != "FOUND" and any(
            value is not None for value in (self.page_number, self.word_start, self.word_end)
        ):
            raise ValueError("This decision does not use a text selection")
        return self


def list_review_annotations(path: Path, case_id: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_review_annotations'"
        ).fetchone() is None:
            return []
        return [dict(row) for row in conn.execute(
            """SELECT * FROM catalog_review_annotations WHERE case_id=?
               ORDER BY rowid DESC""",
            (case_id,),
        )]


def _latest_for_field(
    conn: sqlite3.Connection, case_id: str, field_name: str
) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT * FROM catalog_review_annotations
           WHERE case_id=? AND field_name=? ORDER BY rowid DESC LIMIT 1""",
        (case_id, field_name),
    ).fetchone()


def _insert_event(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    event_id = f"review_annotation_{uuid4().hex}"
    prior = _latest_for_field(conn, values["case_id"], values["field_name"])
    conn.execute(
        """INSERT INTO catalog_review_annotations(
           annotation_id,submission_id,case_id,paper_id,file_version_id,field_name,
           decision,selected_text,page_number,word_start,word_end,comment,value_before,
           value_after,canonical_key_before,canonical_key_after,reviewer_label,
           supersedes_annotation_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id, values["submission_id"], values["case_id"], values["paper_id"],
            values["file_version_id"], values["field_name"], values["decision"],
            values.get("selected_text"), values.get("page_number"), values.get("word_start"),
            values.get("word_end"), values.get("comment", ""), values.get("value_before"),
            values.get("value_after"), values.get("canonical_key_before"),
            values.get("canonical_key_after"), getpass.getuser(),
            prior["annotation_id"] if prior else None, datetime.now(UTC).isoformat(),
        ),
    )
    return dict(conn.execute(
        "SELECT * FROM catalog_review_annotations WHERE annotation_id=?", (event_id,)
    ).fetchone())


def _restore_field(
    conn: sqlite3.Connection, case_id: str, paper_id: str, field_name: str, now: str
) -> tuple[str | None, str | None, str | None, str | None] | None:
    active = []
    for row in conn.execute(
        """SELECT * FROM catalog_review_annotations WHERE case_id=? AND field_name=?
           ORDER BY rowid DESC""",
        (case_id, field_name),
    ):
        if row["decision"] != "FOUND":
            break
        active.append(row)
    if not active:
        return None
    changed = [row for row in active if row["value_before"] != row["value_after"]]
    if not changed:
        return None
    earliest = changed[-1]
    original = earliest["value_before"]
    column = "doi" if field_name == "DOI" else "title"
    paper = conn.execute(
        f"SELECT {column},canonical_key FROM papers WHERE paper_id=?", (paper_id,)
    ).fetchone()
    current = paper[column]
    if current != active[0]["value_after"]:
        raise ValueError("Catalog changed after this annotation; refresh before reversing it")
    if field_name == "DOI":
        original_key = earliest["canonical_key_before"]
        if not original_key:
            raise ValueError("Original DOI identity key is unavailable")
        conn.execute(
            "UPDATE papers SET doi=?,canonical_key=?,updated_at=? WHERE paper_id=?",
            (original, original_key, now, paper_id),
        )
        conn.execute(
            "UPDATE paper_identities SET status='SUPERSEDED' WHERE paper_id=? AND scheme='DOI'",
            (paper_id,),
        )
        if original:
            conn.execute(
                """UPDATE paper_identities SET status='CONFIRMED'
                   WHERE paper_id=? AND scheme='DOI' AND normalized_value=?""",
                (paper_id, original),
            )
        return current, original, paper["canonical_key"], original_key
    conn.execute(
        "UPDATE papers SET title=?,normalized_title=?,updated_at=? WHERE paper_id=?",
        (original, normalize_title(original), now, paper_id),
    )
    return current, original, None, None


def record_review_annotation(
    path: Path,
    case_id: str,
    annotation: ReviewAnnotationInput,
    source_words: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not path.is_file():
        raise LookupError("Catalog database is unavailable")
    with transaction(path) as conn:
        conn.executescript(CATALOG_REVIEW_SCHEMA)
        existing = conn.execute(
            "SELECT * FROM catalog_review_annotations WHERE submission_id=?",
            (annotation.submission_id,),
        ).fetchone()
        if existing is not None:
            if existing["case_id"] != case_id:
                raise ValueError("Submission ID belongs to another review case")
            return dict(existing)
        file = conn.execute(
            """SELECT paper_id,file_version_id,identity_status
               FROM source_file_versions WHERE file_version_id=?""",
            (case_id,),
        ).fetchone()
        if file is None:
            raise LookupError("PDF review case not found")
        if file["identity_status"] != "NEEDS_REVIEW":
            raise ValueError("This PDF no longer needs review")
        if conn.execute(
            "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (file["paper_id"],)
        ).fetchone():
            raise ValueError("Quarantined papers cannot be corrected here")
        paper = conn.execute(
            "SELECT * FROM papers WHERE paper_id=?", (file["paper_id"],)
        ).fetchone()
        if paper is None:
            raise LookupError("Catalog paper not found")
        pdf_decision = _latest_for_field(conn, case_id, "PDF")
        if (pdf_decision and pdf_decision["decision"] == "WRONG_PDF"
                and annotation.decision in {"FOUND", "ABSENT"}):
            raise ValueError("Reopen the PDF mismatch before annotating this file")

        selected_text: str | None = None
        applied_value: str | None = None
        value_before: str | None = None
        canonical_before: str | None = None
        canonical_after: str | None = None
        now = datetime.now(UTC).isoformat()
        if annotation.decision == "FOUND":
            if source_words is None or annotation.word_end >= len(source_words):
                raise ValueError("Selected words are not on this PDF page")
            selected_text = " ".join(
                str(word["text"]) for word in source_words[
                    annotation.word_start:annotation.word_end + 1
                ]
            ).strip()
            if annotation.field_name == "DOI":
                matches = DOI_IN_TEXT.findall(selected_text)
                if len(matches) != 1:
                    raise ValueError("Select one complete DOI in the PDF")
                applied_value = normalize_doi(matches[0])
                if not applied_value:
                    raise ValueError("The selected text is not a DOI")
                value_before = paper["doi"]
                canonical_before = paper["canonical_key"]
                canonical_after = f"doi:{applied_value}"
                collision = conn.execute(
                    """SELECT paper_id FROM papers WHERE (doi=? OR canonical_key=?)
                       AND paper_id<>?""",
                    (applied_value, f"doi:{applied_value}", paper["paper_id"]),
                ).fetchone()
                identity_collision = conn.execute(
                    """SELECT paper_id FROM paper_identities
                       WHERE scheme='DOI' AND normalized_value=? AND paper_id<>?""",
                    (applied_value, paper["paper_id"]),
                ).fetchone()
                if collision or identity_collision:
                    raise ValueError("This DOI already belongs to another Catalog paper")
                if applied_value != value_before:
                    conn.execute(
                        """UPDATE papers SET doi=?,canonical_key=?,updated_at=?
                           WHERE paper_id=?""",
                        (applied_value, canonical_after, now, paper["paper_id"]),
                    )
                    conn.execute(
                        """UPDATE paper_identities SET status='SUPERSEDED'
                           WHERE paper_id=? AND scheme='DOI' AND normalized_value<>?""",
                        (paper["paper_id"], applied_value),
                    )
                identity = conn.execute(
                    """SELECT identity_id FROM paper_identities
                       WHERE scheme='DOI' AND normalized_value=?""",
                    (applied_value,),
                ).fetchone()
                if identity is None:
                    conn.execute(
                        """INSERT INTO paper_identities
                           (identity_id,paper_id,scheme,normalized_value,status,source,observed_at)
                           VALUES(?,?,'DOI',?,'CONFIRMED','human_pdf_annotation',?)""",
                        (f"identity_{uuid4().hex}", paper["paper_id"], applied_value, now),
                    )
                else:
                    conn.execute(
                        """UPDATE paper_identities SET status='CONFIRMED',
                           source='human_pdf_annotation',observed_at=? WHERE identity_id=?""",
                        (now, identity["identity_id"]),
                    )
            else:
                applied_value = " ".join(selected_text.split())
                if len(normalize_title(applied_value).split()) < 2 or len(applied_value) > 500:
                    raise ValueError("Select the complete paper title")
                value_before = paper["title"]
                if applied_value != value_before:
                    conn.execute(
                        """UPDATE papers SET title=?,normalized_title=?,updated_at=?
                           WHERE paper_id=?""",
                        (applied_value, normalize_title(applied_value), now,
                         paper["paper_id"]),
                    )
        elif annotation.decision == "ABSENT":
            restored = _restore_field(conn, case_id, paper["paper_id"], "DOI", now)
            if restored:
                value_before, applied_value, canonical_before, canonical_after = restored
            else:
                value_before = applied_value = paper["doi"]
        elif annotation.decision == "WRONG_PDF":
            for field_name in ("DOI", "TITLE"):
                latest = _latest_for_field(conn, case_id, field_name)
                if latest is None or latest["decision"] != "FOUND":
                    continue
                restored = _restore_field(conn, case_id, paper["paper_id"], field_name, now)
                _insert_event(conn, {
                    "submission_id": f"internal-revert-{uuid4().hex}",
                    "case_id": case_id, "paper_id": paper["paper_id"],
                    "file_version_id": file["file_version_id"],
                    "field_name": field_name, "decision": "REVERTED",
                    "comment": "The PDF was marked as belonging to another paper.",
                    "value_before": restored[0] if restored else latest["value_after"],
                    "value_after": restored[1] if restored else latest["value_after"],
                    "canonical_key_before": restored[2] if restored else None,
                    "canonical_key_after": restored[3] if restored else None,
                })
        return _insert_event(conn, {
            "submission_id": annotation.submission_id, "case_id": case_id,
            "paper_id": paper["paper_id"], "file_version_id": file["file_version_id"],
            "field_name": annotation.field_name, "decision": annotation.decision,
            "selected_text": selected_text, "page_number": annotation.page_number,
            "word_start": annotation.word_start, "word_end": annotation.word_end,
            "comment": annotation.comment, "value_before": value_before,
            "value_after": applied_value, "canonical_key_before": canonical_before,
            "canonical_key_after": canonical_after,
        })
