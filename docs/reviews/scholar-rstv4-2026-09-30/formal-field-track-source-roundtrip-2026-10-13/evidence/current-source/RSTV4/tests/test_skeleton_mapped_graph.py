from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import ReceiptLM
from rstv4.skeleton_graph_reference import (
    alias_claims,
    discourse_cues,
    restore_graph,
    validate_graph,
)
from rstv4.skeleton_mapped_graph import (
    MappedGraphReferenceBuilder,
    mapped_graph,
    restore_mapped_graph,
)
from test_skeleton_graph_reference import source_case


def mapped_case():
    block, reference, graph = source_case()
    _, mapping = alias_claims(reference["claims"])
    aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
    return block, reference, graph, mapping, mapped_graph(aliased)


def test_graph_key_round_trip_preserves_actual_edges_and_cue_decisions():
    block, reference, graph, mapping, value = mapped_case()
    restored = restore_mapped_graph(value, mapping, discourse_cues([block]))
    assert restored == graph
    assert validate_graph(reference, [block], discourse_cues([block]), restored) == [
        {key: graph["connections"][0]["outgoing_relations"][0][key]
         for key in ("source_reference_id", "target_reference_id", "relation", "rationale")}
    ]


@pytest.mark.parametrize("mutation", [
    "missing_claim", "extra_claim", "missing_cue", "absent_cue_edge", "orphan_edge",
    "duplicate_connection", "wrong_connection", "duplicate_cue_edge",
])
def test_graph_keys_reject_incomplete_or_inconsistent_references(mutation):
    block, _, _, mapping, value = mapped_case()
    cue = next(iter(value["cue_resolutions"]))
    if mutation == "missing_claim":
        del value["connections"]["r1"]
    elif mutation == "extra_claim":
        value["connections"]["r9"] = copy.deepcopy(value["connections"]["r1"])
    elif mutation == "missing_cue":
        del value["cue_resolutions"][cue]
    elif mutation == "absent_cue_edge":
        value["cue_resolutions"][cue]["relation_ids"] = ["e99"]
    elif mutation == "orphan_edge":
        value["edges"]["e1"] = copy.deepcopy(value["edges"]["e0"])
    elif mutation == "duplicate_connection":
        value["connections"]["r0"]["outgoing_edge_ids"].append("e0")
    elif mutation == "wrong_connection":
        value["connections"]["r0"]["outgoing_edge_ids"] = []
        value["connections"]["r1"]["outgoing_edge_ids"] = ["e0"]
    else:
        value["cue_resolutions"][cue]["relation_ids"].append("e0")
    with pytest.raises(SourceContractError):
        restore_mapped_graph(value, mapping, discourse_cues([block]))


def test_unique_edge_keys_do_not_weaken_endpoint_evidence_validation():
    block, reference, _, mapping, value = mapped_case()
    value["edges"]["e0"]["target_evidence_span_ids"] = ["paper:b1:s1"]
    graph = restore_mapped_graph(value, mapping, discourse_cues([block]))
    with pytest.raises(SourceContractError, match="actual endpoint"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_unique_edge_keys_preserve_unresolved_cue_failure():
    block, reference, _, mapping, value = mapped_case()
    cue = next(iter(value["cue_resolutions"]))
    value["cue_resolutions"][cue].update(classification="AMBIGUOUS", relation_ids=[])
    graph = restore_mapped_graph(value, mapping, discourse_cues([block]))
    with pytest.raises(SourceContractError, match="Unresolved"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_graph_annotation_review_are_distinct_calls_and_cached_replay(tmp_path, monkeypatch):
    import rstv4.skeleton_mapped_graph as module

    block, reference, graph, _, value = mapped_case()

    class Atomic:
        def __init__(self, *args, **kwargs):
            pass

        def block(self, context, requested):
            assert requested == block
            return copy.deepcopy(reference)

    monkeypatch.setattr(module, "SourceReferenceBuilder", Atomic)
    requests = []

    def response(self, key, body):
        requests.append((key, body))
        return {"model": "gemini-3.1-pro", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": json.dumps(value)}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ReceiptLM, "_durable_response", response)
    builder = MappedGraphReferenceBuilder(tmp_path, actual_model="gemini-3.1-pro")
    builder.lm.excluded_routes = []
    inputs = {"document_context": "Development source only", "source_blocks": json.dumps([block])}
    assert builder.build(inputs)["relations"] == validate_graph(reference, [block], discourse_cues([block]), graph)
    assert len(requests) == 2 and requests[0][0] != requests[1][0]
    assert "INITIAL_SOURCE_GRAPH_ANNOTATION" in requests[0][1]["messages"][1]["content"]
    assert "INDEPENDENT_SOURCE_GRAPH_REVIEW" in requests[1][1]["messages"][1]["content"]
    builder.build(inputs)
    assert len(requests) == 2
    record = next((tmp_path / "references").glob("*.json"))
    saved = json.loads(record.read_text(encoding="utf-8"))
    saved["mapped_graph"]["edges"]["e0"]["relation"] = "Support"
    record.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(SourceContractError, match="differs"):
        builder.build(inputs)
