from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import transaction


EVIDENCE_INTENTS = {
    "Claim",
    "Bold_Claim",
    "Objective_Finding",
    "Result_Highlight",
    "Critical_Evaluation",
    "Boundary_Condition",
    "Research_Gap",
    "Future_Work",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_digest(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    value = hashlib.sha256()
    with candidate.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class LegacyPaperPoolAdapter:
    """Read validated legacy PaperPool rows into the canonical FieldKG build."""

    def __init__(self, scholar_db: Path) -> None:
        self.scholar_db = scholar_db

    def import_batch(
        self, build_id: str, database_path: str | Path, paper_ids: list[int] | None = None
    ) -> dict[str, Any]:
        source_path = Path(database_path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"PaperPool database does not exist: {source_path}")
        with sqlite3.connect(source_path) as source:
            source.row_factory = sqlite3.Row
            query = "SELECT * FROM paper"
            params: list[Any] = []
            if paper_ids:
                query += f" WHERE id IN ({','.join('?' for _ in paper_ids)})"
                params.extend(paper_ids)
            rows = source.execute(query, params).fetchall()
        imported = skipped = 0
        details: list[dict[str, Any]] = []
        for row in rows:
            try:
                result = self._import_row(build_id, dict(row), source_path)
                imported += int(result["status"] == "IMPORTED")
                skipped += int(result["status"] == "SKIPPED")
                details.append(result)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                skipped += 1
                details.append({"legacy_id": row["id"], "status": "SKIPPED", "detail": str(exc)})
        return {"build_id": build_id, "imported": imported, "skipped": skipped, "papers": details}

    def _import_row(self, build_id: str, row: dict[str, Any], source_path: Path) -> dict[str, Any]:
        semantics = row.get("Pp_minced_semantics")
        if isinstance(semantics, str):
            semantics = json.loads(semantics)
        if isinstance(semantics, dict):
            semantics = semantics.get("semantics", [])
        if not isinstance(semantics, list) or not semantics:
            raise ValueError("Pp_minced_semantics is empty or invalid")
        title = str(row.get("title") or "").strip()
        if not title:
            raise ValueError("paper title is missing")
        doi = str(row.get("DOI") or "").strip() or None
        normalized = "".join(character for character in title.casefold() if character.isalnum())
        canonical_key = f"doi:{doi.casefold()}" if doi else f"title:{digest(normalized)}"
        paper_id = stable_id("paper", canonical_key)
        parsed = row.get("ext") or row.get("Pp_txt_dict")
        pdf_path = row.get("file")
        pdf_sha = file_digest(pdf_path)
        parsed_sha = digest(parsed) if parsed else None
        version_key = [paper_id, pdf_sha, parsed_sha, str(source_path), row["id"]]
        paper_version_id = stable_id("paper_version", *version_key)
        skeleton_digest = digest(semantics)
        skeleton_id = stable_id("skeleton", paper_version_id, skeleton_digest)
        timestamp = now()
        with transaction(self.scholar_db) as conn:
            build = conn.execute("SELECT field_id FROM fieldkg_builds WHERE build_id=?", (build_id,)).fetchone()
            if build is None:
                raise ValueError(f"Unknown FieldKG build: {build_id}")
            authors = row.get("authors")
            if isinstance(authors, str):
                try:
                    authors = json.loads(authors)
                except json.JSONDecodeError:
                    authors = [authors]
            conn.execute(
                """INSERT INTO papers(
                   paper_id,canonical_key,doi,normalized_title,title,authors_json,published_year,
                   abstract,landing_url,pdf_url,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(canonical_key) DO UPDATE SET updated_at=excluded.updated_at""",
                (
                    paper_id, canonical_key, doi, normalized, title, json.dumps(authors or []),
                    int(row["year"]) if str(row.get("year") or "").isdigit() else None,
                    row.get("Pp_abstract"), None, None, timestamp, timestamp,
                ),
            )
            canonical = conn.execute(
                "SELECT paper_id FROM papers WHERE canonical_key=?", (canonical_key,)
            ).fetchone()["paper_id"]
            paper_id = canonical
            paper_version_id = stable_id("paper_version", paper_id, pdf_sha, parsed_sha, row["id"])
            conn.execute(
                """INSERT OR IGNORE INTO paper_versions(
                   paper_version_id,paper_id,version,pdf_path,pdf_digest,parsed_path,parsed_digest,
                   source_json,created_at)
                   VALUES(?,?,COALESCE((SELECT MAX(version)+1 FROM paper_versions WHERE paper_id=?),1),?,?,?,?,?,?)""",
                (
                    paper_version_id, paper_id, paper_id, pdf_path, pdf_sha,
                    parsed if isinstance(parsed, str) and Path(parsed).suffix else None,
                    parsed_sha, json.dumps({"adapter": "legacy-paperpool", "database": str(source_path), "id": row["id"]}),
                    timestamp,
                ),
            )
            conn.execute(
                """INSERT OR IGNORE INTO paper_skeletons(
                   skeleton_id,paper_version_id,version,extractor_model,prompt_version,content_digest,created_at)
                   VALUES(?,?,COALESCE((SELECT MAX(version)+1 FROM paper_skeletons WHERE paper_version_id=?),1),?,?,?,?)""",
                (skeleton_id, paper_version_id, paper_version_id, "legacy-paperpool-mincer", "legacy", skeleton_digest, timestamp),
            )
            evidence_ids: list[str] = []
            for index, entry in enumerate(semantics):
                if not isinstance(entry, dict) or not str(entry.get("raw_text") or "").strip():
                    raise ValueError(f"invalid skeleton entry at index {index}")
                seq_idx = int(entry.get("seq_idx", index))
                layer1 = entry.get("layer1") or {}
                layer2 = entry.get("layer2") or {}
                layer3 = entry.get("layer3") or {}
                unit_digest = digest(entry)
                unit_id = stable_id("unit", skeleton_id, seq_idx, unit_digest)
                conn.execute(
                    """INSERT OR IGNORE INTO skeleton_units VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        unit_id, skeleton_id, seq_idx, entry.get("page_idx"), entry.get("section"),
                        entry["raw_text"], json.dumps(layer1, ensure_ascii=False),
                        json.dumps(layer2, ensure_ascii=False), json.dumps(layer3, ensure_ascii=False),
                        entry.get("layer4"), unit_digest,
                    ),
                )
                for triplet in layer1.get("triplets", []):
                    if not all(str(triplet.get(key) or "").strip() for key in ("subject", "predicate", "object")):
                        continue
                    triplet_id = stable_id("triplet", unit_id, triplet)
                    conn.execute(
                        "INSERT OR IGNORE INTO skeleton_triplets VALUES(?,?,?,?,?,?)",
                        (
                            triplet_id, unit_id, triplet["subject"], triplet["predicate"],
                            triplet["object"], digest(triplet),
                        ),
                    )
                intent = str(layer3.get("intent") or "").removeprefix("[Intent: ").removesuffix("]")
                if intent in EVIDENCE_INTENTS:
                    statement = str(layer1.get("coref_resolved") or entry["raw_text"])
                    candidate_id = stable_id("evidence_candidate", build_id, unit_id, statement)
                    relation = "CONTEXTUALIZES" if intent in {"Research_Gap", "Future_Work", "Boundary_Condition", "Critical_Evaluation"} else "SUPPORTS"
                    conn.execute(
                        """INSERT OR IGNORE INTO fieldkg_evidence_candidates(
                           candidate_id,build_id,field_id,unit_id,statement,excerpt,relation,
                           confidence,status,rationale,revision,created_at,reviewed_at)
                           VALUES(?,?,?,?,?,?,?,?, 'PROPOSED',NULL,1,?,NULL)""",
                        (
                            candidate_id, build_id, build["field_id"], unit_id, statement,
                            entry["raw_text"], relation, float(layer3.get("confidence") or 0.0), timestamp,
                        ),
                    )
                    evidence_ids.append(candidate_id)
                    if intent == "Research_Gap":
                        gap_id = stable_id("candidate_gap", build_id, unit_id, statement)
                        conn.execute(
                            """INSERT OR IGNORE INTO fieldkg_candidate_gaps(
                               candidate_gap_id,build_id,field_id,statement,rationale,evidence_ids_json,
                               counterevidence_ids_json,conditions_json,generator_model,prompt_version,
                               status,revision,created_at,reviewed_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?, 'PROPOSED',1,?,NULL)""",
                            (
                                gap_id, build_id, build["field_id"], statement,
                                "Reported research gap extracted from a source PaperSkeleton.",
                                json.dumps([candidate_id]), "[]", "[]", "legacy-paperpool-mincer", "legacy", timestamp,
                            ),
                        )
            conn.execute(
                "INSERT OR REPLACE INTO fieldkg_build_papers VALUES(?,?,?,'IMPORTED',NULL)",
                (build_id, paper_version_id, skeleton_id),
            )
        return {
            "legacy_id": row["id"], "paper_id": paper_id, "paper_version_id": paper_version_id,
            "skeleton_id": skeleton_id, "evidence_candidates": len(evidence_ids), "status": "IMPORTED",
        }
