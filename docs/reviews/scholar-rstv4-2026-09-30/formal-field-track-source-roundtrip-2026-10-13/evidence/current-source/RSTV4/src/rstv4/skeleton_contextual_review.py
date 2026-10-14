"""Source-local grading with shared macro-role contract and full-window context."""
from __future__ import annotations

import json
from pathlib import Path

import dspy
from dspy.utils.exceptions import AdapterParseError

from rstv4.skeleton_block_review import (
    LocalSourceReviewer,
    alias_block_records,
    unassessed_block_review,
    validate_block_review,
)
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import PaperSkeletonProgram, ReceiptLM, json_text, write_json
from rstv4.skeleton_mapped_review import (
    MAPPED_REVIEW_VERSION,
    MappedSourceAssessment,
    UniqueKeyJSONAdapter,
    restore_mapped_review,
)

CONTEXTUAL_REVIEW_VERSION = "source-local-review-shared-role-contract-full-window-v1"
ROLE_REVIEW_RULES = """
Apply extraction_role_contract as the actual definition of the paper's macro roles.
Inspect source_context_blocks for the paper's local scientific setup, continuation across
intervening figures/tables, and section function. Determine the target role from this
specific whole-paper context. Core_Methodology encompasses the functions allowed by that
contract, including definitions in Methods; it does not require an algorithmic formulation.
The local Figure_Intro intent or a caption's text type alone does not decide the macro role.
Keep genuine source-reference defects explicit with source-specific evidence and preserve
uncertainty. The full window supplies context only: claims and matches remain anchored to
the actual target block's spans and aliases. Do not borrow scientific support from an
unrelated block, invent a completion, or change source/reference/candidate data.
"""
ContextualSourceAssessment = MappedSourceAssessment.with_instructions(
    MappedSourceAssessment.instructions + ROLE_REVIEW_RULES,
).append("source_context_blocks", dspy.InputField()).append("extraction_role_contract", dspy.InputField())


def shared_role_contract() -> str:
    return PaperSkeletonProgram().layer4.signature.instructions


class ContextualMappedBlockSourceReviewer:
    def __init__(self, output: Path, *, actual_model: str, legacy_root: Path | None = None) -> None:
        # A prior role criterion cannot be adopted as a judgment under this contract.
        self.output = output
        self.source_window = None
        self.lm = ReceiptLM("thinking", output / "teacher-lm", max_tokens=16000,
                            required_actual_model=actual_model)
        self.predictor = dspy.Predict(ContextualSourceAssessment)

    def bind_window(self, inputs: dict) -> None:
        self.source_window = dict(inputs)

    def assess(self, context: str, block: dict, adjacent: list[dict],
               claims: list[dict], role: dict, atoms: list[dict]) -> dict:
        if self.source_window is None or self.source_window["document_context"] != context:
            raise SourceContractError("Contextual grading requires the exact full source window")
        window = json.loads(self.source_window["source_blocks"])
        if sum(item == block for item in window) != 1:
            raise SourceContractError("Contextual grading target must occur exactly once in raw window")
        changed_claims, changed_atoms, maps = alias_block_records(claims, atoms)
        values = {"document_context": context, "source_block": json_text(block),
                  "adjacent_source_blocks": json_text(adjacent), "reference_claims": json_text(changed_claims),
                  "reference_role": json_text(role), "candidate_atoms": json_text(changed_atoms),
                  "source_context_blocks": self.source_window["source_blocks"],
                  "extraction_role_contract": shared_role_contract()}
        key = digest({"version": MAPPED_REVIEW_VERSION, "inputs": values, "maps": maps})
        path = self.output / "blocks" / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved["input_digest"] != key or saved["identifier_maps"] != maps
                    or saved["protocol_version"] != MAPPED_REVIEW_VERSION
                    or saved.get("context_protocol_version") != CONTEXTUAL_REVIEW_VERSION):
                raise SourceContractError("Mapped block assessment lineage changed")
            if saved["status"] == "ASSESSED":
                actual = saved["actual_inputs"]
                if {key: actual[key] for key in values} != values:
                    raise SourceContractError("Actual contextual grading inputs changed")
            validate_block_review(block, claims, atoms, saved["review"])
            if saved["origin"] == "UNIQUE_KEY_SOURCE_REVIEW":
                if restore_mapped_review(saved["mapped_output"], maps) != saved["review"]:
                    raise SourceContractError("Mapped output differs from its canonical source judgments")
            elif saved["origin"] != "UNIQUE_KEY_SOURCE_REVIEW_FAILED":
                raise SourceContractError("Mapped source judgment has an unknown origin")
            return saved
        feedback, failures = "", []
        for attempt in range(3):
            try:
                if not claims and not atoms:
                    mapped = {"claim_matches": {}, "candidate_verdicts": {}, "reference_defects": [],
                              "feedback": "No reference scientific claim or candidate atom in this block."}
                else:
                    with dspy.context(lm=self.lm, adapter=UniqueKeyJSONAdapter()):
                        result = self.predictor(**values, repair_feedback=feedback)
                    mapped = {"claim_matches": {key: item.model_dump() for key, item in result.claim_matches.items()},
                              "candidate_verdicts": {key: item.model_dump() for key, item in result.candidate_verdicts.items()},
                              "reference_defects": [item.model_dump() for item in result.reference_defects],
                              "feedback": result.feedback}
                review = restore_mapped_review(mapped, maps)
                validate_block_review(block, claims, atoms, review)
                saved = {"input_digest": key, "identifier_maps": maps, "review": review,
                         "mapped_output": mapped, "protocol_version": MAPPED_REVIEW_VERSION,
                         "context_protocol_version": CONTEXTUAL_REVIEW_VERSION,
                         "actual_inputs": {**values, "repair_feedback": feedback},
                         "status": "ASSESSED", "failed_attempts": failures, "origin": "UNIQUE_KEY_SOURCE_REVIEW"}
                write_json(path, saved)
                return saved
            except (AdapterParseError, SourceContractError, ValueError, TypeError) as exc:
                failures.append(str(exc)[:2500])
                feedback = ("Regenerate both COMPLETE JSON OBJECTS. Exact claim_matches keys: "
                            + json_text(list(maps["references"])) + "; exact candidate_verdicts keys: "
                            + json_text(list(maps["atoms"])) + ". No duplicate or extra keys. "
                            "One match per reference; use null for a missing complete assertion. "
                            "Retain all source verdicts and actual evidence. Diagnostic: " + str(exc)[:2500])
        review = unassessed_block_review(claims, atoms, failures[-1])
        validate_block_review(block, claims, atoms, review)
        saved = {"input_digest": key, "identifier_maps": maps, "review": review,
                 "protocol_version": MAPPED_REVIEW_VERSION, "status": "EVALUATION_CONTRACT_FAILURE",
                 "context_protocol_version": CONTEXTUAL_REVIEW_VERSION,
                 "failed_attempts": failures, "origin": "UNIQUE_KEY_SOURCE_REVIEW_FAILED"}
        write_json(path, saved)
        return saved


class ContextualLocalSourceReviewer(LocalSourceReviewer):
    def __init__(self, output: Path, *, actual_model: str, legacy_root: Path | None = None) -> None:
        super().__init__(output, actual_model=actual_model)
        self.blocks = ContextualMappedBlockSourceReviewer(output / "block-review", actual_model=actual_model)

    def assess(self, inputs: dict, reference: dict, candidate: dict) -> dict:
        self.blocks.bind_window(inputs)
        return super().assess(inputs, reference, candidate)
