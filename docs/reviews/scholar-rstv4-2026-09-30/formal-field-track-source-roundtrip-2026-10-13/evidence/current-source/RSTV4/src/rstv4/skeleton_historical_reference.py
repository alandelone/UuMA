"""Replay unchanged verified history while applying current retention to the final graph."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from rstv4.skeleton_augmented_reference_v3 import (
    AugmentedVerifiedReferenceBuilder,
    parent_covers_additions,
)
from rstv4.skeleton_cached_reference import (
    CachedVerifiedReferenceBuilder,
    validate_cached_source_edge,
)
from rstv4.skeleton_complete_reference import COMPLETE_REFERENCE_VERSION, verified_source_additions
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_graph_reference import alias_claims, discourse_cues, edge_key, validate_graph
from rstv4.skeleton_mapped_graph_v2 import (
    MAPPED_GRAPH_VERSION,
    MAPPED_VERIFIED_VERSION,
    MappedGraphReferenceBuilder,
    read,
    restore_mapped_graph,
)
from rstv4.skeleton_preserved_reference import PRESERVED_REFERENCE_VERSION
from rstv4.skeleton_verified_reference import reference_edge_inputs

HISTORICAL_REFERENCE_VERSION = "unchanged-historical-round-replay-current-final-retention-v1"


def retention_ledger(inputs: dict, base: dict, parents: list[tuple[Path, Path]],
                     edge_root: Path) -> list[dict]:
    """Reconstruct unchanged supported edges without annotating or modifying a draft."""
    blocks = json.loads(inputs["source_blocks"])
    claims = {item["reference_id"]: item for item in base["claims"]}
    roles = {item["block_id"]: item for item in base["roles"]}
    selected = {}
    for root, _ in parents:
        for path in sorted((root / "references").glob("*.json")):
            parent = read(path)
            if parent["inputs_digest"] != digest(inputs):
                continue
            if parent["candidate_access"] is not False or not parent["source_graph_review_gate_passed"]:
                raise SourceContractError("Historical retention parent lacks source-only verification")
            old_base = {**copy.deepcopy(parent["reference"]), "relations": []}
            if validate_graph(old_base, blocks, discourse_cues(blocks), parent["graph_review"]) != parent["reference"]["relations"]:
                raise SourceContractError("Historical retention parent changed canonical source graph")
            meta = parent["rounds"][-1]
            final = read(root / "rounds" / path.stem / f"{meta['round']:03d}.json")
            if (digest(final) != meta["round_digest"] or final["reference"] != parent["reference"]
                    or not final["source_graph_review_gate_passed"]):
                raise SourceContractError("Historical retention parent final round changed")
            old_claims = {item["reference_id"]: item for item in old_base["claims"]}
            old_roles = {item["block_id"]: item for item in old_base["roles"]}
            full = {edge_key(edge): edge for connection in parent["graph_review"]["connections"]
                    for edge in connection["outgoing_relations"]}
            synthetic = reference_edge_inputs(parent["reference"], blocks)
            for index, edge in enumerate(parent["reference"]["relations"]):
                ids = [edge["source_reference_id"], edge["target_reference_id"]]
                if not all(key in claims and old_claims[key] == claims[key]
                           and old_roles[old_claims[key]["block_id"]] == roles[claims[key]["block_id"]]
                           for key in ids):
                    continue
                judgment = final["edge_reviews"][index]
                validate_cached_source_edge(inputs, synthetic, index, judgment, edge_root)
                if judgment["verdict"]["verdict"] != "SUPPORTED":
                    raise SourceContractError("Historical retention edge is not supported")
                selected.setdefault(edge_key(edge), {
                    "edge": full[edge_key(edge)], "parent_path": str(path), "parent_digest": digest(parent),
                    "judgment_digest": digest(judgment), "judgment_input_digest": judgment["input_digest"],
                    "source_claim_digest": digest(claims[ids[0]]),
                    "target_claim_digest": digest(claims[ids[1]]),
                })
    return list(selected.values())


class HistoricalDraftReplayer:
    """Retain original semantics and stages; the cached final validator rechecks all rounds."""

    def __init__(self, original: Any, parent_path: Path) -> None:
        self.original, self.parent_path = original, parent_path
        self.output, self.atomic = original.output, original.atomic

    def build(self, inputs: dict[str, str]) -> dict:
        parent = read(self.parent_path)
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [item for part in parts for item in part["claims"]],
                "roles": [item for part in parts for item in part["roles"]], "relations": []}
        _, mapping = alias_claims(base["claims"])
        cues = discourse_cues(blocks)
        if (parent["version"] != MAPPED_GRAPH_VERSION or parent["inputs_digest"] != digest(inputs)
                or parent["atomic_reference_digest"] != digest(base) or parent["identifier_map"] != mapping
                or parent["candidate_access"] is not False
                or {**copy.deepcopy(parent["reference"]), "relations": []} != base
                or restore_mapped_graph(parent["mapped_graph"], mapping, cues) != parent["graph_review"]
                or validate_graph(base, blocks, cues, parent["graph_review"]) != parent["reference"]["relations"]):
            raise SourceContractError("Historical draft changed complete source or canonical decisions")
        for name, stage in parent["stages"].items():
            validate_graph(base, blocks, cues, stage["graph"],
                           require_resolved=name != "INITIAL_SOURCE_GRAPH_ANNOTATION")
            if "mapped_graph" in stage and restore_mapped_graph(stage["mapped_graph"], mapping, cues) != stage["graph"]:
                raise SourceContractError("Historical source stage differs from its canonical graph")
        if len(base["claims"]) >= 2:
            first, second = (parent["stages"][name] for name in
                             ("INITIAL_SOURCE_GRAPH_ANNOTATION", "INDEPENDENT_SOURCE_GRAPH_REVIEW"))
            if first["input_digest"] == second["input_digest"] or second["graph"] != parent["graph_review"]:
                raise SourceContractError("Historical draft stages are not distinct source reviews")
        key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        saved = {**parent, "parent_path": str(self.parent_path), "parent_digest": digest(parent),
                 "origin": "EXACT_HISTORICAL_SOURCE_DRAFT_REPLAY", "new_semantic_inference_calls": 0}
        if path.exists() and read(path) != saved:
            raise SourceContractError("Historical child draft changed for identical replay")
        write_json(path, saved)
        return MappedGraphReferenceBuilder.build(self.original, inputs)


class HistoricalVerifiedReferenceBuilder(AugmentedVerifiedReferenceBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.replay_options = kwargs

    def build(self, inputs: dict[str, str]) -> dict:
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.drafts.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [item for part in parts for item in part["claims"]],
                "roles": [item for part in parts for item in part["roles"]], "relations": []}
        ledger = retention_ledger(inputs, base, self.legacy_verified, self.edges.output / "edges")
        additions = verified_source_additions(inputs, base, self.drafts.addition_reports)
        required = ledger + additions
        for parent_root, draft_root in self.legacy_verified:
            for path in sorted((parent_root / "references").glob("*.json")):
                parent = read(path)
                if not parent_covers_additions(parent, inputs, base, required):
                    continue
                drafts = [p for p in (draft_root / "references").glob("*.json")
                          if read(p)["inputs_digest"] == digest(inputs)]
                if len(drafts) != 1:
                    raise SourceContractError("Historical final parent requires exactly one original draft")
                original = read(drafts[0])
                if original["version"] != MAPPED_GRAPH_VERSION:
                    continue
                # Ordinary augmented reuse suffices if its original draft already covers the
                # current full ledger. This path is only for a changed historical correction.
                if parent_covers_additions(original, inputs, base, required):
                    continue
                cached = CachedVerifiedReferenceBuilder(
                    self.output, actual_model=self.replay_options["actual_model"],
                    atomic_source=self.replay_options.get("atomic_source"),
                    draft_source=self.replay_options.get("draft_source"),
                    edge_source=self.edges.output, legacy_verified=[(parent_root, draft_root)],
                )
                cached.drafts = HistoricalDraftReplayer(cached.drafts, drafts[0])
                result = cached.build(inputs)
                key = digest({"version": MAPPED_VERIFIED_VERSION, "inputs": inputs})
                saved_path = self.output / "references" / f"{key}.json"
                saved = read(saved_path)
                if not parent_covers_additions(saved, inputs, base, required):
                    raise SourceContractError("Historical final replay omitted a current full verified edge")
                _, mapping = alias_claims(base["claims"])
                aliases = {original: alias for alias, original in mapping.items()}
                constraints = copy.deepcopy([item["edge"] for item in ledger])
                for edge in constraints:
                    for name in ("source_reference_id", "target_reference_id"):
                        edge[name] = aliases[edge[name]]
                extra = {
                    "historical_replay": {"version": HISTORICAL_REFERENCE_VERSION,
                        "candidate_access": False, "historical_source_decisions_changed": False},
                    "current_verified_edge_preservation": {"version": PRESERVED_REFERENCE_VERSION,
                        "ledger": ledger, "model_constraint_edges": constraints, "candidate_access": False},
                    "current_verified_source_additions": {"protocol_version": COMPLETE_REFERENCE_VERSION,
                        "ledger": additions, "candidate_access": False},
                }
                if any(key in saved and saved[key] != value for key, value in extra.items()):
                    raise SourceContractError("Current historical-final retention ledger changed")
                write_json(saved_path, {**saved, **extra})
                return result
        return super().build(inputs)
