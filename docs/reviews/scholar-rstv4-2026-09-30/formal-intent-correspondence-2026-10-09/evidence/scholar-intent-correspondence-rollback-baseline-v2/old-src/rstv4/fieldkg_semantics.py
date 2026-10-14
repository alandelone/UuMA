"""Typed FieldKG interpretations with exact sources and independent user review."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .database import transaction
from .durable_model_delivery import ModelRunPending, ModelRunStopped
from .fieldkg import digest, stable_id
from .model_gateway import UnlimitedLLMGateway
from .models import StrictModel
from .research_workspace import WorkspaceError
from .source_review import source_is_available

SCHEMA = """
CREATE TABLE IF NOT EXISTS fieldkg_semantic_runs (
 run_id TEXT PRIMARY KEY,
 request_id TEXT NOT NULL UNIQUE,
 field_id TEXT NOT NULL REFERENCES research_fields(field_id),
 build_id TEXT NOT NULL REFERENCES fieldkg_builds(build_id),
 request_json TEXT NOT NULL,
 input_json TEXT NOT NULL,
 input_digest TEXT NOT NULL,
 status TEXT NOT NULL,
 result_json TEXT NOT NULL,
 router_run_id TEXT,
 error_type TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fieldkg_semantic_objects (
 object_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES fieldkg_semantic_runs(run_id),
 field_id TEXT NOT NULL REFERENCES research_fields(field_id),
 build_id TEXT NOT NULL REFERENCES fieldkg_builds(build_id),
 kind TEXT NOT NULL,
 statement TEXT NOT NULL,
 rationale TEXT NOT NULL,
 references_json TEXT NOT NULL,
 conditions_json TEXT NOT NULL,
 confidence REAL NOT NULL,
 status TEXT NOT NULL,
 revision INTEGER NOT NULL,
 model_contract_json TEXT NOT NULL,
 content_digest TEXT NOT NULL,
 reviewed_at TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fieldkg_semantic_objects_build
 ON fieldkg_semantic_objects(build_id, object_id);
"""

SemanticKind = Literal[
    "CONCEPT", "METHOD", "FINDING", "REPORTED_GAP", "COUNTEREVIDENCE", "DEBATE", "IDEA_MERGER"
]


class SourceReference(StrictModel):
    unit_id: str
    quote: str = Field(min_length=1, max_length=24000)
    role: Literal["SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES"]
    qualifications: list[str] = Field(default_factory=list, max_length=100)
    start: int | None = Field(default=None,ge=0)
    end: int | None = Field(default=None,ge=0)


class SemanticObject(StrictModel):
    kind: SemanticKind
    statement: str = Field(min_length=1, max_length=16000)
    rationale: str = Field(min_length=1, max_length=8000)
    references: list[SourceReference] = Field(min_length=1, max_length=100)
    conditions: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(ge=0, le=1)


class SemanticOutput(StrictModel):
    objects: list[SemanticObject] = Field(max_length=300)
    observed_unit_ids: list[str] = Field(min_length=1, max_length=1000)


class ExtractSemantics(StrictModel):
    operation: Literal["EXTRACT_SEMANTICS"] = "EXTRACT_SEMANTICS"
    request_id: str = Field(min_length=8, max_length=200)
    field_id: str
    build_id: str
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]


class ReviewSemantic(StrictModel):
    operation: Literal["REVIEW_SEMANTIC"] = "REVIEW_SEMANTIC"
    object_id: str | None = None
    request_id: str = Field(min_length=8, max_length=200)
    field_id: str
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["ACCEPTED", "REJECTED"]
    rationale: str = Field(min_length=1, max_length=8000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def nonempty_reason(self):
        if not self.rationale.strip():
            raise ValueError("A semantic review reason is required")

        return self


class AbandonSemantic(StrictModel):
    operation: Literal["ABANDON_SEMANTICS"] = "ABANDON_SEMANTICS"
    run_id: str | None = None
    request_id: str = Field(min_length=8, max_length=200)
    field_id: str
    expected_updated_at: str
    rationale: str = Field(min_length=1, max_length=8000)
    confirmed: Literal[True]


def table_available(conn: sqlite3.Connection) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fieldkg_semantic_objects'"
        ).fetchone()
    )


def semantic_objects(
    conn: sqlite3.Connection, field_id: str, build_id: str | None = None
) -> list[dict]:
    if not table_available(conn):
        return []
    result = []
    for row in conn.execute(
        "SELECT * FROM fieldkg_semantic_objects WHERE field_id=? AND (? IS NULL OR build_id=?) ORDER BY created_at,object_id",
        (field_id, build_id, build_id),
    ):
        item = dict(row)
        for name in ["references", "conditions", "model_contract"]:
            item[name] = json.loads(item.pop(name + "_json"))
        item["scientific_approval"] = False
        item["context_sha256"] = digest(item)
        result.append(item)
    return result


def semantic_runs(
    conn: sqlite3.Connection, field_id: str, build_id: str | None = None
) -> list[dict]:
    if not table_available(conn):
        return []
    return [
        {**dict(row), "result": json.loads(row["result_json"])}
        for row in conn.execute(
            "SELECT run_id,request_id,field_id,build_id,input_digest,status,result_json,router_run_id,error_type,created_at,updated_at FROM fieldkg_semantic_runs WHERE field_id=? AND (? IS NULL OR build_id=?) ORDER BY created_at,run_id",
            (field_id, build_id, build_id),
        )
    ]


def source_windows(sources: list[dict]) -> list[dict]:
    remaining = [list(source["units"]) for source in sources]
    units = []
    while any(remaining):
        for source, queue in zip(sources, remaining, strict=True):
            if queue:
                unit = queue.pop(0)
                units.append(
                    {
                        "unit_id": unit["unit_id"],
                        "paper_id": source["paper_id"],
                        "paper_version_id": source["paper_version_id"],
                        "title": source["title"],
                        "page_idx": unit["page_idx"],
                        "section": unit["section"],
                        "raw_text": unit["raw_text"],
                        "layer3": unit["layer3"],
                    }
                )
    windows = []
    current = []
    for unit in units:
        if len(json.dumps({"units": [unit]}, ensure_ascii=False)) > 28000:
            raise WorkspaceError(
                422,
                "A source unit exceeds the semantic input window; split it with explicit source spans before extraction",
            )
        if current and len(json.dumps({"units": [*current, unit]}, ensure_ascii=False)) > 28000:
            windows.append({"units": current})
            current = []
        current.append(unit)
    if current:
        windows.append({"units": current})
    if not windows:
        raise WorkspaceError(422, "Build has no source units")
    return windows


def validate_output(raw: dict, window: dict, sources: list[dict]) -> list[dict]:
    output = SemanticOutput.model_validate(
        {key: value for key, value in raw.items() if key != "_contract"}
    )
    supplied = {unit["unit_id"] for unit in window["units"]}
    if set(output.observed_unit_ids) != supplied or len(output.observed_unit_ids) != len(supplied):
        raise ValueError("Every supplied source unit must be accounted for exactly once")
    located = {unit["unit_id"]: (source, unit) for source in sources for unit in source["units"]}
    objects = []
    for model, original in zip(output.objects, raw["objects"], strict=True):
        references = []
        paper_ids = set()
        roles = set()
        for ref, original_ref in zip(model.references, original["references"], strict=True):
            if ref.unit_id not in supplied:
                raise ValueError("Semantic reference is outside this source window")
            source, unit = located[ref.unit_id]
            quote = original_ref["quote"]
            if quote not in unit["raw_text"]:
                raise ValueError("Semantic quotation must match the exact original source")
            start=ref.start;end=ref.end
            if start is None and end is None:
                if unit['raw_text'].count(quote)!=1:
                    raise ValueError('Repeated source quotations require explicit character offsets')
                start=unit['raw_text'].index(quote);end=start+len(quote)
            elif start is None or end is None or unit['raw_text'][start:end]!=quote:
                raise ValueError('Semantic source offsets must identify the exact original quotation')
            qualifications = original_ref.get("qualifications", [])
            if any(not text.strip() or text not in unit["raw_text"] for text in qualifications):
                raise ValueError("Semantic qualifications must be exact original quotations")
            paper_ids.add(source["paper_id"])
            roles.add(ref.role)
            references.append(
                {
                    "unit_id": ref.unit_id,
                    "quote": quote,
                    "role": ref.role,
                    "qualifications": qualifications,
                    "source": {
                        key: source.get(key)
                        for key in [
                            "paper_id",
                            "paper_version_id",
                            "paper_version",
                            "skeleton_id",
                            "version",
                            "file_version_id",
                            "parse_run_id",
                            "pdf_digest",
                            "parsed_digest",
                        ]
                    },
                    "location": {
                        "page_idx": unit["page_idx"],
                        "section": unit["section"],
                        "seq_idx": unit["seq_idx"],
                        "offset_unit": "unicode_codepoint",
                        "start": start,
                        "end": end,
                    },
                    "unit_digest": unit["content_digest"],
                    "original_text": unit["raw_text"],
                }
            )
        if model.kind in {"DEBATE", "IDEA_MERGER"} and len(paper_ids) < 2:
            raise ValueError(
                "A Debate or Idea Merger requires explicit sources from different papers"
            )
        if model.kind == "DEBATE" and not {"SUPPORTS", "CONTRADICTS"} <= roles:
            raise ValueError("A Debate must retain both supported and opposing source positions")
        if model.kind == "COUNTEREVIDENCE" and "CONTRADICTS" not in roles:
            raise ValueError("Counterevidence must preserve its explicit opposing source relation")
        item = model.model_dump()
        item["references"] = references
        objects.append(item)
    return objects


class FieldKGSemantics:
    def __init__(self, root: Path, gateway=None):
        self.root = Path(root).resolve()
        self.db_path = self.root / "data/catalog.db"
        self.gateway = gateway

    @staticmethod
    def _run(conn, run_id):
        row = conn.execute(
            "SELECT * FROM fieldkg_semantic_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise WorkspaceError(404, "Semantic extraction request not found")
        result = dict(row)
        result["input"] = json.loads(result.pop("input_json"))
        result["result"] = json.loads(result.pop("result_json"))
        result["request"] = json.loads(result.pop("request_json"))
        return result

    def create(self, payload: ExtractSemantics) -> dict:
        from .acquisition import utc_now
        from .research_views import build_context

        raw = json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True)
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT run_id,request_json FROM fieldkg_semantic_runs WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
            if old:
                if old["request_json"] != raw:
                    raise WorkspaceError(
                        409, "This request ID belongs to another semantic extraction"
                    )
                return self._run(conn, old["run_id"])
            build = build_context(conn, payload.build_id)
            if build["field_id"] != payload.field_id:
                raise WorkspaceError(404, "Build belongs to another Field")
            if build["status"] == "SEALED":
                raise WorkspaceError(
                    409, "A sealed Build cannot receive new semantic interpretations"
                )
            if build["context_sha256"] != payload.expected_context_sha256:
                raise WorkspaceError(409, "Build changed; compare its current sources")
            if any(not source_is_available(conn, s["paper_version_id"]) for s in build["sources"]):
                raise WorkspaceError(409, "Source requires review before semantic extraction")
            inputs = {"sources": build["sources"], "windows": source_windows(build["sources"])}
            run_id = stable_id("semantic_run", payload.request_id)
            now = utc_now()
            conn.execute(
                "INSERT INTO fieldkg_semantic_runs VALUES(?,?,?,?,?,?,?,'READY','[]',NULL,NULL,?,?)",
                (
                    run_id,
                    payload.request_id,
                    payload.field_id,
                    payload.build_id,
                    raw,
                    json.dumps(inputs, ensure_ascii=False),
                    digest(build["sources"]),
                    now,
                    now,
                ),
            )
            return self._run(conn, run_id)

    def get(self, field_id: str, run_id: str) -> dict:
        with closing(
            sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.row_factory = sqlite3.Row
            run = self._run(conn, run_id)
            if run["field_id"] != field_id:
                raise WorkspaceError(404, "Semantic request belongs to another Field")
            return run

    def advance(self, field_id: str, run_id: str) -> dict:
        from .acquisition import utc_now
        from .research_views import build_context

        run = self.get(field_id, run_id)
        if run["status"] in {"COMPLETED", "STALE", "FAILED", "STOPPED", "ABANDONED"}:
            return run
        gateway = self.gateway or UnlimitedLLMGateway(self.root)
        index = len(run["result"])
        window = run["input"]["windows"][index]
        scope = {
            "field_id": field_id,
            "build_id": run["build_id"],
            "semantic_run_id": run_id,
            "window": index,
            "source_digest": run["input_digest"],
        }
        operation = gateway.operation_id("fieldkg_semantics", window, scope)
        raw = None
        objects = None
        pending = None
        error = None
        try:
            raw = gateway.analyze_for_operation("fieldkg_semantics", window, operation)
            if not isinstance(raw.get('_contract'),dict):
                raise TypeError('Semantic extraction has no actual model contract')
            objects = validate_output(raw, window, run["input"]["sources"])
        except (ModelRunPending, ModelRunStopped) as failure:
            pending = failure
        except (ValueError,TypeError,RuntimeError,OSError) as failure:
            error = failure
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._run(conn, run_id)
            if current['status']=='ABANDONED':
                late=list(current['result'])
                if raw is not None:
                    late.append({'window':index,'output':raw,'valid':objects is not None,'publication':'ABANDONED'})
                conn.execute('UPDATE fieldkg_semantic_runs SET result_json=?,router_run_id=?,updated_at=? WHERE run_id=?',
                    (json.dumps(late,ensure_ascii=False),pending.run_id if pending else (raw or {}).get('_contract',{}).get('router_run_id'),utc_now(),run_id))
                return self._run(conn,run_id)
            if len(current["result"]) != index or current["status"] in {
                "COMPLETED",
                "STALE",
                "FAILED",
                "STOPPED",
                "ABANDONED",
            }:
                return current
            build = build_context(conn, run["build_id"])
            now = utc_now()
            if (
                build["status"] == "SEALED"
                or digest(build["sources"]) != run["input_digest"]
                or any(
                    not source_is_available(conn, s["paper_version_id"]) for s in build["sources"]
                )
            ):
                status = "STALE"
            elif pending:
                status = "WAITING" if isinstance(pending, ModelRunPending) else "STOPPED"
            elif error:
                status = "FAILED"
            else:
                status = "COMPLETED" if index + 1 == len(run["input"]["windows"]) else "READY"
            results = list(current["result"])
            if raw is not None:
                results.append({"window": index, "output": raw, "valid": objects is not None})
            conn.execute(
                "UPDATE fieldkg_semantic_runs SET status=?,result_json=?,router_run_id=?,error_type=?,updated_at=? WHERE run_id=?",
                (
                    status,
                    json.dumps(results, ensure_ascii=False),
                    pending.run_id
                    if pending
                    else (raw or {}).get("_contract", {}).get("router_run_id"),
                    type(error).__name__ if error else type(pending).__name__ if pending else None,
                    now,
                    run_id,
                ),
            )
            if status in {"READY", "COMPLETED"} and objects is not None:
                for obj in objects:
                    object_id = stable_id("semantic", run_id, index, digest(obj))
                    contract = raw["_contract"]
                    payload = {
                        **obj,
                        "model_contract": contract,
                        "field_id": field_id,
                        "build_id": run["build_id"],
                    }
                    conn.execute(
                        "INSERT OR IGNORE INTO fieldkg_semantic_objects VALUES(?,?,?,?,?,?,?,?,?,?,'PROPOSED',1,?,?,NULL,?)",
                        (
                            object_id,
                            run_id,
                            field_id,
                            run["build_id"],
                            obj["kind"],
                            obj["statement"],
                            obj["rationale"],
                            json.dumps(obj["references"], ensure_ascii=False),
                            json.dumps(obj["conditions"], ensure_ascii=False),
                            obj["confidence"],
                            json.dumps(contract, ensure_ascii=False),
                            digest(payload),
                            now,
                        ),
                    )
            return self._run(conn, run_id)

    def review(self, object_id: str, payload: ReviewSemantic) -> dict:
        if payload.object_id is not None and payload.object_id != object_id:
            raise WorkspaceError(404, "Semantic review target does not match its request")
        from .acquisition import utc_now

        raw = json.dumps(
            {"object_id": object_id, **payload.model_dump()}, ensure_ascii=False, sort_keys=True
        )
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT request_json,result_json FROM research_workspace_actions WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
            if old:
                if old["request_json"] != raw:
                    raise WorkspaceError(409, "Semantic review ID belongs to another operation")
                return json.loads(old["result_json"])
            obj = next(
                (
                    o
                    for o in semantic_objects(conn, payload.field_id)
                    if o["object_id"] == object_id
                ),
                None,
            )
            if obj is None:
                raise WorkspaceError(404, "Semantic object is outside this Field")
            if (
                obj["context_sha256"] != payload.expected_context_sha256
                or obj["status"] != "PROPOSED"
            ):
                raise WorkspaceError(409, "Semantic interpretation changed or was already reviewed")
            run = self._run(conn, obj["run_id"])
            if (
                conn.execute(
                    "SELECT status FROM fieldkg_builds WHERE build_id=?", (obj["build_id"],)
                ).fetchone()[0]
                == "SEALED"
            ):
                raise WorkspaceError(409, "Snapshot interpretations are immutable")
            if payload.decision == "ACCEPTED":
                from .research_views import build_context

                build = build_context(conn, obj["build_id"])
                if run["status"] != "COMPLETED" or digest(build["sources"]) != run["input_digest"]:
                    raise WorkspaceError(
                        409, "Review a completed extraction with the same original sources"
                    )
                if any(
                    not source_is_available(conn, ref["source"]["paper_version_id"])
                    for ref in obj["references"]
                ):
                    raise WorkspaceError(409, "An interpretation source requires review")
            now = utc_now()
            conn.execute(
                "UPDATE fieldkg_semantic_objects SET status=?,revision=revision+1,reviewed_at=? WHERE object_id=?",
                (payload.decision, now, object_id),
            )
            result = {
                "object_type": "fieldkg_semantic",
                "object_id": object_id,
                "request_id": payload.request_id,
                "review": next(
                    o
                    for o in semantic_objects(conn, payload.field_id)
                    if o["object_id"] == object_id
                ),
                "rationale": payload.rationale,
                "scientific_approval": False,
            }
            conn.execute(
                "INSERT INTO research_workspace_actions(request_id,request_json,object_type,object_id,result_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    payload.request_id,
                    raw,
                    result["object_type"],
                    object_id,
                    json.dumps(result, ensure_ascii=False),
                    now,
                ),
            )
            if payload.decision == "ACCEPTED":
                from .fieldkg_workspace import _enqueue

                _enqueue(
                    conn,
                    "FieldKGSemanticObject",
                    object_id,
                    payload.field_id,
                    result["review"],
                    now,
                )
            return result

    def abandon(self, field_id: str, run_id: str, payload: AbandonSemantic) -> dict:
        from .acquisition import utc_now

        if payload.field_id != field_id or payload.run_id is not None and payload.run_id!=run_id:
            raise WorkspaceError(404, "Extraction disposition belongs to another Field")
        raw = json.dumps(
            {"run_id": run_id, **payload.model_dump()}, ensure_ascii=False, sort_keys=True
        )
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT request_json,result_json FROM research_workspace_actions WHERE request_id=?",
                (payload.request_id,),
            ).fetchone()
            if old:
                if old["request_json"] != raw:
                    raise WorkspaceError(409, "Disposition request ID belongs to another action")
                return json.loads(old["result_json"])
            run = self._run(conn, run_id)
            if run["field_id"] != field_id:
                raise WorkspaceError(404, "Extraction belongs to another Field")
            if run["updated_at"] != payload.expected_updated_at or run["status"] in {
                "COMPLETED",
                "ABANDONED",
            }:
                raise WorkspaceError(
                    409, "Extraction changed or already resolved; compare its current records"
                )
            now = utc_now()
            conn.execute(
                "UPDATE fieldkg_semantic_runs SET status='ABANDONED',updated_at=? WHERE run_id=?",
                (now, run_id),
            )
            conn.execute(
                "UPDATE fieldkg_semantic_objects SET status='REJECTED',revision=revision+1,reviewed_at=? WHERE run_id=? AND status='PROPOSED'",
                (now, run_id),
            )
            result = {
                "object_type": "fieldkg_semantic_disposition",
                "object_id": run_id,
                "request_id": payload.request_id,
                "rationale": payload.rationale,
                "run": self._run(conn, run_id),
                "scientific_approval": False,
            }
            conn.execute(
                "INSERT INTO research_workspace_actions(request_id,request_json,object_type,object_id,result_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    payload.request_id,
                    raw,
                    result["object_type"],
                    run_id,
                    json.dumps(result, ensure_ascii=False),
                    now,
                ),
            )
            return result
