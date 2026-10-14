import copy

from rstv4.skeleton_test_cue_reference_v9 import graph_endpoint_domain_errors


def edge(source, target, relation="Cause"):
    return {"source_reference_id": source, "target_reference_id": target,
            "relation": relation, "rationale": "Actual unchanged scientific rationale",
            "source_evidence_span_ids": ["paper:b1:s1"], "target_evidence_span_ids": ["paper:b1:s2"]}


def test_self_edge_reports_exact_id_and_tuple_without_editing_output():
    actual = {"e2": edge("r2", "r2")}
    before = copy.deepcopy(actual)
    assert graph_endpoint_domain_errors(actual) == [
        {"edge_id": "e2", "tuple": ["r2", "r2", "Cause"], "violation": "SELF_EDGE"}]
    assert actual == before


def test_duplicate_reports_both_actual_ids_and_keeps_all_evidence():
    actual = {"e1": edge("r1", "r2"), "e4": edge("r1", "r2")}
    before = copy.deepcopy(actual)
    assert graph_endpoint_domain_errors(actual) == [{
        "edge_id": "e4", "tuple": ["r1", "r2", "Cause"], "first_edge_id": "e1",
        "violation": "DUPLICATE_DIRECTED_TUPLE"}]
    assert actual == before


def test_distinct_directions_and_relation_types_remain_allowed():
    actual = {"e1": edge("r1", "r2"), "e2": edge("r2", "r1"),
              "e3": edge("r1", "r2", "Support")}
    assert graph_endpoint_domain_errors(actual) == []
