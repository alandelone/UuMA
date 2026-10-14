"""Source graphs with unique claim, cue and edge keys; preserve canonical validation."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Literal

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import BaseModel, ConfigDict, Field

from rstv4.skeleton_context_reference import ContextSourceReferenceBuilder as SourceReferenceBuilder
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_endpoint_review import RELATION_ONTOLOGY, EndpointEdgeReviewer
from rstv4.skeleton_experiment import ReferenceRelation
from rstv4.skeleton_graph_reference import (
    GRAPH_REFERENCE_VERSION,
    SourceGraphAnnotation,
    SourceGraphEdge,
    SourceGraphReview,
    alias_claims,
    discourse_cues,
    edge_key,
    restore_graph,
    validate_graph,
)
from rstv4.skeleton_mapped_review import UniqueKeyJSONAdapter
from rstv4.skeleton_table_reference import TableAtomicReference
from rstv4.skeleton_verified_reference import edge_correction_feedback, reference_edge_inputs

MAPPED_GRAPH_VERSION = "source-graph-lossless-unique-claim-cue-edge-keys-v4"
MAPPED_VERIFIED_VERSION = "source-graph-lossless-unique-keys-isolated-edge-verified-v5"


class ConnectionValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outgoing_edge_ids: list[str]
    no_outgoing_rationale: str | None


class CueValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal[
        "SUPPORTED_RELATION", "WITHIN_ONE_CLAIM", "STRUCTURAL_OR_NON_RELATIONAL", "AMBIGUOUS",
    ]
    relation_ids: list[str]
    relation_rationales: dict[str, str] = Field(default_factory=dict)
    rationale: str


class MappedSourceGraphAnnotation(dspy.Signature):
    review_stage: str = dspy.InputField()
    document_context: str = dspy.InputField()
    source_blocks: str = dspy.InputField()
    reference_claims: str = dspy.InputField()
    discourse_cues: str = dspy.InputField()
    relation_ontology: str = dspy.InputField()
    repair_feedback: str = dspy.InputField()
    edges: dict[str, SourceGraphEdge] = dspy.OutputField()
    connections: dict[str, ConnectionValue] = dspy.OutputField()
    cue_resolutions: dict[str, CueValue] = dspy.OutputField()
    corrections: list[str] = dspy.OutputField()


class MappedSourceGraphReview(MappedSourceGraphAnnotation):
    draft_graph: str = dspy.InputField()


KEY_INSTRUCTIONS = (
    "\n\nUse three separate JSON OBJECTS. edges maps unique e0, e1, ... IDs to complete "
    "SourceGraphEdge records. Define each edge once, including actual source and target r-IDs, "
    "type, rationale and each endpoint's own evidence spans. connections maps EVERY supplied "
    "r-ID exactly once to outgoing_edge_ids and no_outgoing_rationale. Each defined edge must "
    "appear exactly once under its actual source claim. cue_resolutions maps EVERY supplied "
    "cue_id exactly once to classification, relation_ids, relation_rationales and rationale. "
    "relation_rationales is an optional object keyed by the named edge IDs, retaining a "
    "cue-specific explanation when it differs from the edge explanation. When supplied, "
    "include every named relation ID exactly once. relation_ids may only "
    "reference edges defined in this same output. Do not retype endpoint/type triples inside "
    "cue decisions. If correcting/removing an edge, update its connection and cue decisions "
    "together. Preserve genuine unresolved interpretation as AMBIGUOUS; never invent an edge "
    "or relabel a cue merely to pass validation. No duplicate JSON keys or undeclared fields. "
    "All original source coverage, evidence, ontology and omission requirements still apply."
)
MappedSourceGraphAnnotation = MappedSourceGraphAnnotation.with_instructions(
    SourceGraphAnnotation.instructions + KEY_INSTRUCTIONS,
)
MappedSourceGraphReview = MappedSourceGraphReview.with_instructions(
    SourceGraphReview.instructions + KEY_INSTRUCTIONS,
)


def restore_mapped_graph(value: dict, mapping: dict[str, str], cues: list[dict]) -> dict:
    """Dereference explicit model edge IDs without adding or correcting scientific links."""
    if set(value["connections"]) != mapping.keys():
        raise SourceContractError("Mapped graph must examine all and only supplied claim keys")
    if set(value["cue_resolutions"]) != {cue["cue_id"] for cue in cues}:
        raise SourceContractError("Mapped graph must examine all and only supplied cue keys")
    edges = value["edges"]
    if any(not re.fullmatch(r"e\d+", key) for key in edges):
        raise SourceContractError("Mapped graph edge identifiers must use distinct e-number keys")
    edges = {key: SourceGraphEdge.model_validate(edge).model_dump() for key, edge in edges.items()}
    connection_order = value.get("connection_order", list(mapping))
    cue_order = value.get("cue_order", [cue["cue_id"] for cue in cues])
    if (len(connection_order) != len(mapping) or set(connection_order) != mapping.keys()
            or len(cue_order) != len(cues) or set(cue_order) != {cue["cue_id"] for cue in cues}):
        raise SourceContractError("Graph provenance order must retain each claim/cue exactly once")
    connections, used = [], []
    for alias in connection_order:
        item = ConnectionValue.model_validate(value["connections"][alias]).model_dump()
        ids = item["outgoing_edge_ids"]
        if len(ids) != len(set(ids)) or any(key not in edges for key in ids):
            raise SourceContractError("Claim connection names duplicate or absent edge keys")
        if any(edges[key]["source_reference_id"] != alias for key in ids):
            raise SourceContractError("Mapped outgoing edge must start at its examined claim")
        connections.append({"reference_id": alias, "outgoing_relations": [edges[key] for key in ids],
                            "no_outgoing_rationale": item["no_outgoing_rationale"]})
        used.extend(ids)
    if len(used) != len(edges) or set(used) != edges.keys():
        raise SourceContractError("Every defined edge must be connected exactly once")
    decisions = []
    for cue_id in cue_order:
        item = CueValue.model_validate(value["cue_resolutions"][cue_id]).model_dump()
        ids = item.pop("relation_ids")
        rationales = item.pop("relation_rationales")
        if rationales and (set(rationales) != set(ids) or any(not value.strip() for value in rationales.values())):
            raise SourceContractError("Cue-specific explanations must name all and only its explicit relation IDs")
        if len(ids) != len(set(ids)) or any(key not in edges for key in ids):
            raise SourceContractError("Discourse cue names duplicate or absent edge keys")
        decisions.append({"cue_id": cue_id, **item, "relation_keys": [
            {**{name: edges[key][name] for name in ReferenceRelation.model_fields},
             "rationale": rationales.get(key, edges[key]["rationale"])} for key in ids
        ]})
    return restore_graph({"connections": connections, "cue_resolutions": decisions,
                          "corrections": value["corrections"]}, mapping)


def mapped_graph(graph: dict) -> dict:
    """Encode an already validated canonical graph without changing an edge or cue decision."""
    edges, keys, connections = {}, {}, {}
    for record in graph["connections"]:
        ids = []
        for edge in record["outgoing_relations"]:
            key = edge_key(edge)
            if key in keys:
                raise SourceContractError("Cannot encode duplicate canonical graph edges")
            name = f"e{len(edges)}"
            edges[name], keys[key] = copy.deepcopy(edge), name
            ids.append(name)
        connections[record["reference_id"]] = {
            "outgoing_edge_ids": ids, "no_outgoing_rationale": record["no_outgoing_rationale"],
        }
    cues = {}
    for item in graph["cue_resolutions"]:
        if any(edge_key(edge) not in keys for edge in item["relation_keys"]):
            raise SourceContractError("Cannot encode a cue referencing an absent canonical edge")
        cues[item["cue_id"]] = {
            "classification": item["classification"], "rationale": item["rationale"],
            "relation_ids": [keys[edge_key(edge)] for edge in item["relation_keys"]],
            "relation_rationales": {keys[edge_key(edge)]: edge["rationale"] for edge in item["relation_keys"]},
        }
    return {"edges": edges, "connections": connections, "cue_resolutions": cues,
            "connection_order": list(connections), "cue_order": list(cues),
            "corrections": copy.deepcopy(graph["corrections"])}


def prediction_graph(result: Any) -> dict:
    return {"edges": {key: item.model_dump() for key, item in result.edges.items()},
            "connection_order": list(result.connections), "cue_order": list(result.cue_resolutions),
            "connections": {key: item.model_dump() for key, item in result.connections.items()},
            "cue_resolutions": {key: item.model_dump() for key, item in result.cue_resolutions.items()},
            "corrections": result.corrections}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class MappedGraphReferenceBuilder:
    def __init__(self, output: Path, *, actual_model: str, atomic_source: Path | None = None,
                 legacy_source: Path | None = None, table_output: Path | None = None) -> None:
        self.output, self.legacy_source = output, legacy_source
        original = SourceReferenceBuilder(atomic_source or output / "atomic-block-reference",
                                          actual_model=actual_model)
        self.atomic = TableAtomicReference(original, table_output or output / "table-field-ledgers")
        self.lm = ReceiptLM("thinking", output / "graph-teacher-lm", max_tokens=24000,
                            required_actual_model=actual_model)
        self.annotator = dspy.Predict(MappedSourceGraphAnnotation)
        self.reviewer = dspy.Predict(MappedSourceGraphReview)

    def build(self, inputs: dict[str, str]) -> dict:
        key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [claim for part in parts for claim in part["claims"]],
                "roles": [role for part in parts for role in part["roles"]], "relations": []}
        claims, mapping = alias_claims(base["claims"])
        cues = discourse_cues(blocks)
        if path.exists():
            saved = read(path)
            if (saved["inputs_digest"] != digest(inputs) or saved["identifier_map"] != mapping
                    or saved["atomic_reference_digest"] != digest(base)):
                raise SourceContractError("Mapped source graph lineage changed")
            graph = restore_mapped_graph(saved["mapped_graph"], mapping, cues)
            if graph != saved["graph_review"]:
                raise SourceContractError("Mapped graph differs from canonical source judgments")
            edges = validate_graph(base, blocks, cues, graph)
            if saved["reference"] != {**base, "relations": edges}:
                raise SourceContractError("Mapped source reference differs from reviewed graph")
            if saved.get("parent_path") and digest(read(Path(saved["parent_path"]))) != saved["parent_digest"]:
                raise SourceContractError("Mapped source graph parent changed")
            return saved["reference"]
        legacy = None
        if self.legacy_source:
            old_key = digest({"version": GRAPH_REFERENCE_VERSION, "inputs": inputs})
            old_path = self.legacy_source / "references" / f"{old_key}.json"
            if old_path.exists():
                parent = read(old_path)
                if (parent["inputs_digest"] == digest(inputs) and parent["identifier_map"] == mapping
                        and parent["atomic_reference_digest"] == digest(base)):
                    relations = validate_graph(base, blocks, cues, parent["graph_review"])
                    if parent["reference"] != {**base, "relations": relations} or parent["candidate_access"] is not False:
                        raise SourceContractError("Legacy source graph content or isolation changed")
                    if len(claims) >= 2:
                        first = parent["stages"]["INITIAL_SOURCE_GRAPH_ANNOTATION"]
                        second = parent["stages"]["INDEPENDENT_SOURCE_GRAPH_REVIEW"]
                        if first["input_digest"] == second["input_digest"] or second["graph"] != parent["graph_review"]:
                            raise SourceContractError("Legacy graph stages are not distinct reviews")
                    legacy = parent, old_path
        attempts, stages = [], {}
        if legacy:
            parent, old_path = legacy
            graph, stages = parent["graph_review"], parent["stages"]
            aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
            value, origin = mapped_graph(aliased), "EXACT_VALID_LEGACY_GRAPH"
        elif len(claims) < 2:
            value = {"edges": {}, "connections": {
                alias: {"outgoing_edge_ids": [], "no_outgoing_rationale":
                        "Fewer than two reference claims; no distinct endpoint pair."} for alias in mapping
            }, "cue_resolutions": {cue["cue_id"]: {
                "classification": "STRUCTURAL_OR_NON_RELATIONAL", "relation_ids": [],
                "rationale": "No distinct pair of reference claims exists in this source window."
            } for cue in cues}, "corrections": []}
            graph, origin = restore_mapped_graph(value, mapping, cues), "NO_DISTINCT_ENDPOINT_PAIR"
        else:
            values = {**inputs, "reference_claims": json_text(claims), "discourse_cues": json_text(cues),
                      "relation_ontology": RELATION_ONTOLOGY}
            draft = None
            for stage, predictor in (("INITIAL_SOURCE_GRAPH_ANNOTATION", self.annotator),
                                     ("INDEPENDENT_SOURCE_GRAPH_REVIEW", self.reviewer)):
                feedback = ""
                for attempt in range(3):
                    try:
                        stage_values = {**values, "review_stage": stage}
                        if draft is not None:
                            stage_values["draft_graph"] = json_text(draft)
                        with dspy.context(lm=self.lm, adapter=UniqueKeyJSONAdapter()):
                            result = predictor(**stage_values, repair_feedback=feedback)
                        value = prediction_graph(result)
                        graph = restore_mapped_graph(value, mapping, cues)
                        validate_graph(base, blocks, cues, graph,
                                       require_resolved=stage == "INDEPENDENT_SOURCE_GRAPH_REVIEW")
                        stages[stage] = {"input_digest": digest(stage_values), "graph": graph,
                                         "mapped_graph": value}
                        draft = value
                        break
                    except (AdapterParseError, SourceContractError, ValueError, TypeError) as exc:
                        attempts.append({"stage": stage, "attempt": attempt + 1, "error": str(exc)[:2500]})
                        write_json(self.output / "failures" / f"{key}.json", {"attempts": attempts})
                        feedback = "Regenerate the complete graph. Preserve every claim/cue and actual endpoint evidence. " + str(exc)[:2500]
                else:
                    raise SourceContractError("Mapped source graph failed: " + attempts[-1]["error"])
            if stages["INITIAL_SOURCE_GRAPH_ANNOTATION"]["input_digest"] == stages["INDEPENDENT_SOURCE_GRAPH_REVIEW"]["input_digest"]:
                raise SourceContractError("Mapped graph stages must use distinct requests")
            origin = "UNIQUE_KEY_SOURCE_GRAPH"
        relations = validate_graph(base, blocks, cues, graph)
        reference = {**base, "relations": relations}
        saved = {"version": MAPPED_GRAPH_VERSION, "inputs_digest": digest(inputs), "identifier_map": mapping,
                 "atomic_reference_digest": digest(base), "reference": reference, "graph_review": graph,
                 "mapped_graph": value, "stages": stages, "failed_attempts": attempts, "origin": origin,
                 "candidate_access": False, "status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD"}
        if legacy:
            saved.update({"parent_path": str(old_path), "parent_digest": digest(parent)})
        write_json(path, saved)
        return reference


class MappedVerifiedReferenceBuilder:
    def __init__(self, output: Path, *, actual_model: str, atomic_source: Path | None = None,
                 draft_source: Path | None = None, edge_source: Path | None = None,
                 legacy_draft: Path | None = None) -> None:
        self.output = output
        self.drafts = MappedGraphReferenceBuilder(
            draft_source or output / "draft-source-graph", actual_model=actual_model,
            atomic_source=atomic_source, legacy_source=legacy_draft, table_output=output / "table-field-ledgers",
        )
        self.edges = EndpointEdgeReviewer(edge_source or output / "source-edge-review", actual_model=actual_model)
        self.lm = ReceiptLM("thinking", output / "correction-teacher-lm", max_tokens=24000,
                            required_actual_model=actual_model)
        self.corrector = dspy.Predict(MappedSourceGraphReview)

    def build(self, inputs: dict[str, str]) -> dict:
        key = digest({"version": MAPPED_VERIFIED_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        blocks = json.loads(inputs["source_blocks"])
        original = self.drafts.build(inputs)
        draft_key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
        draft_record = read(self.drafts.output / "references" / f"{draft_key}.json")
        base = {**copy.deepcopy(original), "relations": []}
        claims, mapping = alias_claims(base["claims"])
        aliases = {value: alias for alias, value in mapping.items()}
        cues = discourse_cues(blocks)
        if path.exists():
            saved = read(path)
            if (saved["inputs_digest"] != digest(inputs) or saved["draft_reference_digest"] != digest(original)
                    or saved["atomic_reference_digest"] != digest(base) or saved["draft_record_digest"] != digest(draft_record)):
                raise SourceContractError("Mapped isolated-edge source lineage changed")
            if restore_mapped_graph(saved["mapped_graph"], mapping, cues) != saved["graph_review"]:
                raise SourceContractError("Mapped final graph differs from its canonical judgments")
            relations = validate_graph(base, blocks, cues, saved["graph_review"])
            if saved["reference"] != {**base, "relations": relations} or not saved["source_graph_review_gate_passed"]:
                raise SourceContractError("Mapped final source graph differs or needs review")
            if saved.get("parent_path") and digest(read(Path(saved["parent_path"]))) != saved["parent_digest"]:
                raise SourceContractError("Mapped verified source parent changed")
            return saved["reference"]
        graph, reference, rounds = copy.deepcopy(draft_record["graph_review"]), copy.deepcopy(original), []
        for round_index in range(4):
            synthetic = reference_edge_inputs(reference, blocks)
            results = [self.edges.assess(inputs, synthetic, index) for index in range(len(reference["relations"]))]
            passed = all(item["status"] == "ASSESSED" and item["verdict"]["verdict"] == "SUPPORTED" for item in results)
            round_record = {"round": round_index, "reference": reference, "graph_review": graph,
                            "edge_reviews": results, "source_graph_review_gate_passed": passed}
            write_json(self.output / "rounds" / key / f"{round_index:03d}.json", round_record)
            rounds.append({"round": round_index, "round_digest": digest(round_record), "edges": len(results),
                           "source_graph_review_gate_passed": passed})
            if passed:
                encoded = mapped_graph(restore_graph(graph, aliases))
                write_json(path, {"version": MAPPED_VERIFIED_VERSION, "inputs_digest": digest(inputs),
                    "reference": reference, "graph_review": graph, "mapped_graph": encoded,
                    "identifier_map": mapping, "draft_reference_digest": digest(original),
                    "draft_record_digest": digest(draft_record), "atomic_reference_digest": digest(base),
                    "rounds": rounds, "candidate_access": False, "source_graph_review_gate_passed": True,
                    "status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD", "origin": "UNIQUE_KEY_EDGE_VERIFIED_GRAPH"})
                return reference
            if any(item["status"] != "ASSESSED" for item in results):
                raise SourceContractError("Source edge evaluator failed; preserve judgments and repair evaluator")
            if round_index == 3:
                raise SourceContractError("Source graph has unsupported/uncertain edges after three full corrections")
            values = {**inputs, "review_stage": "SOURCE_GRAPH_CORRECTION_AFTER_ISOLATED_ENDPOINT_REVIEW",
                      "reference_claims": json_text(claims), "discourse_cues": json_text(cues),
                      "relation_ontology": RELATION_ONTOLOGY, "draft_graph": json_text(mapped_graph(restore_graph(graph, aliases)))}
            feedback = ("Correct the COMPLETE source graph against isolated actual endpoint judgments. "
                        "Preserve sound links, review omissions, keep claims/qualifiers/IDs unchanged. "
                        + json_text(edge_correction_feedback(reference, results, aliases)))
            failures = []
            for attempt in range(3):
                try:
                    with dspy.context(lm=self.lm, adapter=UniqueKeyJSONAdapter()):
                        result = self.corrector(**values, repair_feedback=feedback)
                    encoded = prediction_graph(result)
                    proposed = restore_mapped_graph(encoded, mapping, cues)
                    relations = validate_graph(base, blocks, cues, proposed)
                    write_json(self.output / "corrections" / key / f"{round_index + 1:03d}.json", {
                        "inputs_digest": digest({**values, "repair_feedback": feedback}), "mapped_graph": encoded,
                        "graph_review": proposed, "failed_attempts": failures})
                    graph, reference = proposed, {**base, "relations": relations}
                    break
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as exc:
                    failures.append(str(exc)[:2500])
                    write_json(self.output / "failures" / f"{key}-round-{round_index + 1}.json", {"failures": failures})
                    feedback += "\nRegenerate all explicit edges, claim keys and cue keys together. " + str(exc)[:2500]
            else:
                raise SourceContractError("Mapped full graph correction failed: " + failures[-1])
        raise AssertionError("Source verification exhausted without explicit terminal outcome")
