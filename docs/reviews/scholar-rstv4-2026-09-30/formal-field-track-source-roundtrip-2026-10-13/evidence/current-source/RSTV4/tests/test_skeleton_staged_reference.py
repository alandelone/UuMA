from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_mapped_graph_v2 import CueValue
from rstv4.skeleton_staged_reference import StagedGraphPredictor, coverage_domain
from rstv4.skeleton_transactional_reference import EdgeRepair
from test_skeleton_transactional_reference import repair_case


def test_coverage_domain_comes_from_actual_declared_operations_and_cue_evidence():
    graph, judgments, patch = repair_case()
    patch["repairs"]["e1"].update(action="REMOVE", replacement=None)
    cues = [{"cue_id": "r2:s1:discourse", "source_span_id": "r2:s1"}]
    before = copy.deepcopy((graph, judgments, patch, cues))
    domain = coverage_domain(graph, judgments, patch, cues)
    assert domain["required_empty_claim_ids"] == ["r1", "r2"]
    assert domain["eligible_cue_edges"] == {"r2:s1:discourse": []}
    assert domain["resulting_edges"] == {"e0": graph["edges"]["e0"]}
    assert (graph, judgments, patch, cues) == before


def staged_case(tmp_path, bad_cue=False):
    graph, judgments, patch = repair_case()
    if bad_cue:
        patch["cue_resolutions"]["r2:s1:discourse"]["relation_ids"] = []
    predictor = StagedGraphPredictor(tmp_path)
    plan_calls, review_calls = [], []

    def plan(**values):
        plan_calls.append(values)
        return SimpleNamespace(repairs={key: EdgeRepair.model_validate(item)
                                        for key, item in patch["repairs"].items()},
                               additional_edges={}, corrections=patch["corrections"])

    def review(**values):
        review_calls.append(values)
        return SimpleNamespace(empty_claim_rationales=patch["empty_claim_rationales"],
            cue_resolutions={key: CueValue.model_validate(item) for key, item in patch["cue_resolutions"].items()})

    predictor.planner, predictor.coverage = plan, review
    values = {"document_context": "{}", "source_blocks": "[]", "reference_claims": "[]",
              "relation_ontology": "actual source ontology", "review_stage": "old correction stage",
              "draft_graph": json_text(graph), "repair_feedback": json_text(list(judgments.values())),
              "discourse_cues": json_text([{"cue_id": "r2:s1:discourse", "source_span_id": "r2:s1"}])}
    return predictor, values, graph, plan_calls, review_calls


def test_staged_correction_retains_two_distinct_requests_and_exact_declared_graph(tmp_path):
    predictor, values, graph, plan_calls, review_calls = staged_case(tmp_path)
    result = predictor(**values)
    assert result.edges["e0"].model_dump() == graph["edges"]["e0"]
    assert result.edges["e1"].relation == "Parallel"
    assert json.loads(review_calls[0]["required_empty_claim_ids"]) == ["r2"]
    assert json.loads(review_calls[0]["eligible_cue_edges"]) == {"r2:s1:discourse": ["e1"]}
    assert plan_calls[0]["review_stage"] != review_calls[0]["review_stage"]
    record = json.loads(next((tmp_path / "correction-patches").glob("*.json")).read_text(encoding="utf-8"))
    assert record["plan_inputs_digest"] != record["coverage_inputs_digest"]
    assert record["candidate_access"] is False
    assert record["status"] == "APPLIED_PENDING_EDGE_REVIEW"


def test_staged_source_review_names_invalid_actual_cue_and_preserves_failure(tmp_path):
    predictor, values, _, _, _ = staged_case(tmp_path, bad_cue=True)
    with pytest.raises(SourceContractError, match="Actual cue r2:s1:discourse"):
        predictor(**values)
    record = json.loads(next((tmp_path / "correction-patches").glob("*.json")).read_text(encoding="utf-8"))
    assert record["status"] == "PROPOSED_NOT_VERIFIED"
    assert "mapped_graph" not in record
