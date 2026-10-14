from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, write_json
from rstv4.skeleton_graph_reference import GRAPH_REFERENCE_VERSION, restore_graph
from rstv4.skeleton_verified_reference import VerifiedReferenceBuilder
from test_skeleton_graph_reference import source_case


def prepared_builder(tmp_path, monkeypatch, *, failed_judge=False, invalid_correction=False):
    import rstv4.skeleton_verified_reference as module

    block, reference, correct_graph = source_case()
    wrong_graph = copy.deepcopy(correct_graph)
    wrong_graph["connections"][0]["outgoing_relations"][0]["relation"] = "Elaboration"
    wrong_graph["cue_resolutions"][0]["relation_keys"][0]["relation"] = "Elaboration"
    initial = {**copy.deepcopy(reference), "relations": [{
        name: value for name, value in wrong_graph["connections"][0]["outgoing_relations"][0].items()
        if name not in {"source_evidence_span_ids", "target_evidence_span_ids"}
    }]}
    inputs = {"document_context": "Source-only case", "source_blocks": json.dumps([block])}

    class Drafts:
        def __init__(self, output, **kwargs):
            self.output = output
            key = digest({"version": GRAPH_REFERENCE_VERSION, "inputs": inputs})
            write_json(output / "references" / f"{key}.json", {"graph_review": wrong_graph})

        def build(self, value):
            assert value == inputs
            return copy.deepcopy(initial)

    class Edges:
        def __init__(self, *args, **kwargs):
            pass

        def assess(self, value, synthetic, index):
            assert value == inputs
            edge = synthetic["relations"][index]
            return {
                "input_digest": digest(edge),
                "status": "EVALUATION_CONTRACT_FAILURE" if failed_judge else "ASSESSED",
                "failed_attempts": ["Invalid endpoint evidence"] if failed_judge else [],
                "verdict": None if failed_judge else {
                    **{key: edge[key] for key in ("source_id", "target_id", "relation")},
                    "verdict": "SUPPORTED" if edge["relation"] == "Cause" else "UNSUPPORTED",
                    "source_evidence_span_ids": ["paper:b1:s1"],
                    "target_evidence_span_ids": ["paper:b1:s2"],
                    "rationale": "The gap is an explanatory reason, not a general-to-detail proposition.",
                },
            }

    calls = []
    aliased = restore_graph(correct_graph, {"paper:b1:r1": "r0", "paper:b1:r2": "r1"})
    if invalid_correction:
        aliased["connections"] = []

    def response(self, key, body):
        calls.append(body)
        return {"model": "gemini-3.1-pro", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": json.dumps(aliased)}, "finish_reason": "stop"}]}

    monkeypatch.setattr(module, "GraphReferenceBuilder", Drafts)
    monkeypatch.setattr(module, "EndpointEdgeReviewer", Edges)
    monkeypatch.setattr(ReceiptLM, "_durable_response", response)
    builder = VerifiedReferenceBuilder(tmp_path, actual_model="gemini-3.1-pro")
    builder.lm.excluded_routes = []
    return builder, inputs, reference, calls


def test_full_reference_correction_preserves_claims_and_failed_round(tmp_path, monkeypatch):
    builder, inputs, base, calls = prepared_builder(tmp_path, monkeypatch)
    result = builder.build(inputs)
    assert result["claims"] == base["claims"] and result["roles"] == base["roles"]
    assert result["relations"][0]["relation"] == "Cause"
    rounds = sorted((tmp_path / "rounds").rglob("*.json"))
    assert len(rounds) == 2
    original = json.loads(rounds[0].read_text(encoding="utf-8"))
    assert not original["source_graph_review_gate_passed"]
    assert original["reference"]["relations"][0]["relation"] == "Elaboration"
    assert len(calls) == 1
    prompt = calls[0]["messages"][1]["content"]
    assert "There is a research gap." in prompt and "We seek a solution." in prompt
    assert "UNSUPPORTED" in prompt
    assert builder.build(inputs) == result and len(calls) == 1


def test_source_edge_judge_failure_cannot_be_repaired_by_discarding_edge(tmp_path, monkeypatch):
    builder, inputs, _, calls = prepared_builder(tmp_path, monkeypatch, failed_judge=True)
    with pytest.raises(SourceContractError, match="evaluator failed"):
        builder.build(inputs)
    assert not calls
    assert not list((tmp_path / "references").glob("*.json"))
    assert list((tmp_path / "rounds").rglob("*.json"))


def test_missing_claims_in_graph_correction_remain_a_source_failure(tmp_path, monkeypatch):
    builder, inputs, _, _ = prepared_builder(tmp_path, monkeypatch, invalid_correction=True)
    with pytest.raises(SourceContractError, match="correction failed"):
        builder.build(inputs)
    assert not list((tmp_path / "references").glob("*.json"))
    assert list((tmp_path / "failures").glob("*.json"))
