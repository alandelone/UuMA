"""Preserve individually unchanged verified edges during atomic reference revisions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import dspy

from rstv4.skeleton_cached_reference import (
    CachedVerifiedReferenceBuilder,
    validate_cached_source_edge,
)
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_graph_reference import alias_claims, discourse_cues, edge_key, validate_graph
from rstv4.skeleton_mapped_graph_v2 import (
    MAPPED_GRAPH_VERSION,
    MappedGraphReferenceBuilder,
    MappedSourceGraphReview,
    read,
)
from rstv4.skeleton_verified_reference import reference_edge_inputs

PRESERVED_REFERENCE_VERSION = "unchanged-verified-edge-retention-with-specific-cue-repair-v1"
PRESERVATION_INSTRUCTIONS = (
    "\nPreserved_source_edges are previously independently SUPPORTED edges with exactly unchanged "
    "endpoint propositions, quotes, qualifications and raw source. Retain every supplied complete "
    "edge unchanged, including its rationale and evidence, while inspecting all new/changed claims "
    "and omissions. Only endpoint ID FIELDS use current aliases: old aliases mentioned in parent "
    "rationale text are historical, not new endpoint assignments. Use actual attached claims/source. "
    "Never return an empty graph that discards these validated unchanged links. They are source "
    "references, not learner predictions. A SUPPORTED_RELATION cue needs a nonempty relation_ids "
    "list naming defined edges at that cue's actual evidence. Non-relational/within-claim cues use "
    "no edge IDs. Preserve genuine uncertainty as AMBIGUOUS. When isolated criticism rejects a "
    "new edge, do not keep that same type/direction tuple unchanged; re-read source and change the "
    "complete graph/cues consistently or leave ambiguity explicit. Do not invent a replacement."
)


def source_rejections(feedback: str) -> list[dict]:
    for position, char in enumerate(feedback):
        if char != "[":
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(feedback[position:])
        except ValueError:
            continue
        required = {"source_reference_id", "target_reference_id", "relation", "source_review"}
        if isinstance(value, list) and value and all(isinstance(item, dict) and required <= item.keys() for item in value):
            return value
    return []


class PreservedGraphPredictor:
    def __init__(self, signature: type, owner: PreservedGraphReferenceBuilder) -> None:
        self.owner = owner
        signature = signature.append("preserved_source_edges", dspy.InputField()).with_instructions(
            signature.instructions + PRESERVATION_INSTRUCTIONS,
        )
        self.predictor = dspy.Predict(signature)

    def __call__(self, **values: str) -> Any:
        constraints = self.owner.constraint_edges
        result = self.predictor(**values, preserved_source_edges=json_text(constraints))
        edges = [item.model_dump() for item in result.edges.values()]
        by_key = {edge_key(edge): edge for edge in edges}
        for edge in constraints:
            if by_key.get(edge_key(edge)) != edge:
                raise SourceContractError("Complete graph lost/changed unchanged verified edge: " + json_text(edge))
        for cue_id, cue in result.cue_resolutions.items():
            if (cue.classification == "SUPPORTED_RELATION") != bool(cue.relation_ids):
                raise SourceContractError("Cue " + cue_id + " has inconsistent classification/link IDs; "
                                          "SUPPORTED_RELATION needs actual defined links; nonrelation/within-claim/ambiguity needs no links.")
            missing = [key for key in cue.relation_ids if key not in result.edges]
            if missing:
                raise SourceContractError("Cue " + cue_id + " references absent explicit edges " + json_text(missing))
        for name, edge in result.edges.items():
            if edge.relation == "UNKNOWN":
                raise SourceContractError("Source edge " + name + " is UNKNOWN; preserve actual unresolved meaning "
                                          "as cue ambiguity rather than an unverified reference edge.")
        for rejected in source_rejections(values["repair_feedback"]):
            if edge_key(rejected) in by_key:
                raise SourceContractError("Rejected source tuple recurred unchanged: "
                                          + json_text({key: rejected[key] for key in (
                                              "source_reference_id", "target_reference_id", "relation", "source_review")}))
        return result


class PreservedGraphReferenceBuilder(MappedGraphReferenceBuilder):
    def __init__(self, output: Path, *, source_parents: list[tuple[Path, Path]], edge_root: Path,
                 **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.source_parents, self.edge_root = source_parents, edge_root
        self.constraint_edges: list[dict] = []
        self.ledger: list[dict] = []
        self.annotator = PreservedGraphPredictor(self.annotator.signature, self)
        self.reviewer = PreservedGraphPredictor(self.reviewer.signature, self)

    def build(self, inputs: dict[str, str]) -> dict:
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [claim for part in parts for claim in part["claims"]],
                "roles": [role for part in parts for role in part["roles"]], "relations": []}
        claims = {claim["reference_id"]: claim for claim in base["claims"]}
        roles = {role["block_id"]: role for role in base["roles"]}
        _, mapping = alias_claims(base["claims"])
        aliases = {value: alias for alias, value in mapping.items()}
        selected = {}
        for parent_root, _ in self.source_parents:
            for path in sorted((parent_root / "references").glob("*.json")):
                parent = read(path)
                if parent["inputs_digest"] != digest(inputs):
                    continue
                if parent["candidate_access"] is not False or parent["source_graph_review_gate_passed"] is not True:
                    raise SourceContractError("Preserved edge parent lacks source-only verification")
                before = {claim["reference_id"]: claim for claim in parent["reference"]["claims"]}
                old_roles = {role["block_id"]: role for role in parent["reference"]["roles"]}
                original_base = {**copy.deepcopy(parent["reference"]), "relations": []}
                if validate_graph(original_base, blocks, discourse_cues(blocks), parent["graph_review"]) != parent["reference"]["relations"]:
                    raise SourceContractError("Preserved edge parent canonical graph changed")
                last_meta = parent["rounds"][-1]
                last = read(parent_root / "rounds" / path.stem / f"{last_meta['round']:03d}.json")
                if (digest(last) != last_meta["round_digest"] or last["reference"] != parent["reference"]
                        or not last["source_graph_review_gate_passed"]):
                    raise SourceContractError("Preserved edge parent final supported round changed")
                synthetic = reference_edge_inputs(parent["reference"], blocks)
                full = {edge_key(edge): edge for item in parent["graph_review"]["connections"] for edge in item["outgoing_relations"]}
                for index, edge in enumerate(parent["reference"]["relations"]):
                    ids = [edge["source_reference_id"], edge["target_reference_id"]]
                    if not all(item in claims and before[item] == claims[item]
                               and old_roles[before[item]["block_id"]] == roles[claims[item]["block_id"]] for item in ids):
                        continue
                    judgment = last["edge_reviews"][index]
                    validate_cached_source_edge(inputs, synthetic, index, judgment, self.edge_root)
                    if judgment["verdict"]["verdict"] != "SUPPORTED":
                        raise SourceContractError("Unchanged source edge lacks a supported exact judgment")
                    selected.setdefault(edge_key(edge), {"edge": full[edge_key(edge)], "parent_path": str(path),
                        "parent_digest": digest(parent), "judgment_digest": digest(judgment),
                        "judgment_input_digest": judgment["input_digest"],
                        "source_claim_digest": digest(claims[ids[0]]), "target_claim_digest": digest(claims[ids[1]])})
        self.ledger = list(selected.values())
        self.constraint_edges = copy.deepcopy([item["edge"] for item in self.ledger])
        for edge in self.constraint_edges:
            for name in ("source_reference_id", "target_reference_id"):
                edge[name] = aliases[edge[name]]
        reference = super().build(inputs)
        key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        saved = read(path)
        required = {edge_key(item["edge"]) for item in self.ledger}
        if not required <= {edge_key(edge) for edge in reference["relations"]}:
            raise SourceContractError("Reviewed source graph silently omitted unchanged verified edges")
        expected = {"version": PRESERVED_REFERENCE_VERSION, "ledger": self.ledger,
                    "model_constraint_edges": self.constraint_edges, "candidate_access": False}
        if "verified_edge_preservation" in saved and saved["verified_edge_preservation"] != expected:
            raise SourceContractError("Verified unchanged-edge coverage ledger changed")
        if "verified_edge_preservation" not in saved:
            write_json(path, {**saved, "verified_edge_preservation": expected})
        return reference


class PreservedVerifiedReferenceBuilder(CachedVerifiedReferenceBuilder):
    def __init__(self, output: Path, *, actual_model: str, atomic_source: Path | None = None,
                 draft_source: Path | None = None, edge_source: Path | None = None,
                 legacy_draft: Path | None = None, legacy_verified: list[tuple[Path, Path]] | None = None) -> None:
        super().__init__(output, actual_model=actual_model, atomic_source=atomic_source,
                         draft_source=draft_source, edge_source=edge_source, legacy_draft=legacy_draft,
                         legacy_verified=legacy_verified)
        self.drafts = PreservedGraphReferenceBuilder(
            draft_source or output / "draft-source-graph", actual_model=actual_model,
            atomic_source=atomic_source, legacy_source=legacy_draft, table_output=output / "table-field-ledgers",
            source_parents=legacy_verified or [], edge_root=self.edges.output / "edges",
        )
        self.corrector = PreservedGraphPredictor(MappedSourceGraphReview, self.drafts)

    def build(self, inputs: dict[str, str]) -> dict:
        reference = super().build(inputs)
        required = {edge_key(item["edge"]) for item in self.drafts.ledger}
        if not required <= {edge_key(edge) for edge in reference["relations"]}:
            raise SourceContractError("Final verified graph silently omitted unchanged supported edges")
        return reference
