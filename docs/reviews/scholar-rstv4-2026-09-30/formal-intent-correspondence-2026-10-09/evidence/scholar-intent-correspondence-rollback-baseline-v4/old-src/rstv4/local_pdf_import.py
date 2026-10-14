"""Durable, reviewable intake of user-owned local PDF directories."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .acquisition import DOI_PATTERN, digest, normalize_doi, normalize_title, stable_id, utc_now
from .database import transaction
from .models import LocalPdfImportInput

if TYPE_CHECKING:
    from .acquisition import AcquisitionService


_RECALL_ON_DATA_ACCESS = 0x400000
_RECALL_ON_OPEN = 0x40000
_OFFLINE = 0x1000


def _candidate_title(path: Path) -> str:
    title = re.sub(r"^[!\-\s]+", "", path.stem).replace("_", " ")
    return " ".join(title.split())[:500]


class LocalPdfImporter:
    def __init__(self, service: AcquisitionService) -> None:
        self.service = service

    def import_directories(self, payload: LocalPdfImportInput) -> dict[str, Any]:
        roots = [Path(value).expanduser().resolve() for value in payload.directories]
        for root in roots:
            if not root.is_dir():
                raise NotADirectoryError(root)
        discovered = 0
        for root in roots:
            for directory, subdirectories, names in os.walk(root):
                subdirectories[:] = [
                    name for name in subdirectories if name.casefold() != "pdfparser"
                ]
                for name in names:
                    if not name.lower().endswith(".pdf"):
                        continue
                    path = Path(directory) / name
                    if path.is_symlink():
                        continue
                    try:
                        size = path.stat().st_size
                    except OSError:
                        size = -1
                    self._stage(path, root, size)
                    discovered += 1

        with transaction(self.service.db_path) as conn:
            waiting = conn.execute(
                "SELECT source_path FROM local_pdf_imports WHERE status='WAITING_LOCAL_FILE'"
            ).fetchall()
        for row in waiting:
            path = Path(row["source_path"])
            try:
                attributes = getattr(path.stat(), "st_file_attributes", 0)
            except OSError:
                continue
            if not attributes & (_RECALL_ON_DATA_ACCESS | _RECALL_ON_OPEN | _OFFLINE):
                self._set_status(path, "DISCOVERED")

        processed = 0
        with transaction(self.service.db_path) as conn:
            candidates = conn.execute(
                """SELECT source_path FROM local_pdf_imports
                   WHERE status='DISCOVERED' ORDER BY source_path LIMIT ?""",
                (payload.max_files,),
            ).fetchall()
        for row in candidates:
            self._process(Path(row["source_path"]))
            processed += 1
        return {"discovered": discovered, "processed": processed, **self.status()}

    def status(self) -> dict[str, Any]:
        with transaction(self.service.db_path) as conn:
            rows = conn.execute(
                "SELECT status,count(*) AS count FROM local_pdf_imports GROUP BY status"
            ).fetchall()
            roots = conn.execute(
                """SELECT root_path,status,count(*) AS count FROM local_pdf_imports
                   GROUP BY root_path,status ORDER BY root_path,status"""
            ).fetchall()
        return {
            "total": sum(row["count"] for row in rows),
            "statuses": {row["status"]: row["count"] for row in rows},
            "by_directory": [dict(row) for row in roots],
        }

    def quarantine_parser_outputs(self, root_path: str) -> dict[str, int]:
        """Hide already staged parser derivatives without erasing their audit trail."""
        root = Path(root_path).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        parser_root = root / "pdfparser"
        with transaction(self.service.db_path) as conn:
            rows = conn.execute(
                """SELECT source_path,paper_id FROM local_pdf_imports
                   WHERE root_path=? AND source_path LIKE ?""",
                (str(root), str(parser_root) + os.sep + "%"),
            ).fetchall()
            quarantined = 0
            for row in rows:
                paper_id = row["paper_id"]
                if paper_id is not None:
                    other = conn.execute(
                        """SELECT 1 FROM local_pdf_imports WHERE paper_id=?
                           AND source_path NOT LIKE ? LIMIT 1""",
                        (paper_id, str(parser_root) + os.sep + "%"),
                    ).fetchone()
                    if other is None:
                        inserted = conn.execute(
                            """INSERT OR IGNORE INTO catalog_quarantine
                               VALUES(?,?,?,?)""",
                            (paper_id, "PARSER_DERIVATIVE", row["source_path"], utc_now()),
                        )
                        quarantined += inserted.rowcount
                conn.execute(
                    """UPDATE local_pdf_imports SET status='EXCLUDED_DERIVATIVE',
                       detail_json=?,updated_at=? WHERE source_path=?""",
                    (
                        json.dumps({"reason": "Parser output, not source paper"}),
                        utc_now(), row["source_path"],
                    ),
                )
        return {"excluded_files": len(rows), "quarantined_papers": quarantined}

    def _stage(self, path: Path, root: Path, size: int) -> None:
        now = utc_now()
        with transaction(self.service.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO local_pdf_imports
                   (source_path,root_path,size_bytes,sha256,title_candidate,doi_candidate,
                    paper_id,file_version_id,status,detail_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,NULL,NULL,'DISCOVERED','{}',?,?)""",
                (str(path), str(root), size, None, _candidate_title(path), None, now, now),
            )

    def _set_status(
        self, path: Path, status: str, *, detail: dict[str, Any] | None = None,
        sha256: str | None = None, paper_id: str | None = None,
        file_version_id: str | None = None,
    ) -> None:
        with transaction(self.service.db_path) as conn:
            conn.execute(
                """UPDATE local_pdf_imports SET status=?,detail_json=?,
                   sha256=COALESCE(?,sha256),paper_id=COALESCE(?,paper_id),
                   file_version_id=COALESCE(?,file_version_id),updated_at=?
                   WHERE source_path=?""",
                (
                    status, json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
                    sha256, paper_id, file_version_id, utc_now(), str(path),
                ),
            )

    def _process(self, path: Path) -> None:
        try:
            stat = path.stat()
            attributes = getattr(stat, "st_file_attributes", 0)
            if attributes & (_RECALL_ON_DATA_ACCESS | _RECALL_ON_OPEN | _OFFLINE):
                self._set_status(path, "WAITING_LOCAL_FILE", detail={"reason": "iCloud file not local"})
                return
            if stat.st_size > 100 * 1024 * 1024:
                self._set_status(path, "NEEDS_REVIEW", detail={"reason": "PDF exceeds 100 MiB"})
                return
            with path.open("rb") as stream:
                head = stream.read(1024)
                stream.seek(max(0, stat.st_size - 2048))
                tail = stream.read()
            if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
                self._set_status(path, "NEEDS_REVIEW", detail={"reason": "Invalid or incomplete PDF"})
                return
            sha256 = self.service._file_digest(path)
            with transaction(self.service.db_path) as conn:
                matches = conn.execute(
                    """SELECT file_version_id,paper_id FROM source_file_versions
                       WHERE sha256=? ORDER BY file_version_id""",
                    (sha256,),
                ).fetchall()
            paper_ids = {row["paper_id"] for row in matches}
            if len(paper_ids) == 1:
                match = matches[0]
                self._set_status(
                    path, "ALREADY_CATALOGED", sha256=sha256,
                    paper_id=match["paper_id"], file_version_id=match["file_version_id"],
                )
                return
            if len(paper_ids) > 1:
                self._set_status(
                    path, "NEEDS_REVIEW", sha256=sha256,
                    detail={"reason": "Same PDF is assigned to multiple catalog papers"},
                )
                return
            title = _candidate_title(path)
            if not title:
                self._set_status(path, "NEEDS_REVIEW", sha256=sha256,
                                 detail={"reason": "No title candidate"})
                return
            doi_match = DOI_PATTERN.search(path.stem)
            doi = normalize_doi(doi_match.group(0)) if doi_match else None
            paper_id = self._resolve_paper(title, doi)
            observation = {"title_candidate": title, "doi_candidate": doi,
                           "source_path": str(path), "sha256": sha256}
            with transaction(self.service.db_path) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO metadata_observations
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        stable_id("metadata", "LOCAL_PDF_FILENAME", str(path), sha256),
                        paper_id, "LOCAL_PDF_FILENAME", utc_now(), "CANDIDATE",
                        json.dumps(observation, ensure_ascii=False, sort_keys=True),
                        digest(observation),
                    ),
                )
            registered = self.service._register_unscoped_pdf(
                paper_id, path, acquisition_method="local-pdf-directory"
            )
            status = (
                "IMPORTED_VERIFIED" if registered["identity_status"] == "VERIFIED"
                else "IMPORTED_NEEDS_REVIEW"
            )
            self._set_status(
                path, status, sha256=sha256, paper_id=paper_id,
                file_version_id=registered["file_version_id"],
                detail={"identity_status": registered["identity_status"]},
            )
        except (OSError, ValueError, sqlite3.Error) as exc:
            self._set_status(path, "FAILED", detail={"error": str(exc)[:500]})

    def _resolve_paper(self, title: str, doi: str | None) -> str:
        normalized = normalize_title(title)
        with transaction(self.service.db_path) as conn:
            if doi:
                row = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (doi,)).fetchone()
                if row:
                    return str(row["paper_id"])
            rows = conn.execute(
                "SELECT paper_id FROM papers WHERE normalized_title=?", (normalized,)
            ).fetchall()
        if len(rows) == 1:
            return str(rows[0]["paper_id"])
        return self.service._upsert_paper(title=title, doi=doi, authors=[], year=None)
