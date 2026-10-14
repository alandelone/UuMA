"""Unique-key source review; retain canonical judgments and legacy failure evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, get_args

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import BaseModel, ConfigDict

from rstv4.skeleton_block_review import (
    BLOCK_REVIEW_VERSION,
    LocalSourceReviewer,
    SourceBlockAssessment,
    alias_block_records,
    restore_block_review,
    unassessed_block_review,
    validate_block_review,
)
from rstv4.skeleton_contract import BlockRole, SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_grounded_review import ReferenceDefect

MAPPED_REVIEW_VERSION = "block-local-unique-key-source-review-v2"


class MatchValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atom_id: str | None
    meaning_preserved: bool
    qualifications_preserved: bool
    rationale: str


class VerdictValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "UNCERTAIN"]
    evidence_span_ids: list[str]
    rationale: str


class MappedSourceAssessment(dspy.Signature):
    document_context: str = dspy.InputField()
    source_block: str = dspy.InputField()
    adjacent_source_blocks: str = dspy.InputField()
    reference_claims: str = dspy.InputField()
    reference_role: str = dspy.InputField()
    candidate_atoms: str = dspy.InputField()
    repair_feedback: str = dspy.InputField()
    claim_matches: dict[str, MatchValue] = dspy.OutputField()
    candidate_verdicts: dict[str, VerdictValue] = dspy.OutputField()
    reference_defects: list[ReferenceDefect] = dspy.OutputField()
    feedback: str = dspy.OutputField()


MappedSourceAssessment = MappedSourceAssessment.with_instructions(
    SourceBlockAssessment.instructions + "\n\n"
    "Output claim_matches as a JSON OBJECT keyed by each supplied r-ID exactly once. "
    "Its value contains only atom_id, meaning_preserved, qualifications_preserved and rationale. "
    "Choose one actual atom or null for that complete reference assertion; never emit additional "
    "negative matches for other candidate atoms. Do not merge multiple partial atoms into an "
    "invented combined atom or mark a partial assertion complete. "
    "Output candidate_verdicts as a separate JSON OBJECT keyed by each supplied c-ID exactly once, "
    "with verdict, evidence_span_ids and rationale. The two objects have separate domains. "
    "No duplicate JSON keys, no undeclared fields, and no invented aliases. "
    "A source role of UNKNOWN is permitted when the actual function is unresolved or cannot be "
    "represented by the available role taxonomy. A role defect must explain a source-supported "
    "alternative allowed by that taxonomy; the absence of an administrative label is not itself "
    "proof that UNKNOWN is wrong. Preserve all genuine source/reference defects. "
    "Allowed macro roles: " + json_text(list(get_args(BlockRole.model_fields["role"].annotation)))
)


def strict_json_object(completion: str) -> dict:
    payload = completion.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if len(lines) < 3 or lines[-1].strip() != "```":
            raise SourceContractError("Mapped review requires one complete JSON object")
        payload = "\n".join(lines[1:-1]).strip()

    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise SourceContractError("Duplicate JSON review key: " + key)
            result[key] = value
        return result

    value = json.loads(payload, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise SourceContractError("Mapped review must return an object")
    return value


class UniqueKeyJSONAdapter(dspy.JSONAdapter):
    def parse(self, signature: type, completion: str) -> dict:
        value = strict_json_object(completion)
        if value.keys() != signature.output_fields.keys():
            raise SourceContractError("Mapped review has missing or undeclared top-level fields")
        return super().parse(signature, completion)


def restore_mapped_review(value: dict, maps: dict[str, dict[str, str]]) -> dict:
    if (set(value["claim_matches"]) != maps["references"].keys()
            or set(value["candidate_verdicts"]) != maps["atoms"].keys()):
        raise SourceContractError("Mapped review must include all and only each supplied reference/atom key")
    canonical = {
        "matches": [{"reference_id": key, **MatchValue.model_validate(value["claim_matches"][key]).model_dump()}
                    for key in maps["references"]],
        "atom_verdicts": [{"atom_id": key, **VerdictValue.model_validate(value["candidate_verdicts"][key]).model_dump()}
                          for key in maps["atoms"]],
        "reference_defects": value["reference_defects"], "feedback": value["feedback"],
    }
    return restore_block_review(canonical, maps)


class MappedBlockSourceReviewer:
    def __init__(self, output: Path, *, actual_model: str, legacy_root: Path | None = None) -> None:
        self.output, self.legacy_root = output, legacy_root
        self.lm = ReceiptLM("thinking", output / "teacher-lm", max_tokens=16000,
                            required_actual_model=actual_model)
        self.predictor = dspy.Predict(MappedSourceAssessment)

    def assess(self, context: str, block: dict, adjacent: list[dict],
               claims: list[dict], role: dict, atoms: list[dict]) -> dict:
        changed_claims, changed_atoms, maps = alias_block_records(claims, atoms)
        values = {"document_context": context, "source_block": json_text(block),
                  "adjacent_source_blocks": json_text(adjacent), "reference_claims": json_text(changed_claims),
                  "reference_role": json_text(role), "candidate_atoms": json_text(changed_atoms)}
        key = digest({"version": MAPPED_REVIEW_VERSION, "inputs": values, "maps": maps})
        path = self.output / "blocks" / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved["input_digest"] != key or saved["identifier_maps"] != maps
                    or saved["protocol_version"] != MAPPED_REVIEW_VERSION):
                raise SourceContractError("Mapped block assessment lineage changed")
            validate_block_review(block, claims, atoms, saved["review"])
            if saved["origin"] == "UNIQUE_KEY_SOURCE_REVIEW":
                if restore_mapped_review(saved["mapped_output"], maps) != saved["review"]:
                    raise SourceContractError("Mapped output differs from its canonical source judgments")
            elif saved["origin"] == "EXACT_VALID_LEGACY_JUDGMENT":
                parent = json.loads(Path(saved["parent_path"]).read_text(encoding="utf-8"))
                if (digest(parent) != saved["parent_digest"] or parent["status"] != "ASSESSED"
                        or parent["review"]["reference_defects"] or parent["review"] != saved["review"]):
                    raise SourceContractError("Adopted source judgment parent changed")
            elif saved["origin"] != "UNIQUE_KEY_SOURCE_REVIEW_FAILED":
                raise SourceContractError("Mapped source judgment has an unknown origin")
            return saved
        if self.legacy_root is not None:
            old_key = digest({"version": BLOCK_REVIEW_VERSION, "inputs": values, "maps": maps})
            old_path = self.legacy_root / f"{old_key}.json"
            if old_path.exists():
                parent = json.loads(old_path.read_text(encoding="utf-8"))
                if parent["input_digest"] != old_key or parent["identifier_maps"] != maps:
                    raise SourceContractError("Legacy block judgment identity changed")
                validate_block_review(block, claims, atoms, parent["review"])
                if parent["status"] == "ASSESSED" and not parent["review"]["reference_defects"]:
                    saved = {**parent, "input_digest": key, "protocol_version": MAPPED_REVIEW_VERSION,
                             "origin": "EXACT_VALID_LEGACY_JUDGMENT", "parent_path": str(old_path),
                             "parent_digest": digest(parent), "parent_input_digest": old_key}
                    write_json(path, saved)
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
                 "failed_attempts": failures, "origin": "UNIQUE_KEY_SOURCE_REVIEW_FAILED"}
        write_json(path, saved)
        return saved


class MappedLocalSourceReviewer(LocalSourceReviewer):
    def __init__(self, output: Path, *, actual_model: str, legacy_root: Path | None = None) -> None:
        super().__init__(output, actual_model=actual_model)
        self.blocks = MappedBlockSourceReviewer(output / "block-review", actual_model=actual_model,
                                                legacy_root=legacy_root)
