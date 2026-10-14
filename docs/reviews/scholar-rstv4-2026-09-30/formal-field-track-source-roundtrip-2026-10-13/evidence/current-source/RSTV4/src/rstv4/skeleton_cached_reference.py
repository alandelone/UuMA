"""Revalidate exact verified source parents instead of regenerating unchanged graphs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_endpoint_review import (
    ENDPOINT_REVIEW_VERSION,
    RELATION_ONTOLOGY,
    atom_index,
    validate_endpoint_verdict,
)
from rstv4.skeleton_graph_reference import (
    alias_claims,
    discourse_cues,
    restore_graph,
    validate_graph,
)
from rstv4.skeleton_mapped_graph_v2 import (
    MAPPED_GRAPH_VERSION,
    MAPPED_VERIFIED_VERSION,
    MappedVerifiedReferenceBuilder,
    mapped_graph,
    read,
    restore_mapped_graph,
)
from rstv4.skeleton_verified_reference import reference_edge_inputs

CACHED_REFERENCE_VERSION = "exact-source-parent-all-round-and-endpoint-revalidation-v1"


def validate_cached_source_edge(inputs: dict, synthetic: dict, index: int,
                                record: dict, edge_root: Path) -> None:
    edge = synthetic["relations"][index]
    atoms = atom_index(synthetic)
    source_block, source = atoms[edge["source_id"]]
    target_block, target = atoms[edge["target_id"]]
    blocks = [block for block in json.loads(inputs["source_blocks"])
              if block["block_id"] in {source_block, target_block}]
    values = {"document_context": inputs["document_context"], "source_blocks": json_text(blocks),
              "source_atom": json_text(source), "target_atom": json_text(target),
              "candidate_edge": json_text(edge), "relation_ontology": RELATION_ONTOLOGY}
    key = digest({"version": ENDPOINT_REVIEW_VERSION, "inputs": values})
    if record["input_digest"] != key or read(edge_root / f"{key}.json") != record:
        raise SourceContractError("Verified source parent endpoint cache/input changed")
    if record["status"] != "ASSESSED":
        raise SourceContractError("Verified source parent retains an evaluator failure")
    validate_endpoint_verdict(edge, source, target, record["verdict"])


class CachedVerifiedReferenceBuilder(MappedVerifiedReferenceBuilder):
    def __init__(self, output: Path, *, legacy_verified: list[tuple[Path, Path]] | None = None,
                 **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.legacy_verified = legacy_verified or []

    def build(self, inputs: dict[str, str]) -> dict:
        key = digest({"version": MAPPED_VERIFIED_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        if path.exists():
            result = super().build(inputs)
            saved = read(path)
            if saved.get("origin") == "EXACT_REVALIDATED_VERIFIED_SOURCE_PARENT":
                parent = read(Path(saved["parent_path"]))
                if digest(parent) != saved["parent_digest"] or parent["reference"] != result:
                    raise SourceContractError("Reused verified source parent changed")
                if digest(read(Path(saved["parent_draft_path"]))) != saved["parent_draft_digest"]:
                    raise SourceContractError("Reused verified source draft parent changed")
                parent_path = Path(saved["parent_path"])
                for meta in parent["rounds"]:
                    record = read(parent_path.parent.parent / "rounds" / parent_path.stem / f"{meta['round']:03d}.json")
                    own = read(self.output / "rounds" / key / f"{meta['round']:03d}.json")
                    if digest(record) != meta["round_digest"] or own != record:
                        raise SourceContractError("Reused source correction parent round changed")
                    synthetic = reference_edge_inputs(record["reference"], json.loads(inputs["source_blocks"]))
                    for index, edge in enumerate(record["edge_reviews"]):
                        validate_cached_source_edge(inputs, synthetic, index, edge, self.edges.output / "edges")
            return result
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.drafts.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [claim for part in parts for claim in part["claims"]],
                "roles": [role for part in parts for role in part["roles"]], "relations": []}
        _, mapping = alias_claims(base["claims"])
        cues = discourse_cues(blocks)
        # Parent priority is explicitly supplied, fixed before any candidate performance.
        for parent_root, parent_draft_root in self.legacy_verified:
            for parent_path in sorted((parent_root / "references").glob("*.json")):
                parent = read(parent_path)
                if (parent["inputs_digest"] != digest(inputs)
                        or parent["atomic_reference_digest"] != digest(base)):
                    continue
                if (parent["candidate_access"] is not False or parent["source_graph_review_gate_passed"] is not True
                        or parent["identifier_map"] != mapping
                        or {**copy.deepcopy(parent["reference"]), "relations": []} != base):
                    raise SourceContractError("Verified parent source content/isolation changed")
                if validate_graph(base, blocks, cues, parent["graph_review"]) != parent["reference"]["relations"]:
                    raise SourceContractError("Verified parent final graph differs from its reference")
                parent_drafts = [item for item in (parent_draft_root / "references").glob("*.json")
                                 if read(item)["inputs_digest"] == digest(inputs)]
                if len(parent_drafts) != 1:
                    raise SourceContractError("Verified parent requires exactly its own draft graph")
                parent_draft = read(parent_drafts[0])
                if (digest(parent_draft) != parent["draft_record_digest"]
                        or digest(parent_draft["reference"]) != parent["draft_reference_digest"]
                        or parent_draft["atomic_reference_digest"] != digest(base)):
                    raise SourceContractError("Verified parent draft lineage changed")
                validate_graph(base, blocks, cues, parent_draft["graph_review"])
                if len(base["claims"]) >= 2:
                    stages = parent_draft["stages"]
                    first, second = stages["INITIAL_SOURCE_GRAPH_ANNOTATION"], stages["INDEPENDENT_SOURCE_GRAPH_REVIEW"]
                    if first["input_digest"] == second["input_digest"] or second["graph"] != parent_draft["graph_review"]:
                        raise SourceContractError("Verified parent source stages reused or changed requests")
                retained = []
                for meta in parent["rounds"]:
                    round_path = parent_root / "rounds" / parent_path.stem / f"{meta['round']:03d}.json"
                    record = read(round_path)
                    if (digest(record) != meta["round_digest"]
                            or {**copy.deepcopy(record["reference"]), "relations": []} != base
                            or validate_graph(base, blocks, cues, record["graph_review"]) != record["reference"]["relations"]):
                        raise SourceContractError("Verified parent correction round changed source/graph")
                    synthetic = reference_edge_inputs(record["reference"], blocks)
                    if len(record["edge_reviews"]) != len(synthetic["relations"]):
                        raise SourceContractError("Verified parent round omitted endpoint judgments")
                    for index, edge in enumerate(record["edge_reviews"]):
                        validate_cached_source_edge(inputs, synthetic, index, edge, self.edges.output / "edges")
                    passed = all(item["verdict"]["verdict"] == "SUPPORTED" for item in record["edge_reviews"])
                    if passed != record["source_graph_review_gate_passed"]:
                        raise SourceContractError("Verified parent round misreported acceptance")
                    retained.append(record)
                if (not retained or not retained[-1]["source_graph_review_gate_passed"]
                        or retained[-1]["reference"] != parent["reference"]
                        or retained[-1]["graph_review"] != parent["graph_review"]):
                    raise SourceContractError("Verified parent final supported round differs")
                original = self.drafts.build(inputs)
                draft_key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
                draft = read(self.drafts.output / "references" / f"{draft_key}.json")
                if original != parent_draft["reference"]:
                    raise SourceContractError("Effective original graph differs from verified parent's draft")
                graph = parent["graph_review"]
                encoded = mapped_graph(restore_graph(graph, {value: alias for alias, value in mapping.items()}))
                if restore_mapped_graph(encoded, mapping, cues) != graph:
                    raise SourceContractError("Verified source parent conversion lost canonical decisions")
                for meta, record in zip(parent["rounds"], retained, strict=True):
                    write_json(self.output / "rounds" / key / f"{meta['round']:03d}.json", record)
                saved = {**parent, "version": MAPPED_VERIFIED_VERSION,
                         "draft_record_digest": digest(draft), "mapped_graph": encoded,
                         "origin": "EXACT_REVALIDATED_VERIFIED_SOURCE_PARENT",
                         "reuse_protocol": CACHED_REFERENCE_VERSION, "parent_path": str(parent_path),
                         "parent_digest": digest(parent), "parent_draft_path": str(parent_drafts[0]),
                         "parent_draft_digest": digest(parent_draft), "new_semantic_inference_calls": 0}
                write_json(path, saved)
                return saved["reference"]
        return super().build(inputs)
