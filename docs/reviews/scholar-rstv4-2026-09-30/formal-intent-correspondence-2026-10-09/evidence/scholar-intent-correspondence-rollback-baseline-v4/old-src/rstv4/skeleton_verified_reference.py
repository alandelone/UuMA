"""Coverage-reviewed source graphs corrected against isolated actual endpoint judgments."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import dspy
from dspy.utils.exceptions import AdapterParseError

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_endpoint_review import RELATION_ONTOLOGY, EndpointEdgeReviewer
from rstv4.skeleton_graph_reference import (
    GRAPH_REFERENCE_VERSION,
    GraphReferenceBuilder,
    SourceGraphReview,
    alias_claims,
    discourse_cues,
    restore_graph,
    validate_graph,
)

VERIFIED_REFERENCE_VERSION = "source-graph-coverage-and-isolated-edge-reference-v3"


def reference_edge_inputs(reference: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Map source references into the edge API without introducing learner predictions."""
    return {
        "block_atoms": [{"block_id": block["block_id"], "atoms": [
            {"atom_id": claim["reference_id"], **{name: value for name, value in claim.items()
             if name != "reference_id"}} for claim in reference["claims"]
            if claim["block_id"] == block["block_id"]]}
            for block in blocks],
        "relations": [{"source_id": edge["source_reference_id"],
                       "target_id": edge["target_reference_id"],
                       "relation": edge["relation"], "rationale": edge["rationale"]}
                      for edge in reference["relations"]],
    }


def edge_correction_feedback(
    reference: dict[str, Any], results: list[dict[str, Any]], aliases: dict[str, str],
) -> list[dict[str, Any]]:
    claims = {claim["reference_id"]: claim for claim in reference["claims"]}
    feedback = []
    for index, result in enumerate(results):
        if result["status"] == "ASSESSED" and result["verdict"]["verdict"] == "SUPPORTED":
            continue
        edge = reference["relations"][index]
        feedback.append({
            "source_reference_id": aliases[edge["source_reference_id"]],
            "target_reference_id": aliases[edge["target_reference_id"]],
            "relation": edge["relation"],
            "source_statement": claims[edge["source_reference_id"]]["statement"],
            "target_statement": claims[edge["target_reference_id"]]["statement"],
            "source_review": result["verdict"] if result["status"] == "ASSESSED" else result,
        })
    return feedback


class VerifiedReferenceBuilder:
    def __init__(
        self, output: Path, *, actual_model: str, atomic_source: Path | None = None,
        draft_source: Path | None = None, edge_source: Path | None = None,
    ) -> None:
        self.output = output
        self.drafts = GraphReferenceBuilder(draft_source or output / "draft-source-graph",
                                           actual_model=actual_model, atomic_source=atomic_source)
        self.edges = EndpointEdgeReviewer(edge_source or output / "source-edge-review",
                                          actual_model=actual_model)
        self.lm = ReceiptLM("thinking", output / "correction-teacher-lm", max_tokens=24000,
                            required_actual_model=actual_model)
        self.corrector = dspy.Predict(SourceGraphReview)

    def build(self, inputs: dict[str, str]) -> dict[str, Any]:
        key = digest({"version": VERIFIED_REFERENCE_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        blocks = json.loads(inputs["source_blocks"])
        original = self.drafts.build(inputs)
        draft_key = digest({"version": GRAPH_REFERENCE_VERSION, "inputs": inputs})
        draft_record = json.loads((self.drafts.output / "references" / f"{draft_key}.json").read_text(encoding="utf-8"))
        base = {**copy.deepcopy(original), "relations": []}
        claims, mapping = alias_claims(base["claims"])
        aliases = {value: alias for alias, value in mapping.items()}
        cues = discourse_cues(blocks)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved["inputs_digest"] != digest(inputs)
                    or saved["draft_reference_digest"] != digest(original)
                    or saved["atomic_reference_digest"] != digest(base)):
                raise SourceContractError("Isolated-edge verified source lineage changed")
            edges = validate_graph(base, blocks, cues, saved["graph_review"])
            if saved["reference"] != {**base, "relations": edges}:
                raise SourceContractError("Verified reference differs from the reviewed source graph")
            if not saved["source_graph_review_gate_passed"]:
                raise SourceContractError("Source graph still needs review")
            return saved["reference"]
        graph = copy.deepcopy(draft_record["graph_review"])
        reference = copy.deepcopy(original)
        rounds = []
        for round_index in range(4):
            synthetic = reference_edge_inputs(reference, blocks)
            results = [self.edges.assess(inputs, synthetic, index)
                       for index in range(len(reference["relations"]))]
            passed = all(result["status"] == "ASSESSED" and result["verdict"]["verdict"] == "SUPPORTED"
                         for result in results)
            round_record = {
                "round": round_index, "reference": reference, "graph_review": graph,
                "edge_reviews": results, "source_graph_review_gate_passed": passed,
            }
            write_json(self.output / "rounds" / key / f"{round_index:03d}.json", round_record)
            rounds.append({"round": round_index, "round_digest": digest(round_record),
                           "edges": len(results), "source_graph_review_gate_passed": passed})
            if passed:
                write_json(path, {
                    "version": VERIFIED_REFERENCE_VERSION, "inputs_digest": digest(inputs),
                    "reference": reference, "graph_review": graph, "identifier_map": mapping,
                    "draft_reference_digest": digest(original), "atomic_reference_digest": digest(base),
                    "draft_record_digest": digest(draft_record), "rounds": rounds,
                    "source_graph_review_gate_passed": True, "candidate_access": False,
                    "status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD",
                })
                return reference
            if any(result["status"] != "ASSESSED" for result in results):
                raise SourceContractError("Source-edge evaluator failed; preserve judgments and repair evaluator")
            if round_index == 3:
                raise SourceContractError("Source graph still has unsupported/uncertain edges after three full corrections")
            values = {
                **inputs, "review_stage": "SOURCE_GRAPH_CORRECTION_AFTER_ISOLATED_ENDPOINT_REVIEW",
                "reference_claims": json_text(claims), "discourse_cues": json_text(cues),
                "relation_ontology": RELATION_ONTOLOGY, "draft_graph": json_text(restore_graph(graph, aliases)),
            }
            feedback = (
                "Correct the COMPLETE source graph against the following isolated source-edge judgments. "
                "These are source-reference propositions, not learner predictions. Recheck the actual type "
                "and direction, preserve all sound links and review omissions/cues. Do not silently discard "
                "claims or force unsupported links. Keep all claims, qualifiers and IDs unchanged. "
                + json_text(edge_correction_feedback(reference, results, aliases))
            )
            failures = []
            for attempt in range(3):
                try:
                    with dspy.context(lm=self.lm, adapter=dspy.JSONAdapter()):
                        result = self.corrector(**values, repair_feedback=feedback)
                    proposed = restore_graph({
                        "connections": [item.model_dump() for item in result.connections],
                        "cue_resolutions": [item.model_dump() for item in result.cue_resolutions],
                        "corrections": result.corrections,
                    }, mapping)
                    relations = validate_graph(base, blocks, cues, proposed)
                    write_json(self.output / "corrections" / key / f"{round_index + 1:03d}.json", {
                        "inputs_digest": digest({**values, "repair_feedback": feedback}),
                        "graph_review": proposed, "failed_attempts": failures,
                    })
                    graph, reference = proposed, {**base, "relations": relations}
                    break
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as exc:
                    failures.append(str(exc)[:2500])
                    write_json(self.output / "failures" / f"{key}-round-{round_index + 1}.json", {
                        "failures": failures, "source_inputs_digest": digest(inputs),
                    })
                    feedback += "\nRegenerate all claim connections and cue decisions. Diagnostic: " + str(exc)[:2500]
            else:
                raise SourceContractError("Full source graph correction failed: " + failures[-1])
        raise AssertionError("Source verification exhausted without an explicit terminal outcome")
