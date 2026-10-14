"""Read immutable author/generated views without starting jobs or seeding documents."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .service import NotFoundError, RSTV4Error
from .studio_context import citation_ids, generated_view, legacy_bibliography
from .studio_correspondence import has_correspondence, realization_document
from .studio_materials import markdown as material_markdown
from .studio_materials import verify_files as verify_material_files
from .studio_realization import validate as validate_realization
from .studio_structure import argument_context


def document_revision(conn: sqlite3.Connection, manuscript_id: str, revision: int) -> dict:
    current = conn.execute("SELECT * FROM studio_documents WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    if current is not None and revision == current["revision"]:
        document = json.loads(current["document_json"])
    else:
        row = conn.execute(
            """SELECT c.before_json,c.after_json,o.base_revision,o.resulting_revision
               FROM studio_changes c JOIN studio_operations o USING(operation_id)
               WHERE c.manuscript_id=? AND
               (o.resulting_revision=? OR (o.base_revision=0 AND ?=0))
               ORDER BY o.resulting_revision LIMIT 1""",
            (manuscript_id, revision, revision),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown author revision: {revision}")
        document = json.loads(row["before_json"] if revision == 0 else row["after_json"])
    if document.get("manuscript_id") != manuscript_id:
        raise RSTV4Error("The original author revision belongs to another manuscript")
    return {"manuscript_id": manuscript_id, "revision": revision, "document": document}


def verified_artifact_bytes(storage_root: Path, artifact: Any) -> bytes:
    path = Path(artifact["storage_path"]).resolve()
    if storage_root.resolve() not in path.parents or not path.is_file():
        raise RSTV4Error("The original generated artifact is unavailable")
    content = path.read_bytes()
    if len(content) != artifact["size_bytes"] or hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        raise RSTV4Error("The original generated artifact failed its integrity check")
    return content


def generated_markdown(generated: dict[str, Any]) -> str:
    parts = [f"# {generated['title']}"]
    if generated.get("abstract"):
        parts.extend(["", "## Abstract", "", generated["abstract"]])
    for section in generated["sections"]:
        prefix = "#" * (2 + section.get("section_depth", 0))
        parts.extend(["", f"{prefix} {section['title']}"])
        for paragraph in section["paragraphs"]:
            parts.extend(["", paragraph["text"]])
            for formula in paragraph.get("formulas", []):
                parts.extend(["", "$$", formula["latex"], "$$"])
                if formula.get("caption"):
                    parts.append(f"*{formula['caption']}*")
            parts.extend(material_markdown(paragraph.get("assets", [])))
    return "\n".join(parts).strip() + "\n"


def generated_version(conn: sqlite3.Connection, storage_root: Path, manuscript_id: str, version_id: str) -> dict:
    row = conn.execute("SELECT * FROM manuscript_versions WHERE manuscript_id=? AND manuscript_version_id=?", (manuscript_id, version_id)).fetchone()
    if row is None:
        raise NotFoundError("The generated version does not belong to this manuscript")
    version = dict(row)
    inputs = json.loads(version["inputs_json"])
    artifacts = conn.execute("SELECT * FROM studio_artifacts WHERE manuscript_id=? AND job_id=?", (manuscript_id, inputs.get("job_id"))).fetchall()
    generated = inputs.get("generated")
    by_kind = {item["artifact_kind"]: item for item in artifacts}
    if generated is None and "GENERATED_JSON" in by_kind:
        generated = json.loads(verified_artifact_bytes(storage_root, by_kind["GENERATED_JSON"]))
    if generated is not None and (generated_markdown(generated) != version["content"] or generated["input_revision"] != inputs.get("studio_revision")):
        raise RSTV4Error("Generated structure does not match its immutable version")
    if generated is not None:
        source_paragraphs = None
        for section in generated["sections"]:
            for paragraph in section["paragraphs"]:
                if not paragraph.get("model_call_id"):
                    continue
                if source_paragraphs is None:
                    source_document = document_revision(conn, manuscript_id, inputs["studio_revision"])["document"]
                    projected = realization_document(source_document)
                    if has_correspondence(source_document) and (
                            generated.get("author_source_sections") != projected["author_source_sections"]
                            or generated.get("argument_relations", []) != source_document.get("argument_relations", [])):
                        raise RSTV4Error("Generated correspondence differs from its original author context")
                    source_paragraphs = {p["id"]: p for s in projected["sections"] for p in s["paragraphs"]}
                source_paragraph = source_paragraphs.get(paragraph["paragraph_id"])
                call = conn.execute("SELECT * FROM studio_model_calls WHERE call_id=?", (paragraph["model_call_id"],)).fetchone()
                if (call is None or call["manuscript_id"] != manuscript_id
                        or call["job_id"] != inputs.get("job_id")
                        or call["input_revision"] != inputs.get("studio_revision")
                        or call["task"] != "paragraph_realization" or call["status"] != "VALIDATED"):
                    raise RSTV4Error("Generated realization has no matching validated model call")
                raw = json.loads(call["output_json"])
                call_input = json.loads(call["input_json"])
                if (source_paragraph is None or not isinstance(call_input, dict)
                        or call_input.get("intents") != source_paragraph["intents"]
                        or paragraph["thought_ids"] != [t["id"] for intent in source_paragraph["intents"] for t in intent["thoughts"]]
                        or hashlib.sha256(call["input_json"].encode("utf-8")).hexdigest() != call["input_sha256"]):
                    raise RSTV4Error("Generated realization does not match its original author input")
                if source_paragraph.get("author_contexts") and (
                        call_input.get("author_contexts") != source_paragraph["author_contexts"]
                        or call_input.get("argument_relations", []) != argument_context(source_document, source_paragraph)
                        or paragraph.get("author_contexts") != source_paragraph["author_contexts"]
                        or paragraph.get("formulas") != source_paragraph.get("formulas", [])
                        or paragraph.get("asset_ids") != source_paragraph.get("asset_ids", [])):
                    raise RSTV4Error("Generated correspondence does not match its original author context")
                if generated.get("material_snapshot_schema") == 1:
                    assets = paragraph.get("assets", [])
                    if (paragraph.get("asset_ids", []) != source_paragraph.get("asset_ids", [])
                            or [a["asset_id"] for a in assets] != source_paragraph.get("asset_ids", [])
                            or call_input.get("assets", []) != assets):
                        raise RSTV4Error("Generated materials differ from the original author input")
                    for asset in assets:
                        record = conn.execute("SELECT * FROM studio_assets WHERE manuscript_id=? AND asset_id=?",
                                              (manuscript_id, asset["asset_id"])).fetchone()
                        if record is None or any(asset.get(key) != record[key] for key in
                                                 ["filename", "media_type", "asset_kind", "sha256", "size_bytes"]):
                            raise RSTV4Error("Generated material has no matching original identity")
                    material_directory = storage_root / manuscript_id / "generated" / inputs["job_id"]
                    verify_material_files(material_directory, assets)
                realized = validate_realization(raw, set(paragraph["thought_ids"]), set(paragraph["evidence_ids"]))
                if (any(paragraph.get(key) != value for key, value in realized.items())
                        or paragraph.get("model_contract") != json.loads(call["contract_json"] or "null")
                        or raw.get("_contract") != paragraph.get("model_contract")):
                    raise RSTV4Error("Generated realization differs from its original validated model output")
    references = generated.get("references") if generated else None
    if references is None:
        historical = legacy_bibliography(verified_artifact_bytes(storage_root, by_kind["BIB"]).decode("utf-8")) if "BIB" in by_kind else {}
        references = [{**historical.get(evidence_id, {"evidence_id": evidence_id}), "citation_index": index, "source_snapshot_available": evidence_id in historical} for index, evidence_id in enumerate(citation_ids(version["content"]), 1)]
    view = generated_view(version, generated, references)
    view["artifacts"] = [dict(item) for item in artifacts]
    return view


def search_sources(conn: sqlite3.Connection, manuscript_id: str, query: str, *, limit: int = 30) -> list[dict]:
    manuscript = conn.execute("SELECT track_id FROM manuscripts WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    if manuscript is None:
        raise NotFoundError("The manuscript is unavailable")
    pattern = f"%{query.strip()}%"
    records = conn.execute(
        """SELECT e.evidence_id,e.statement,e.excerpt,e.location_json,e.relation,
           e.confidence,e.paper_id,p.title,p.authors_json,p.published_year,p.doi,
           p.landing_url,p.pdf_url FROM evidence e LEFT JOIN papers p ON p.paper_id=e.paper_id
           WHERE (e.track_id=? OR e.field_id=(SELECT field_id FROM research_tracks
           WHERE track_id=?)) AND (?='' OR e.statement LIKE ? OR e.excerpt LIKE ?
            OR p.title LIKE ? OR e.evidence_id=?)
           ORDER BY e.confidence DESC,e.created_at DESC LIMIT ?""",
        (manuscript["track_id"], manuscript["track_id"], query.strip(), pattern, pattern, pattern, query.strip(), min(max(limit, 1), 100)),
    ).fetchall()
    result = []
    for row in records:
        item = dict(row)
        item["location"] = json.loads(item.pop("location_json"))
        item["authors"] = json.loads(item.pop("authors_json")) if item["authors_json"] else []
        result.append(item)
    return result
