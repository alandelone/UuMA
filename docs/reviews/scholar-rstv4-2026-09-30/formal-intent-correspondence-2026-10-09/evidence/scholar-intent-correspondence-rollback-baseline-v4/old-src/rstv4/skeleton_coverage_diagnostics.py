"""Preserve actual unresolved source coverage context in bounded repair feedback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy

from rstv4.skeleton_complete_reference import CompleteVerifiedReferenceBuilder
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_mapped_graph_v2 import prediction_graph, read
from rstv4.skeleton_staged_reference import SourceEdgePlan

COVERAGE_DIAGNOSTIC_VERSION = "actual-unresolved-source-cue-feedback-v1"


class CoverageDiagnosticPredictor:
    """Report an unresolved model decision without changing its semantic content."""

    def __init__(self, inner: Any, output: Path, *, require_resolved: bool = True) -> None:
        self.inner, self.output, self.require_resolved = inner, output, require_resolved

    def __call__(self, **values: str) -> Any:
        result = self.inner(**values)
        graph = prediction_graph(result)
        unresolved = {key: item for key, item in graph["cue_resolutions"].items()
                      if item["classification"] == "AMBIGUOUS"}
        if not unresolved or not self.require_resolved:
            return result
        cues = {item["cue_id"]: item for item in json.loads(values["discourse_cues"])}
        record = {"version": COVERAGE_DIAGNOSTIC_VERSION, "inputs": values,
                  "inputs_digest": digest(values), "mapped_graph": graph,
                  "unresolved_cues": {key: {"source_cue": cues[key], "decision": item}
                                      for key, item in unresolved.items()},
                  "candidate_access": False, "model_decisions_changed": False,
                  "status": "UNRESOLVED_REJECTED"}
        path = self.output / "coverage-diagnostics" / f"{digest(values)}.json"
        if path.exists() and read(path) != record:
            raise SourceContractError("Unresolved source coverage changed for identical inputs")
        write_json(path, record)
        # The caller preserves up to 2,500 diagnostic characters. Put the source issue
        # first; the complete unabridged decision stays in the immutable record above.
        details = [{"cue_id": key, "source_cue": cues[key], "decision": item}
                   for key, item in unresolved.items()]
        raise SourceContractError(
            "Unresolved source coverage: " + json_text(details)
            + ". Re-read the stated antecedent/omission in the full source and ontology; "
            "supply a source-supported plan or preserve uncertainty. No forced resolution."
        )


class DiagnosticCompleteVerifiedReferenceBuilder(CompleteVerifiedReferenceBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        planner = SourceEdgePlan.with_instructions(
            SourceEdgePlan.instructions
            + "\nFor REMOVE explicitly include replacement: null; the nullable field is required. "
            "Review any actual unresolved coverage cue and its rationale in repair_feedback. "
            "A missing source relation may use additional_edges; do not force a structural label "
            "or invent a link to clear ambiguity."
        )
        self.corrector.planner = dspy.Predict(planner)
        self.corrector = CoverageDiagnosticPredictor(self.corrector, output)
        self.drafts.annotator = CoverageDiagnosticPredictor(
            self.drafts.annotator, self.drafts.output, require_resolved=False,
        )
        self.drafts.reviewer = CoverageDiagnosticPredictor(
            self.drafts.reviewer, self.drafts.output,
        )
