"""Bridge shared fixed-source discussions to Studio's explicit suggestion decisions."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .research_workspace import WorkspaceError
from .studio_context import bound_quote
from .studio_read_views import search_sources
from .studio_sources import model_source
from .studio_suggestions import MODEL_FORMAT
from .studio_suggestions import normalize as normalize_suggestions


def quotation(source: dict) -> dict:
    context = source["context"]
    target, record = context["target"], context["record"]
    generated = record.get("generated")
    revision = record.get("snapshot", {}).get("revision") if record.get("snapshot") else None
    if generated is not None:
        revision = generated["input_revision"]
    quote = bound_quote(
        manuscript_id=target["manuscript_id"], anchor_type=target["object_kind"],
        anchor_id=target["object_id"], anchor_revision=revision if revision is not None else 0,
        label=context["label"], text=context["object_text"],
        raw_text=record["block"]["text"] if generated else context["object_text"],
        quote={key: source["quote"][key] for key in ["text", "start", "end", "offset_unit", "annotation"] if key in source["quote"]},
        generated_version_id=target.get("generated_version_id"),
    )
    if generated:
        quote["source"].update(author_revision_known=revision is not None, generated_version=generated["version"])
    return quote


def prepare_payload(conn: sqlite3.Connection, model_input: dict) -> dict:
    source = model_input["source"]
    record = source["context"]["record"]
    quote = quotation(source)
    # Freeze the existing owned Track/Field retrieval now, never in the worker.
    sources = search_sources(conn, source["context"]["target"]["manuscript_id"], model_input["question"], limit=8)
    # Generated contexts have already verified references against the original model call.
    # Give those frozen sources precedence over mutable catalog/search metadata.
    fixed_sources = {}
    for item in [source, *model_input["additional_sources"]]:
        generated = item["context"]["record"].get("generated") or {}
        for reference in generated.get("references", []):
            if (reference.get("source_snapshot_available") is True
                    and reference.get("reference_snapshot_source") == "generation_input"
                    and (reference.get("source_context") or {}).get("available") is True):
                fixed_sources.setdefault(reference["evidence_id"], model_source(reference))
    for item in sources:
        fixed_sources.setdefault(item["evidence_id"], item)
    generated = record.get("generated")
    if generated:
        generated = {**generated, "references": [model_source(item) for item in generated["references"]]}
    def fixed(item):
        context = item["context"]
        return {"context": {key: context[key] for key in ["target", "scope_key", "label", "object_text", "versions", "context_sha256"]}, "quote": item["quote"]}
    conversation = [
        {**{key: message[key] for key in ["message_id", "request_id", "reply_to", "actor", "content", "call_record"]},
         "source": fixed(message), "additional_sources": [fixed(item) for item in message["additional_sources"]]}
        for message in model_input["conversation"]
    ]
    return {
        "author_question": model_input["question"],
        "anchor": {"type": quote["source"]["anchor_type"], "id": quote["source"]["anchor_id"], "revision": quote["source"]["anchor_revision"], "quote": quote},
        "document": record.get("snapshot", {}).get("document") if record.get("snapshot") else None,
        "generated_version": generated, "retrieved_evidence": list(fixed_sources.values()),
        "discussion_source": fixed(source),
        "additional_sources": [fixed(item) for item in model_input["additional_sources"]],
        "conversation": conversation, "suggestion_format": MODEL_FORMAT,
        "constraint": "Suggestions must not be applied to the manuscript. Previous replies are discussion, not evidence.",
    }


def author_projection(conn: sqlite3.Connection, model_input: dict, request_id: str, message_id: str, parent: str | None, timestamp: str) -> None:
    quote = quotation(model_input["source"])
    quote["_research_discussion"] = {"request_id": request_id, "context_sha256": model_input["source"]["context"]["context_sha256"]}
    source = quote["source"]
    conn.execute("INSERT INTO studio_chat_messages VALUES(?,?,?,?,?,?,?,?,?,?,?)", (message_id, source["manuscript_id"], parent, "AUTHOR", model_input["question"], source["anchor_type"], source["anchor_id"], source["anchor_revision"], json.dumps(quote, ensure_ascii=False, sort_keys=True), "QUEUED", timestamp))


def validated_suggestions(response: dict, payload: dict) -> list:
    evidence = response.get("evidence_ids", [])
    known = {item["evidence_id"] for item in payload["retrieved_evidence"]}
    if not isinstance(evidence, list) or any(not isinstance(item, str) or item not in known for item in evidence):
        raise ValueError("The Studio reply cites evidence not supplied in this fixed discussion")
    return normalize_suggestions(response.get("suggestions", []), payload["document"], payload["retrieved_evidence"])


def call_projection(conn: sqlite3.Connection, model_input: dict, author_id: str, response: dict | None, contract: dict | None, error: dict | None, started_at: str, completed_at: str) -> None:
    payload = model_input["writing_payload"]
    original_response = {key: value for key, value in response.items() if key != "_validated_studio_suggestions"} if response else None
    input_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    conn.execute("INSERT INTO studio_model_calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        model_input["studio_call_id"], model_input["source"]["context"]["target"]["manuscript_id"], None, author_id,
        "writing_chat", payload["anchor"]["revision"], hashlib.sha256(input_json.encode('utf-8')).hexdigest(), input_json,
        json.dumps(original_response, ensure_ascii=False, sort_keys=True) if original_response is not None else None,
        json.dumps(contract, ensure_ascii=False, sort_keys=True) if contract is not None else None,
        "REJECTED" if error and response is not None else "FAILED" if error else "RETURNED",
        json.dumps(error, ensure_ascii=False, sort_keys=True) if error else None, started_at, completed_at,
    ))


def agent_projection(conn: sqlite3.Connection, model_input: dict, request_id: str, author_id: str, agent_id: str, response: dict, timestamp: str) -> None:
    quote = quotation(model_input["source"])
    suggestions = response["_validated_studio_suggestions"]
    quote.update(evidence_ids=response.get("evidence_ids", []), _model_provenance={"model_contract": response.get("_contract"), "model_call_id": model_input["studio_call_id"]}, _research_discussion={"request_id": request_id, "context_sha256": model_input["source"]["context"]["context_sha256"]})
    if suggestions:
        quote.update(suggestions=suggestions, model_contract=response.get("_contract"))
    source = quote["source"]
    conn.execute("INSERT INTO studio_chat_messages VALUES(?,?,?,?,?,?,?,?,?,?,?)", (agent_id, source["manuscript_id"], author_id, "AGENT", response["answer"].strip(), source["anchor_type"], source["anchor_id"], source["anchor_revision"], json.dumps(quote, ensure_ascii=False, sort_keys=True), "SUGGESTION" if suggestions else "DISCUSSION", timestamp))
    conn.execute("UPDATE studio_chat_messages SET status='COMPLETE' WHERE message_id=?", (author_id,))


def studio_messages(conn: sqlite3.Connection, request_id: str) -> list[dict]:
    records = conn.execute("SELECT s.* FROM studio_chat_messages s JOIN research_discussion_messages r ON r.message_id=s.message_id WHERE r.request_id=? ORDER BY r.seq", (request_id,)).fetchall()
    result = []
    for row in records:
        verify_projection(conn, row)
        item = dict(row)
        item["quoted"] = json.loads(item.pop("quoted_json"))
        provenance = item["quoted"].pop("_model_provenance", None)
        if provenance:
            item["model_provenance"] = provenance
        result.append(item)
    return result


def verify_projection(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    """Existing read/decision APIs must not adopt an altered shared suggestion."""
    try:
        quote = json.loads(row["quoted_json"])
        marker = quote.get("_research_discussion")
        if not marker:
            return
        from .research_discussions import _verified_message

        common = conn.execute("SELECT * FROM research_discussion_messages WHERE message_id=?", (row["message_id"],)).fetchone()
        if common is None:
            raise WorkspaceError(410, "The original shared discussion is unavailable")
        message = _verified_message(conn, common)
        job = conn.execute("SELECT * FROM research_discussion_jobs WHERE request_id=?", (message["request_id"],)).fetchone()
        model_input = json.loads(job["input_json"])
        expected = quotation(model_input["source"])
        expected["_research_discussion"] = {"request_id": message["request_id"], "context_sha256": message["context"]["context_sha256"]}
        if row["role"] == "AGENT":
            response = json.loads(job["response_json"])
            expected.update(evidence_ids=response.get("evidence_ids", []), _model_provenance={"model_contract": response.get("_contract"), "model_call_id": model_input["studio_call_id"]})
            suggestions = response["_validated_studio_suggestions"]
            if suggestions:
                expected.update(suggestions=suggestions, model_contract=response.get("_contract"))
            call = conn.execute("SELECT * FROM studio_model_calls WHERE call_id=?", (model_input["studio_call_id"],)).fetchone()
            raw = {key: value for key, value in response.items() if key != "_validated_studio_suggestions"}
            if (call is None or call["manuscript_id"] != row["manuscript_id"]
                    or call["message_id"] != job["author_message_id"] or call["task"] != "writing_chat"
                    or call["status"] != "RETURNED" or json.loads(call["input_json"]) != model_input["writing_payload"]
                    or hashlib.sha256(call["input_json"].encode('utf-8')).hexdigest() != call["input_sha256"]
                    or json.loads(call["output_json"]) != raw
                    or json.loads(call["contract_json"] or 'null') != response.get("_contract")):
                raise WorkspaceError(410, "The Studio reply differs from its original model call")
        if (quote != expected or row["manuscript_id"] != expected["source"]["manuscript_id"]
                or row["role"] != message["actor"] or row["content"] != message["content"]
                or row["parent_message_id"] != message["reply_to"]
                or row["anchor_type"] != expected["source"]["anchor_type"]
                or row["anchor_id"] != expected["source"]["anchor_id"]
                or row["anchor_revision"] != expected["source"]["anchor_revision"]):
            raise WorkspaceError(410, "The Studio suggestion or source differs from its shared discussion")
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkspaceError(410, "The original Studio discussion record is inconsistent") from exc
