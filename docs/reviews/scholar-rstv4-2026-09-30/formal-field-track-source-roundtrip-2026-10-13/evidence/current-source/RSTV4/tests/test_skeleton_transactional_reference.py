from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_transactional_reference import apply_source_graph_patch, rejected_edge_ids


def repair_case():
    def edge(source, target, relation):
        return {"source_reference_id": source, "target_reference_id": target, "relation": relation,
                "rationale": "Exact source-based explanation of the directed relation.",
                "source_evidence_span_ids": [source + ":s1"],
                "target_evidence_span_ids": [target + ":s1"]}
    original = {
        "edges": {"e0": edge("r0", "r1", "Cause"), "e1": edge("r1", "r2", "Elaboration")},
        "connection_order": ["r0", "r1", "r2"], "cue_order": ["r2:s1:discourse"],
        "connections": {"r0": {}, "r1": {}, "r2": {}},
        "cue_resolutions": {"r2:s1:discourse": {"classification": "SUPPORTED_RELATION",
                                               "relation_ids": ["e1"], "rationale": "Actual source cue explanation."}},
    }
    judgments = {"e1": {**original["edges"]["e1"], "source_review": {
        "verdict": "UNSUPPORTED", "rationale": "Additional coordinate activity is not elaboration."}}}
    patch = {
        "repairs": {"e1": {"action": "REPLACE", "replacement": edge("r1", "r2", "Parallel"),
                           "rationale": "The source explicitly coordinates two distinct activities."}},
        "additional_edges": {}, "cue_resolutions": copy.deepcopy(original["cue_resolutions"]),
        "empty_claim_rationales": {"r2": "The last coordinate activity has no outgoing assertion."},
        "corrections": ["Reconsidered the exact rejected edge from raw source."],
    }
    return original, judgments, patch


def test_explicit_replacement_preserves_supported_edges_and_original_inputs():
    graph, judgments, patch = repair_case()
    before = copy.deepcopy((graph, judgments, patch))
    result = apply_source_graph_patch(graph, judgments, patch)
    assert result["edges"]["e0"] == graph["edges"]["e0"]
    assert result["edges"]["e1"]["relation"] == "Parallel"
    assert result["connections"]["r1"]["outgoing_edge_ids"] == ["e1"]
    assert (graph, judgments, patch) == before


def test_removal_requires_a_declared_decision_and_new_empty_claim_rationale():
    graph, judgments, patch = repair_case()
    patch["repairs"]["e1"].update(action="REMOVE", replacement=None)
    patch["cue_resolutions"]["r2:s1:discourse"].update(
        classification="STRUCTURAL_OR_NON_RELATIONAL", relation_ids=[])
    with pytest.raises(SourceContractError, match="all and only empty"):
        apply_source_graph_patch(graph, judgments, patch)
    patch["empty_claim_rationales"]["r1"] = "The source warrants no outgoing edge from this activity."
    result = apply_source_graph_patch(graph, judgments, patch)
    assert set(result["edges"]) == {"e0"}
    assert result["cue_resolutions"]["r2:s1:discourse"]["relation_ids"] == []


@pytest.mark.parametrize("change", ["omit_rejected", "edit_supported", "same_tuple", "hidden_replacement",
                                    "unknown", "existing_new_id", "absent_endpoint", "omit_cue"])
def test_source_repair_rejects_incomplete_or_unauthorized_operations(change):
    graph, judgments, patch = repair_case()
    if change == "omit_rejected":
        patch["repairs"] = {}
    elif change == "edit_supported":
        patch["repairs"]["e0"] = copy.deepcopy(patch["repairs"]["e1"])
    elif change == "same_tuple":
        patch["repairs"]["e1"]["replacement"]["relation"] = "Elaboration"
    elif change == "hidden_replacement":
        patch["repairs"]["e1"]["action"] = "REMOVE"
    elif change == "unknown":
        patch["repairs"]["e1"]["replacement"]["relation"] = "UNKNOWN"
    elif change == "existing_new_id":
        patch["additional_edges"]["e0"] = copy.deepcopy(patch["repairs"]["e1"]["replacement"])
    elif change == "absent_endpoint":
        patch["repairs"]["e1"]["replacement"]["target_reference_id"] = "r99"
    else:
        patch["cue_resolutions"] = {}
    with pytest.raises(SourceContractError):
        apply_source_graph_patch(graph, judgments, patch)


def test_criticism_bijection_uses_actual_edge_ids_and_exact_rejected_tuples():
    graph, judgments, _ = repair_case()
    value = list(judgments.values())
    assert rejected_edge_ids(graph, value) == judgments
    with pytest.raises(SourceContractError, match="distinct actual rejected"):
        rejected_edge_ids(graph, value * 2)
    value[0]["source_review"]["verdict"] = "SUPPORTED"
    with pytest.raises(SourceContractError, match="distinct actual rejected"):
        rejected_edge_ids(graph, value)


def test_addition_cannot_reintroduce_an_explicitly_rejected_relation():
    graph, judgments, patch = repair_case()
    patch["additional_edges"]["e3"] = copy.deepcopy(graph["edges"]["e1"])
    with pytest.raises(SourceContractError, match="reintroduces a rejected"):
        apply_source_graph_patch(graph, judgments, patch)
