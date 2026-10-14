from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_complete_reference import EdgeCoverageGraphPredictor, verified_source_additions
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_graph_reference import SourceGraphEdge
from rstv4.skeleton_mapped_graph_v2 import CueValue
from test_skeleton_transactional_reference import repair_case


def test_initial_source_graph_has_edge_first_and_exact_coverage_requests(tmp_path):
    graph, _, patch = repair_case()
    owner = SimpleNamespace(output=tmp_path, current_mapping={key: key for key in graph["connections"]},
                            constraint_edges=[], addition_ledger=[])
    predictor = EdgeCoverageGraphPredictor(owner)
    captured = []
    predictor.planner = lambda **values: SimpleNamespace(
        edges={key: SourceGraphEdge.model_validate(value) for key, value in graph["edges"].items()},
        corrections=["Complete source edge plan."])

    def coverage(**values):
        captured.append(values)
        return SimpleNamespace(empty_claim_rationales=patch["empty_claim_rationales"],
            cue_resolutions={key: CueValue.model_validate(value) for key, value in graph["cue_resolutions"].items()})

    predictor.coverage = coverage
    result = predictor(document_context="{}", source_blocks="[]", relation_ontology="source-only ontology",
        reference_claims=json_text([{"reference_id": key} for key in graph["connections"]]),
        discourse_cues=json_text([{"cue_id": "r2:s1:discourse", "source_span_id": "r2:s1"}]),
        review_stage="INITIAL_SOURCE_GRAPH_ANNOTATION", repair_feedback="")
    assert result.edges["e0"].model_dump() == graph["edges"]["e0"]
    assert captured[0]["required_empty_claim_ids"] == '["r2"]'
    assert captured[0]["review_stage"] == "INITIAL_SOURCE_GRAPH_ANNOTATION_EXACT_SOURCE_COVERAGE"
    assert len(list((tmp_path / "edge-coverage-stages").glob("*.json"))) == 1


def test_edge_only_annotation_cannot_erase_a_verified_required_link(tmp_path):
    graph, _, _ = repair_case()
    owner = SimpleNamespace(output=tmp_path, current_mapping={}, constraint_edges=[graph["edges"]["e0"]],
                            addition_ledger=[])
    predictor = EdgeCoverageGraphPredictor(owner)
    predictor.planner = lambda **values: SimpleNamespace(edges={}, corrections=[])
    with pytest.raises(SourceContractError, match="lost/changed a verified required"):
        predictor(reference_claims="[]", discourse_cues="[]", review_stage="INITIAL_SOURCE_GRAPH_ANNOTATION",
                  repair_feedback="", source_blocks="[]", document_context="{}", relation_ontology="source")


@pytest.mark.parametrize("defect", ["candidate_access", "changed_source"])
def test_source_addition_rejects_candidate_derived_or_changed_scientific_inputs(tmp_path, defect):
    inputs = {"source_blocks": "[]", "document_context": "{}"}
    base = {"claims": [], "roles": [], "relations": []}
    parent = {"reference": base}
    parent_path = tmp_path / "source-parent.json"
    write_json(parent_path, parent)
    proposal = {"relation": "Parallel"}
    report = {"inputs_digest": digest(inputs), "parent_path": str(parent_path),
              "parent_digest": digest(parent), "source_reference": {**copy.deepcopy(base), "relations": [proposal]},
              "candidate_access": False, "held_out_source_access": False,
              "diagnosis_only_no_reference_or_score_edit": True, "proposal": proposal}
    if defect == "candidate_access":
        report["candidate_access"] = True
    else:
        report["source_reference"]["claims"] = [{"statement": "Changed source proposition"}]
    path = tmp_path / "report.json"
    write_json(path, report)
    with pytest.raises(SourceContractError, match="changed source/content/isolation"):
        verified_source_additions(inputs, base, [path])
