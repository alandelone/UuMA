"""Resolve actual Catalog/FieldKG/Track objects before freezing a discussion."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .fieldkg import digest
from .models import StrictModel
from .research_views import (
    candidate_context,
    parse_record,
    require,
    rows,
    skeleton_source,
    snapshot_view,
)
from .research_workspace import WorkspaceError
from .service import NotFoundError, RSTV4Error
from .studio_context import exact_quote, structure_object
from .studio_read_views import document_revision, generated_version


class DiscussionTarget(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    module: Literal["CATALOG", "FIELDKG", "TRACK", "STUDIO"]
    object_kind: Literal["paper", "property", "pdf_page", "parse", "parse_block", "assessment", "skeleton", "unit", "field", "candidate", "gap", "evidence", "concept", "relationship", "snapshot", "track", "node", "edge", "section", "paragraph_group", "paragraph", "intent", "thought", "generated_title", "generated_heading", "generated_paragraph", "semantic"]
    object_id: str = Field(min_length=1, max_length=2000)
    paper_id: str | None = None
    field_id: str | None = None
    track_id: str | None = None
    snapshot_id: str | None = None
    part: str | None = Field(default=None, max_length=100)
    page_number: int | None = Field(default=None, ge=1)
    manuscript_id: str | None = None
    document_revision: int | None = Field(default=None, ge=0)
    generated_version_id: str | None = None

    @model_validator(mode="after")
    def check_scope(self) -> DiscussionTarget:
        if self.module == "CATALOG" and not self.paper_id:
            raise ValueError("Catalog discussion requires its paper")
        if self.module == "FIELDKG" and not self.field_id:
            raise ValueError("FieldKG discussion requires its Field")
        if self.module == "TRACK" and not self.track_id:
            raise ValueError("Track discussion requires its Track")
        if self.module != "FIELDKG" and self.snapshot_id is not None:
            raise ValueError("A frozen FieldKG view belongs to FieldKG")
        if self.module == "STUDIO":
            if not self.manuscript_id:
                raise ValueError("Studio discussion requires its manuscript")
            if self.object_kind.startswith("generated_"):
                if not self.generated_version_id:
                    raise ValueError("Generated discussion requires its immutable version")
            elif self.document_revision is None or self.generated_version_id is not None:
                raise ValueError("Author discussion requires an exact author revision")
        elif any(value is not None for value in [self.manuscript_id, self.document_revision, self.generated_version_id]):
            raise ValueError("Manuscript version context belongs to Studio")
        return self


def scope_key(target: DiscussionTarget) -> str:
    owner = {"CATALOG": target.paper_id, "FIELDKG": target.field_id, "TRACK": target.track_id, "STUDIO": target.manuscript_id}[target.module]
    return json.dumps([target.module, owner], ensure_ascii=False, separators=(",", ":"))


def target_data(target: DiscussionTarget) -> dict:
    data = target.model_dump(mode="json")
    # Existing fixed sources and exact request identities predate these fields.
    for name in ["manuscript_id", "document_revision", "generated_version_id"]:
        if data[name] is None:
            data.pop(name)
    return data


def _get(conn: sqlite3.Connection, table: str, column: str, value: str) -> dict:
    row = conn.execute(f"SELECT * FROM {table} WHERE {column}=?", (value,)).fetchone()
    if row is None:
        raise WorkspaceError(404, "The selected source object is unavailable")
    return parse_record(dict(row))


def _owned(record: dict, column: str, value: str | None) -> None:
    if record.get(column) != value:
        raise WorkspaceError(404, "The selected object does not belong to this scope")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _pdf_page(conn: sqlite3.Connection, target: DiscussionTarget) -> dict:
    file = _get(conn, "source_file_versions", "file_version_id", target.object_id)
    _owned(file, "paper_id", target.paper_id)
    path = Path(file.pop("storage_path")).resolve()
    page = target.page_number
    if page is None:
        raise WorkspaceError(422, "PDF discussion requires its original page number")
    if file["mime_type"] != "application/pdf" or not path.is_file():
        raise WorkspaceError(410, "The original PDF is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
        raise WorkspaceError(410, "The original PDF no longer matches its recorded version")
    extractor = shutil.which("pdftotext")
    if not extractor:
        raise WorkspaceError(503, "The PDF text extractor is unavailable")
    try:
        if page > len(PdfReader(path, strict=False).pages):
            raise WorkspaceError(404, "The selected PDF page is unavailable")
        output = subprocess.run([extractor, "-f", str(page), "-l", str(page), "-bbox-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=45, check=False)
        if output.returncode:
            raise WorkspaceError(422, "The original PDF text could not be read")
        document = ET.fromstring(output.stdout)
        page_element = document.find(".//{http://www.w3.org/1999/xhtml}page")
        if page_element is None:
            raise WorkspaceError(422, "The original PDF page text is unavailable")
        words = []
        for word in page_element.findall(".//{http://www.w3.org/1999/xhtml}word"):
            text = "".join(word.itertext()).strip()
            if text:
                words.append({"text": text, "x": float(word.attrib["xMin"]), "y": float(word.attrib["yMin"]), "width": float(word.attrib["xMax"]) - float(word.attrib["xMin"]), "height": float(word.attrib["yMax"]) - float(word.attrib["yMin"])})
        if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
            raise WorkspaceError(410, "The original PDF changed while reading")
        return {"file": file, "page_number": page, "words": words, "page_text": " ".join(word["text"] for word in words)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceError(503, "The PDF source could not be read") from exc
    except (ET.ParseError, ValueError, KeyError, PdfReadError) as exc:
        raise WorkspaceError(422, "The PDF source text or layout is invalid") from exc


def _catalog(conn: sqlite3.Connection, target: DiscussionTarget) -> tuple[str, str, dict, list]:
    paper = _get(conn, "papers", "paper_id", target.paper_id or "")
    kind, object_id = target.object_kind, target.object_id
    versions: list[dict] = []
    label = paper["title"]
    if kind == "paper":
        _owned(paper, "paper_id", object_id)
        record = paper
        text = "\n".join(str(value) for value in [paper["title"], paper.get("abstract")] if value)
    elif kind == "property":
        _owned(paper, "paper_id", object_id)
        if target.part not in {"title", "abstract", "doi", "authors", "published_year"}:
            raise WorkspaceError(422, "This paper property is not discussable")
        record = {"paper_id": paper["paper_id"], "part": target.part, "value": paper.get(target.part), "updated_at": paper["updated_at"]}
        text = _text(record["value"])
        label += " / " + target.part
    elif kind == "pdf_page":
        record = _pdf_page(conn, target)
        text = record["page_text"]
        versions = [{"file_version_id": object_id, "file_sha256": record["file"]["sha256"], "page_number": target.page_number}]
        label += f" / PDF 第 {target.page_number} 页"
    elif kind in {"parse", "parse_block"}:
        if kind == "parse_block":
            record = _get(conn, "document_blocks", "block_id", object_id)
            run = _get(conn, "parse_runs", "parse_run_id", record["parse_run_id"])
            text = record["text"]
        else:
            run = _get(conn, "parse_runs", "parse_run_id", object_id)
            record = {"run": run, "blocks": [parse_record(row) for row in rows(conn, "SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence", (object_id,))]}
            text = "\n\n".join(block["text"] for block in record["blocks"])
        file = _get(conn, "source_file_versions", "file_version_id", run["file_version_id"])
        _owned(file, "paper_id", target.paper_id)
        run = {key: value for key, value in run.items() if key != "artifact_manifest"}
        if "run" in record:
            record["run"] = run
        versions = [{"parse_run_id": run["parse_run_id"], "file_version_id": file["file_version_id"], "file_sha256": file["sha256"], "parser_name": run["parser_name"], "parser_version": run["parser_version"], "config_digest": run["config_digest"], "parse_status": run["status"]}]
        label += " / Parse"
    elif kind == "assessment":
        record = _get(conn, "paper_assessments", "assessment_id", object_id)
        _owned(record, "paper_id", target.paper_id)
        if target.part:
            if target.part not in record["result"]:
                raise WorkspaceError(404, "This QuickRead section is unavailable")
            text = _text(record["result"][target.part])
        else:
            text = _text(record["result"])
        versions = [{"assessment_id": object_id, "input_digest": record["input_digest"], "prompt_version": record["prompt_version"], "model_name": record["model_name"]}]
        label += " / " + record["assessment_type"] + (" / " + target.part if target.part else "")
    elif kind in {"skeleton", "unit"}:
        if kind == "unit":
            record = _get(conn, "skeleton_units", "unit_id", object_id)
            source = skeleton_source(conn, record["skeleton_id"])
            text = record["raw_text"]
        else:
            source = skeleton_source(conn, object_id)
            record = source
            text = "\n\n".join(unit["raw_text"] for unit in source["units"])
        _owned(source, "paper_id", target.paper_id)
        versions = [_source_version(source)]
        if kind == "unit":
            versions[0].update(unit_id=object_id, page_idx=record["page_idx"], seq_idx=record["seq_idx"], section=record["section"])
        label += f" / Skeleton v{source['version']}"
    else:
        raise WorkspaceError(422, "This object kind is not a Catalog object")
    return label, text, record, versions


def _source_version(source: dict) -> dict:
    return {key: source.get(key) for key in ["paper_id", "paper_version_id", "paper_version", "skeleton_id", "version", "file_version_id", "parse_run_id", "content_digest", "parsed_digest", "pdf_digest", "extractor_model", "prompt_version"]}


def _field(conn: sqlite3.Connection, target: DiscussionTarget) -> tuple[str, str, dict, list]:
    field = require(conn, "field", target.field_id or "")
    fixed = snapshot_view(conn, field["field_id"], target.snapshot_id) if target.snapshot_id else None
    if fixed and (not fixed["digest_matches"] or not fixed["members_match"]):
        raise WorkspaceError(410, "The fixed Snapshot content is inconsistent")
    sources = fixed["sources"] if fixed else [skeleton_source(conn, row[0]) for row in conn.execute("SELECT DISTINCT bp.skeleton_id FROM fieldkg_build_papers bp JOIN fieldkg_builds b ON b.build_id=bp.build_id WHERE b.field_id=? AND bp.skeleton_id IS NOT NULL ORDER BY bp.skeleton_id", (target.field_id,))]
    label, versions = field["name"], []
    kind, object_id = target.object_kind, target.object_id
    if kind == "field":
        _owned(field, "field_id", object_id)
        if fixed:
            raise WorkspaceError(422, "Select a fixed Snapshot object instead of current Field metadata")
        record, text = field, field["name"] + "\n" + (field["description"] or "")
    elif kind == "snapshot":
        snapshot = fixed or snapshot_view(conn, field["field_id"], object_id)
        _owned(snapshot, "snapshot_id", object_id)
        if not snapshot["digest_matches"] or not snapshot["members_match"]:
            raise WorkspaceError(410, "The fixed Snapshot content is inconsistent")
        record = {key: snapshot[key] for key in ["snapshot_id", "version", "content_digest", "manifest", "members", "source_records_available"]}
        text = f"Snapshot v{snapshot['version']}\n" + _text(snapshot["manifest"])
        versions = [{"snapshot_id": object_id, "snapshot_digest": snapshot["content_digest"], "snapshot_version": snapshot["version"]}]
    elif kind in {"paper", "skeleton", "unit"}:
        column = {"paper": "paper_id", "skeleton": "skeleton_id", "unit": "unit_id"}[kind]
        source = next((source for source in sources if (any(unit["unit_id"] == object_id for unit in source["units"]) if kind == "unit" else source[column] == object_id)), None)
        if source is None:
            raise WorkspaceError(404, "This source is outside the selected Field or Snapshot")
        record = next(unit for unit in source["units"] if unit["unit_id"] == object_id) if kind == "unit" else source
        text = record["raw_text"] if kind == "unit" else "\n\n".join(unit["raw_text"] for unit in source["units"])
        label += " / " + source["title"]
        versions = [_source_version(source)]
        if kind == "unit":
            versions[0].update(unit_id=object_id, page_idx=record["page_idx"], seq_idx=record["seq_idx"], section=record["section"])
    elif kind == 'semantic':
        from .fieldkg_semantics import semantic_objects
        collection=fixed['frozen_semantic_objects'] if fixed else semantic_objects(conn,target.field_id)
        selected=next((obj for obj in collection if obj['object_id']==object_id),None)
        if selected is None:raise WorkspaceError(404,'Semantic object is outside the selected Field or Snapshot')
        record=selected
        text=selected['statement']+'\n\n'+'\n\n'.join(ref['quote'] for ref in selected['references'])
        label+=' / '+selected['kind']
        for ref in selected['references']:
            source=next((s for s in sources if s['skeleton_id']==ref['source']['skeleton_id']),None)
            if source is None:raise WorkspaceError(410,'Original semantic source is unavailable in this scope')
            versions.append({**_source_version(source),'unit_id':ref['unit_id'],**ref['location']})
    elif kind in {"candidate", "gap", "evidence"}:
        if fixed:
            collection, column = {"candidate": (fixed["manifest"].get("reviewed_candidates", []), "candidate_id"), "gap": (fixed["frozen_candidate_gaps"], "candidate_gap_id"), "evidence": (fixed["frozen_evidence"], "evidence_id")}[kind]
            selected = next((row for row in collection if row[column] == object_id), None)
            if selected is None:
                raise WorkspaceError(404, "This object is not in the fixed Snapshot")
            record = parse_record(selected)
            if kind == "gap":
                record["references"] = fixed["manifest"].get("gap_references", {}).get(object_id, [])
        else:
            record = _get(conn, "evidence", "evidence_id", object_id) if kind == "evidence" else require(conn, kind, object_id)
            _owned(record, "field_id", target.field_id)
            if kind == "evidence" and record["scope_kind"] != "FIELDKG":
                raise WorkspaceError(404, "This is not FieldKG evidence")
            if kind != "evidence":
                context = candidate_context(conn, kind, object_id)
                record = {**parse_record(record), **{key: value for key, value in context.items() if key in {"source", "references"}}}
        text = record.get("excerpt") or record["statement"]
        label += " / " + kind
        unit_id = record.get("unit_id") or (record.get("location") or {}).get("unit_id")
        source = next((source for source in sources if any(unit["unit_id"] == unit_id for unit in source["units"])), None)
        if source:
            versions = [_source_version(source)]
            unit = next(unit for unit in source["units"] if unit["unit_id"] == unit_id)
            versions[0].update(unit_id=unit_id, page_idx=unit["page_idx"], seq_idx=unit["seq_idx"], section=unit["section"])
    elif kind == "concept":
        occurrences = [{"triplet": triplet, "unit": next(unit for unit in source["units"] if unit["unit_id"] == triplet["unit_id"]), "source_version": _source_version(source)} for source in sources for triplet in source["triplets"] if object_id in {triplet["subject"], triplet["object"]}]
        if not occurrences:
            raise WorkspaceError(404, "This exact term is outside the selected Field or Snapshot")
        record = {"term": object_id, "occurrences": occurrences}
        text = "\n\n".join(item["unit"]["raw_text"] for item in occurrences)
        versions = [item["source_version"] for item in occurrences]
        label += " / " + object_id
    elif kind == "relationship":
        try:
            relation_kind, relation_id = json.loads(object_id)
        except (ValueError, TypeError) as exc:
            raise WorkspaceError(422, "Invalid graph relationship identity") from exc
        if not isinstance(relation_kind, str) or (relation_kind == "gap-reference" and (not isinstance(relation_id, list) or len(relation_id) != 2 or not all(isinstance(item, str) for item in relation_id))) or (relation_kind != "gap-reference" and not isinstance(relation_id, str)):
            raise WorkspaceError(422, "Invalid graph relationship identity")
        if relation_kind == "triplet":
            source = next((source for source in sources if any(item["triplet_id"] == relation_id for item in source["triplets"])), None)
            if source is None:
                raise WorkspaceError(404, "This relationship is outside the selected scope")
            triplet = next(item for item in source["triplets"] if item["triplet_id"] == relation_id)
            unit = next(item for item in source["units"] if item["unit_id"] == triplet["unit_id"])
            record, text, versions = {"triplet": triplet, "unit": unit}, unit["raw_text"], [_source_version(source)]
        elif relation_kind == "citation":
            paper_ids = {source["paper_id"] for source in sources}
            citations = fixed["manifest"].get("citations", []) if fixed else rows(conn, "SELECT * FROM citation_observations WHERE citation_id=?", (relation_id,))
            record = next((row for row in citations if row["citation_id"] == relation_id and row["citing_paper_id"] in paper_ids and row["cited_paper_id"] in paper_ids), None)
            if record is None:
                raise WorkspaceError(404, "This citation is outside the selected scope")
            text = _text(record)
        elif relation_kind in {"source", "candidate-source", "gap-reference"}:
            nested_kind = {"source": "unit", "candidate-source": "candidate", "gap-reference": "gap"}[relation_kind]
            nested_id = relation_id[0] if relation_kind == "gap-reference" and isinstance(relation_id, list) and len(relation_id) == 2 else relation_id
            nested = target.model_copy(update={"object_kind": nested_kind, "object_id": nested_id})
            _, text, record, versions = _field(conn, nested)
            if relation_kind == "gap-reference":
                refs = record.get("references", [])
                if not any(ref.get("record", {}).get("candidate_id", ref.get("record", {}).get("evidence_id")) == relation_id[1] for ref in refs):
                    raise WorkspaceError(404, "This Gap reference is unavailable")
            record = {"relationship_identity": object_id, "source_record": record}
        elif relation_kind == 'semantic-source':
            try:
                semantic_id,index=relation_id.rsplit('|',1)
                index=int(index)
            except (ValueError,TypeError) as error:
                raise WorkspaceError(422,'Invalid semantic source relationship') from error
            nested=target.model_copy(update={'object_kind':'semantic','object_id':semantic_id})
            _,_,semantic,source_versions=_field(conn,nested)
            if index<0 or index>=len(semantic['references']):
                raise WorkspaceError(404,'This semantic source relationship is unavailable')
            ref=semantic['references'][index]
            record={'relationship_identity':object_id,'semantic_object':semantic,'reference':ref}
            text=ref['quote']
            versions=[version for version in source_versions if version.get('unit_id')==ref['unit_id']]
        else:
            raise WorkspaceError(422, "This graph relationship kind is unavailable")
        label += " / 关系"
    else:
        raise WorkspaceError(422, "This object kind is not a FieldKG object")
    if fixed:
        versions.append({"snapshot_id": fixed["snapshot_id"], "snapshot_digest": fixed["content_digest"], "snapshot_version": fixed["version"]})
    return label, text, record, versions


def _track(conn: sqlite3.Connection, target: DiscussionTarget) -> tuple[str, str, dict, list]:
    track = require(conn, "track", target.track_id or "")
    label, kind, object_id = track["title"], target.object_kind, target.object_id
    if kind == "track":
        _owned(track, "track_id", object_id)
        record, text = track, track["title"] + "\n" + (track["scope"] or "")
    elif kind in {"node", "edge", "evidence"}:
        table, column = {"node": ("research_nodes", "node_id"), "edge": ("research_edges", "edge_id"), "evidence": ("evidence", "evidence_id")}[kind]
        record = _get(conn, table, column, object_id)
        if kind == "evidence" and record["scope_kind"] == "FIELDKG":
            _owned(record, "field_id", track["field_id"])
            if not conn.execute("SELECT 1 FROM node_evidence ne JOIN research_nodes n ON n.node_id=ne.node_id WHERE ne.evidence_id=? AND n.track_id=?", (object_id, target.track_id)).fetchone():
                raise WorkspaceError(404, "This evidence is not linked to the selected Track")
        else:
            _owned(record, "track_id", target.track_id)
        if kind == "edge":
            for name in ["source_node_id", "target_node_id"]:
                node = _get(conn, "research_nodes", "node_id", record[name])
                _owned(node, "track_id", target.track_id)
                record[name.removesuffix("_id")] = node
            text = record["source_node"]["statement"] + "\n" + record["relation"] + "\n" + record["target_node"]["statement"]
        else:
            text = record.get("excerpt") or record["statement"]
        label += " / " + kind
    elif kind == "snapshot":
        if not conn.execute("SELECT 1 FROM track_snapshot_adoptions WHERE track_id=? AND snapshot_id=?", (target.track_id, object_id)).fetchone():
            raise WorkspaceError(404, "This Snapshot has not been adopted by the selected Track")
        snapshot = snapshot_view(conn, track["field_id"], object_id)
        if not snapshot["digest_matches"] or not snapshot["members_match"]:
            raise WorkspaceError(410, "The adopted Snapshot is inconsistent")
        record = {key: snapshot[key] for key in ["snapshot_id", "version", "content_digest", "manifest"]}
        text = _text(record["manifest"])
    else:
        raise WorkspaceError(422, "This object kind is not a Track object")
    if target.field_id is not None and target.field_id != track["field_id"]:
        raise WorkspaceError(404, "The Track does not belong to the requested Field")
    return label, text, record, [{"track_id": target.track_id, "track_revision": track["revision"], "field_id": track["field_id"]}]


def _studio(conn: sqlite3.Connection, target: DiscussionTarget) -> tuple[str, str, dict, list]:
    manuscript = _get(conn, "manuscripts", "manuscript_id", target.manuscript_id or "")
    if target.track_id is not None and target.track_id != manuscript["track_id"]:
        raise WorkspaceError(404, "The manuscript does not belong to this Track")
    if target.field_id is not None:
        track = require(conn, "track", manuscript["track_id"])
        if target.field_id != track["field_id"]:
            raise WorkspaceError(404, "The manuscript does not belong to this Field")
    try:
        if target.object_kind.startswith("generated_"):
            db_file = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
            view = generated_version(conn, Path(db_file).parent / "writing-studio", manuscript["manuscript_id"], target.generated_version_id or "")
            block = next((item for item in view["blocks"] if item["anchor_id"] == target.object_id), None)
            if block is None or target.object_kind != f"generated_{block['kind']}":
                raise WorkspaceError(404, "The original generated block is unavailable")
            known = view["input_revision"]
            if target.document_revision is not None and target.document_revision != (known if known is not None else 0):
                raise WorkspaceError(422, "The generated block has a different original author revision")
            snapshot = document_revision(conn, manuscript["manuscript_id"], known) if known is not None else None
            view["artifacts"] = [{key: value for key, value in item.items() if key != "storage_path"} for item in view["artifacts"]]
            record = {"snapshot": snapshot, "generated": view, "block": block}
            versions = [{"manuscript_id": manuscript["manuscript_id"], "generated_version_id": view["generated_version_id"], "generated_version": view["version"], "author_revision": known}]
            return block["label"], block["display_text"], record, versions
        snapshot = document_revision(conn, manuscript["manuscript_id"], target.document_revision)
        label, text = structure_object(snapshot["document"], target.object_kind, target.object_id)
        return label, text, {"snapshot": snapshot}, [{"manuscript_id": manuscript["manuscript_id"], "author_revision": target.document_revision}]
    except NotFoundError as exc:
        raise WorkspaceError(404, str(exc)) from exc
    except RSTV4Error as exc:
        raise WorkspaceError(410, str(exc)) from exc


def resolve_context(conn: sqlite3.Connection, target: DiscussionTarget) -> dict:
    label, text, record, versions = {"CATALOG": _catalog, "FIELDKG": _field, "TRACK": _track, "STUDIO": _studio}[target.module](conn, target)
    context = {"target": target_data(target), "scope_key": scope_key(target), "label": label, "object_text": text, "record": record, "versions": versions}
    context["context_sha256"] = digest(context)
    return context


def freeze_quote(context: dict, quote: dict | None) -> dict:
    return {**exact_quote(context["object_text"], quote), "source": {**context["target"], "label": context["label"], "context_sha256": context["context_sha256"], "versions": context["versions"]}, "object_text": context["object_text"]}
