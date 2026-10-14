from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_coverage_diagnostics import CoverageDiagnosticPredictor
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_graph_reference import SourceGraphEdge
from rstv4.skeleton_mapped_graph_v2 import ConnectionValue, CueValue
from rstv4.skeleton_transactional_reference import apply_source_graph_patch
from test_skeleton_transactional_reference import repair_case


def ambiguous_result():
    original, judgments, patch = repair_case()
    graph = apply_source_graph_patch(original, judgments, patch)
    cue = next(iter(graph["cue_resolutions"]))
    graph["cue_resolutions"][cue] = {
        "classification": "AMBIGUOUS", "relation_ids": [],
        "rationale": "The plan omits the antecedent load assessment; cost does not imply capacity.",
    }
    result = SimpleNamespace(
        edges={key: SourceGraphEdge.model_validate(value) for key, value in graph["edges"].items()},
        corrections=[],
        connections={key: ConnectionValue.model_validate(value)
                     for key, value in graph["connections"].items()},
        cue_resolutions={key: CueValue.model_validate(value)
                         for key, value in graph["cue_resolutions"].items()},
    )
    values = {"discourse_cues": json_text([
        {"cue_id": cue, "source_span_id": "r2:s1", "text": "Hence, the design meets demand."}
    ]), "review_stage": "SOURCE_CORRECTION", "repair_feedback": ""}
    return result, values, cue


def test_unresolved_coverage_feedback_preserves_actual_source_issue_and_rejection(tmp_path):
    result, values, cue = ambiguous_result()
    before = copy.deepcopy(result.cue_resolutions[cue].model_dump())
    predictor = CoverageDiagnosticPredictor(lambda **_: result, tmp_path)
    with pytest.raises(SourceContractError) as caught:
        predictor(**values)
    feedback = str(caught.value)[:2500]
    assert cue in feedback and "antecedent load assessment" in feedback
    assert "cost does not imply capacity" in feedback and "Hence" in feedback
    saved = json.loads(next((tmp_path / "coverage-diagnostics").glob("*.json")).read_text())
    assert saved["status"] == "UNRESOLVED_REJECTED"
    assert saved["unresolved_cues"][cue]["decision"] == before
    assert result.cue_resolutions[cue].model_dump() == before
    # The same request cannot silently replace a prior unresolved decision.
    result.cue_resolutions[cue].rationale = "A different unresolved source interpretation."
    with pytest.raises(SourceContractError, match="changed for identical"):
        predictor(**values)


def test_initial_draft_uncertainty_is_preserved_for_independent_review(tmp_path):
    result, values, _ = ambiguous_result()
    predictor = CoverageDiagnosticPredictor(lambda **_: result, tmp_path, require_resolved=False)
    assert predictor(**values) is result
    assert not (tmp_path / "coverage-diagnostics").exists()
