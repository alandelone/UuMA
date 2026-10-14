"""Explicit ordered citation context for independent source block annotation/review."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy
from dspy.utils.exceptions import AdapterParseError

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_source_reference import (
    SOURCE_REFERENCE_VERSION,
    SourceBlockAnnotation,
    SourceBlockReview,
    SourceReferenceBuilder,
    canonical_block_reference,
)

CONTEXT_REFERENCE_VERSION = "source-block-explicit-citation-context-v2"


def citation_context(block: dict) -> str:
    return json_text({
        "ordered_spans": [{"position": index, "span_id": span["span_id"],
                           "start": span["start"], "end": span["end"]}
                          for index, span in enumerate(block["source_spans"])],
        "rules": [
            "Use a nonempty consecutive span sublist per claim, without gaps, duplicates or reordering. Positions [0,2] are invalid; [0,1,2] is valid.",
            "Prefer the smallest consecutive range containing the actual assertion. Do not pair a table header with a nonadjacent row using gapped citations.",
            "Use headers and notes as context; locate row assertions to the actual row, preserve values, significance symbols, row identity and stated units. Do not reconstruct mixed columns or infer units.",
            "Preserve significance definitions as separately located source content. Split separately stated methods, findings and conclusions rather than merging their assertions.",
            "Retain substantive content, unique local IDs and exact source. Do not omit assertions to pass validation. A caption or roadmap describes content; classify it from that actual function.",
        ],
    })


class ContextSourceReferenceBuilder(SourceReferenceBuilder):
    def __init__(self, output: Path, *, actual_model: str) -> None:
        super().__init__(output, actual_model=actual_model)
        self.annotator = dspy.Predict(SourceBlockAnnotation.append("citation_contract", dspy.InputField()))
        self.reviewer = dspy.Predict(SourceBlockReview.append("citation_contract", dspy.InputField()))

    def block(self, context: str, block: dict[str, Any]) -> dict:
        key = digest({"version": SOURCE_REFERENCE_VERSION, "context": context, "block": block})
        path = self.output / "blocks" / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["input_digest"] != key:
                raise SourceContractError("Context source block identity changed")
            checked = canonical_block_reference(block, saved["reference"]["claims"], saved["reference"]["roles"][0])
            if checked != saved["reference"]:
                raise SourceContractError("Context source block changed canonical claims/quotes")
            if "citation_contract_digest" in saved and saved["citation_contract_digest"] != digest(citation_context(block)):
                raise SourceContractError("Source citation context changed")
            return saved["reference"]
        values = {"document_context": context, "source_block": json_text(block),
                  "citation_contract": citation_context(block)}
        stages = {}

        def call(stage: str, predictor: dspy.Predict, inputs: dict) -> tuple[dict, list]:
            feedback, failures = "", []
            for attempt in range(3):
                try:
                    with dspy.context(lm=self.lm, adapter=dspy.JSONAdapter()):
                        result = predictor(**inputs, repair_feedback=feedback)
                    reference = canonical_block_reference(block, [item.model_dump() for item in result.claims],
                                                          result.role.model_dump())
                    stages[stage] = {"inputs_digest": digest(inputs), "reference": reference,
                                     "failed_attempts": failures}
                    return reference, list(getattr(result, "corrections", []))
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as exc:
                    failures.append(str(exc)[:2500])
                    write_json(self.output / "failures" / f"{key}-{stage}.json", {"failures": failures})
                    feedback = "Regenerate complete source assertions and role using citation_contract. " + str(exc)[:2500]
            raise SourceContractError("Context source reference exhausted: " + failures[-1])

        draft, _ = call("ANNOTATION", self.annotator, values)
        reference, corrections = call("INDEPENDENT_REVIEW", self.reviewer,
                                      {**values, "draft_reference": json_text(draft)})
        if stages["ANNOTATION"]["inputs_digest"] == stages["INDEPENDENT_REVIEW"]["inputs_digest"]:
            raise SourceContractError("Source annotation and independent review must use distinct inputs")
        write_json(path, {"input_digest": key, "draft": draft, "reference": reference,
                          "corrections": corrections, "protocol_version": CONTEXT_REFERENCE_VERSION,
                          "citation_contract_digest": digest(values["citation_contract"]), "stages": stages,
                          "candidate_access": False, "status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD"})
        return reference
