from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import ReceiptLM
from rstv4.skeleton_graph_reference import (
    GraphReferenceBuilder,
    alias_claims,
    discourse_cues,
    restore_graph,
    validate_graph,
)


def source_case():
    text = "There is a research gap. As a result, we seek a solution."
    block = {
        "block_id": "paper:b1", "text": text,
        "source_spans": [
            {"span_id": "paper:b1:s1", "start": 0, "end": 24, "text": text[:24]},
            {"span_id": "paper:b1:s2", "start": 24, "end": len(text), "text": text[24:]},
        ],
    }
    claims = [{
        "reference_id": f"paper:b1:r{index}", "block_id": "paper:b1",
        "statement": statement, "quote": span["text"],
        "source_span_ids": [span["span_id"]], "qualifications": [], "intent": intent,
    } for index, (span, statement, intent) in enumerate(zip(
        block["source_spans"], ["There is a research gap.", "We seek a solution."],
        ["Research_Gap", "Paper_Objective"], strict=True,
    ), 1)]
    reference = {"claims": claims, "relations": [], "roles": [{
        "block_id": "paper:b1", "role": "Motivation_Intro", "confidence": 1.0,
        "rationale": "The gap motivates the study.",
    }]}
    edge = {
        "source_reference_id": claims[0]["reference_id"],
        "target_reference_id": claims[1]["reference_id"], "relation": "Cause",
        "rationale": "The explicit research gap motivates the stated research objective.",
        "source_evidence_span_ids": ["paper:b1:s1"],
        "target_evidence_span_ids": ["paper:b1:s2"],
    }
    relation_key = {key: edge[key] for key in (
        "source_reference_id", "target_reference_id", "relation", "rationale",
    )}
    graph = {"connections": [
        {"reference_id": claims[0]["reference_id"], "outgoing_relations": [edge],
         "no_outgoing_rationale": None},
        {"reference_id": claims[1]["reference_id"], "outgoing_relations": [],
         "no_outgoing_rationale": "The objective has no stated outgoing relation to another claim."},
    ], "cue_resolutions": [{
        "cue_id": "paper:b1:s2:discourse", "classification": "SUPPORTED_RELATION",
        "relation_keys": [relation_key], "rationale": "As a result explicitly links the gap to the objective.",
    }], "corrections": []}
    return block, reference, graph


def test_graph_requires_every_claim_and_cue():
    block, reference, graph = source_case()
    cues = discourse_cues([block])
    assert len(validate_graph(reference, [block], cues, graph)) == 1
    for key in ("connections", "cue_resolutions"):
        dropped = copy.deepcopy(graph)
        dropped[key] = []
        with pytest.raises(SourceContractError, match="every"):
            validate_graph(reference, [block], cues, dropped)


def test_graph_rejects_duplicate_claim_review():
    block, reference, graph = source_case()
    graph["connections"][1] = copy.deepcopy(graph["connections"][0])
    with pytest.raises(SourceContractError, match="every"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_graph_rejects_wrong_endpoint_anchor():
    block, reference, graph = source_case()
    graph["connections"][0]["outgoing_relations"][0]["target_evidence_span_ids"] = ["paper:b1:s1"]
    with pytest.raises(SourceContractError, match="actual endpoint"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_graph_does_not_accept_unresolved_cues_as_gold():
    block, reference, graph = source_case()
    graph["cue_resolutions"][0]["classification"] = "AMBIGUOUS"
    graph["cue_resolutions"][0]["relation_keys"] = []
    validate_graph(reference, [block], discourse_cues([block]), graph, require_resolved=False)
    with pytest.raises(SourceContractError, match="Unresolved"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_source_graph_aliases_preserve_claim_content():
    _, reference, graph = source_case()
    changed, mapping = alias_claims(reference["claims"])
    for original, alias in zip(reference["claims"], changed, strict=True):
        assert {k: v for k, v in original.items() if k != "reference_id"} == {
            k: v for k, v in alias.items() if k != "reference_id"
        }
    inverse = {original: alias for alias, original in mapping.items()}
    aliased = restore_graph(graph, inverse)
    assert restore_graph(aliased, mapping) == graph
    aliased["connections"][0]["reference_id"] = "invented"
    with pytest.raises(SourceContractError, match="Invented"):
        restore_graph(aliased, mapping)


def test_zero_outgoing_claims_need_omission_explanation():
    block, reference, graph = source_case()
    graph["connections"][1]["no_outgoing_rationale"] = ""
    with pytest.raises(SourceContractError, match="omission-review"):
        validate_graph(reference, [block], discourse_cues([block]), graph)


def test_annotation_and_review_have_distinct_real_receipt_requests(tmp_path, monkeypatch):
    import rstv4.skeleton_graph_reference as module

    block, reference, graph = source_case()

    class Atomic:
        def __init__(self, *args, **kwargs):
            pass

        def block(self, context, value):
            assert value == block
            return copy.deepcopy(reference)

    monkeypatch.setattr(module, "SourceReferenceBuilder", Atomic)
    _, mapping = alias_claims(reference["claims"])
    aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
    requests = []

    def response(self, key, body):
        requests.append((key, body))
        return {"model": "gemini-3.1-pro", "choices": [{
            "index": 0, "message": {"role": "assistant", "content": json.dumps(aliased)},
            "finish_reason": "stop",
        }]}

    monkeypatch.setattr(ReceiptLM, "_durable_response", response)
    builder = GraphReferenceBuilder(tmp_path, actual_model="gemini-3.1-pro")
    builder.lm.excluded_routes = []
    inputs = {"document_context": "Source-only development case", "source_blocks": json.dumps([block])}
    result = builder.build(inputs)
    assert len(result["relations"]) == 1
    assert len(requests) == 2 and requests[0][0] != requests[1][0]
    assert "INITIAL_SOURCE_GRAPH_ANNOTATION" in requests[0][1]["messages"][1]["content"]
    assert "INDEPENDENT_SOURCE_GRAPH_REVIEW" in requests[1][1]["messages"][1]["content"]
    # Replaying the complete graph must not submit either inference again.
    assert builder.build(inputs) == result
    assert len(requests) == 2
