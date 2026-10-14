"""Bound independent output-protocol repair without returning old graph hypotheses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy
from dspy.utils.exceptions import AdapterParseError

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_mapped_graph_v2 import CueValue, read
from rstv4.skeleton_partition_reference_v2 import (
    IndependentCueCoverage,
    IndependentEmptyClaimCoverage,
)

SEPARATED_COVERAGE_VERSION = "independent-source-coverage-with-bounded-protocol-feedback-v3"
PROTOCOL_INSTRUCTIONS = """
protocol_repair_feedback contains only exact field/domain violations of your own prior
independent output, never an old graph draft, plan, source interpretation or desired label.
Re-read the actual raw source, complete claims and resulting-edge domain and return a new
complete independent decision. SUPPORTED_RELATION requires a nonempty list of actual
eligible edge IDs. All other classifications have an empty relation_ids list. Do not
claim an edge with no ID or invent an eligible ID. A contrast/causal comparison retained
inside a single claim is decided from its actual two propositions and partition, not
from the presence of a trigger word. Every named edge requires its actual rationale.
Preserve genuine uncertainty; protocol repair must not force scientific acceptance.
Return all and only the requested domains. Code never edits your scientific decisions.
"""
ProtocolCueCoverage = IndependentCueCoverage.with_instructions(
    IndependentCueCoverage.instructions + PROTOCOL_INSTRUCTIONS,
).append("protocol_repair_feedback", dspy.InputField())
ProtocolEmptyClaimCoverage = IndependentEmptyClaimCoverage.with_instructions(
    IndependentEmptyClaimCoverage.instructions + PROTOCOL_INSTRUCTIONS,
).append("protocol_repair_feedback", dspy.InputField())


def cue_protocol_errors(inputs: dict, decisions: dict) -> list[str]:
    required = {item["cue_id"] for item in json.loads(inputs["discourse_cues"])}
    eligible = json.loads(inputs["eligible_cue_edges"])
    if decisions.keys() != required:
        return ["Exact cue key domain required: " + json.dumps({"missing": sorted(required - decisions.keys()),
                                                                "extra": sorted(decisions.keys() - required)})]
    errors = []
    for key, value in decisions.items():
        ids = value["relation_ids"]
        reasons = value["relation_rationales"]
        if (len(ids) != len(set(ids)) or not set(ids).issubset(eligible[key])
                or (value["classification"] == "SUPPORTED_RELATION") != bool(ids)
                or set(reasons) != set(ids) or not value["rationale"].strip()
                or any(not text.strip() for text in reasons.values())):
            errors.append("Independent cue output field/domain violation: " + json.dumps({
                "cue_id": key, "classification": value["classification"], "relation_ids": ids,
                "eligible_relation_ids": eligible[key], "rationale_keys": list(reasons),
                "rule": "SUPPORTED_RELATION iff nonempty actual eligible IDs; otherwise zero IDs. Unique IDs, exact rationale keys and nonempty explanations required. Re-read source/claims; no desired label is prescribed.",
            }, sort_keys=True))
    return errors


def empty_protocol_errors(inputs: dict, rationales: dict) -> list[str]:
    required = set(json.loads(inputs["required_empty_claim_ids"]))
    if rationales.keys() != required or any(not value.strip() for value in rationales.values()):
        return ["Independent empty-claim output needs exact nonempty rationale domain: " + json.dumps({
            "required_ids": sorted(required), "returned_ids": sorted(rationales),
        }, sort_keys=True)]
    return []


class ProtocolIndependentCoveragePredictor:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.cues = dspy.Predict(ProtocolCueCoverage)
        self.empty = dspy.Predict(ProtocolEmptyClaimCoverage)

    def _bounded(self, name: str, predictor: Any, values: dict,
                 output_name: str, validate: Any) -> tuple[dict, list[dict]]:
        attempts, feedback = [], ""
        for number in range(3):
            inputs = {**values, "protocol_repair_feedback": feedback}
            try:
                result = predictor(**inputs)
                output = getattr(result, output_name)
                if output_name == "cue_resolutions":
                    output = {key: value.model_dump() for key, value in output.items()}
                errors = validate(values, output)
                attempts.append({"inputs": inputs, "inputs_digest": digest(inputs),
                                 "output": output, "protocol_errors": errors})
            except (AdapterParseError, ValueError, TypeError) as exc:
                errors = ["Independent output parser/schema violation: " + str(exc)[:2500]]
                attempts.append({"inputs": inputs, "inputs_digest": digest(inputs),
                                 "parser_failure": errors[0], "protocol_errors": errors})
            # Feedback contains only this independent stage's current protocol violation.
            # A scientific interpretation is never substituted, selected or rewritten here.
            if not errors:
                return output, attempts
            write_json(self.output / "independent-coverage-failures" /
                       f"{digest(values)}-{name}-{number + 1}.json", attempts[-1])
            feedback = "\n".join(errors)
        raise SourceContractError("Independent " + name + " exhausted bounded protocol repair: " + feedback)

    def __call__(self, **values: str) -> Any:
        cues = {key: values[key] for key in (
            "document_context", "source_blocks", "reference_claims", "discourse_cues",
            "relation_ontology", "resulting_edges", "eligible_cue_edges",
        )}
        empty = {key: values[key] for key in (
            "document_context", "source_blocks", "reference_claims", "relation_ontology",
            "resulting_edges", "required_empty_claim_ids",
        )}
        decisions, cue_attempts = self._bounded("cues", self.cues, cues,
                                              "cue_resolutions", cue_protocol_errors)
        reasons, empty_attempts = self._bounded("empty-claims", self.empty, empty,
                                               "empty_claim_rationales", empty_protocol_errors)
        record = {"version": SEPARATED_COVERAGE_VERSION, "coverage_inputs": values,
                  "coverage_inputs_digest": digest(values), "cue_source_inputs": cues,
                  "empty_source_inputs": empty, "cue_attempts": cue_attempts,
                  "empty_attempts": empty_attempts, "cue_resolutions": decisions,
                  "empty_claim_rationales": reasons,
                  "cue_signature_digest": digest(ProtocolCueCoverage.instructions),
                  "empty_signature_digest": digest(ProtocolEmptyClaimCoverage.instructions),
                  "candidate_access": False, "prior_hypotheses_supplied": False,
                  "protocol_feedback_only": True}
        path = self.output / "independent-coverage-stages" / f"{digest(values)}.json"
        if path.exists() and read(path) != record:
            raise SourceContractError("Bounded independent coverage changed for identical actual inputs")
        write_json(path, record)
        return dspy.Prediction(cue_resolutions={key: CueValue.model_validate(value)
                                              for key, value in decisions.items()},
                               empty_claim_rationales=reasons)
