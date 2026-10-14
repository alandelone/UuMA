from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_cached_reference import CachedVerifiedReferenceBuilder
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_endpoint_review import ENDPOINT_REVIEW_VERSION, RELATION_ONTOLOGY
from rstv4.skeleton_graph_reference import GRAPH_REFERENCE_VERSION, alias_claims, validate_graph
from rstv4.skeleton_mapped_graph_v2 import MappedVerifiedReferenceBuilder
from rstv4.skeleton_source_reference import SOURCE_REFERENCE_VERSION
from rstv4.skeleton_verified_reference import VERIFIED_REFERENCE_VERSION, reference_edge_inputs
from test_skeleton_graph_reference import source_case


def prepared_parent(tmp_path, monkeypatch):
    block, base, graph = source_case()
    graph["cue_resolutions"][0]["relation_keys"][0]["rationale"] = "The cue-specific explanation is independently retained."
    inputs = {"document_context": "Unchanged development source", "source_blocks": json_text([block])}
    reference = {**copy.deepcopy(base), "relations": validate_graph(base, [block], [{
        "cue_id": graph["cue_resolutions"][0]["cue_id"], "source_span_id": "paper:b1:s2",
    }], graph)}
    atomic, draft_root, parent_root, edges = [tmp_path / name for name in ("atomic", "draft-parent", "verified-parent", "edges")]
    block_key = digest({"version": SOURCE_REFERENCE_VERSION, "context": inputs["document_context"], "block": block})
    write_json(atomic / "blocks" / f"{block_key}.json", {"input_digest": block_key, "reference": base})
    _, mapping = alias_claims(base["claims"])
    draft = {"inputs_digest": digest(inputs), "atomic_reference_digest": digest(base),
             "reference": reference, "graph_review": graph, "identifier_map": mapping,
             "candidate_access": False, "stages": {
                "INITIAL_SOURCE_GRAPH_ANNOTATION": {"input_digest": "annotation-request", "graph": graph},
                "INDEPENDENT_SOURCE_GRAPH_REVIEW": {"input_digest": "review-request", "graph": graph}}}
    draft_key = digest({"version": GRAPH_REFERENCE_VERSION, "inputs": inputs})
    write_json(draft_root / "references" / f"{draft_key}.json", draft)
    synthetic = reference_edge_inputs(reference, [block])
    edge = synthetic["relations"][0]
    source, target = synthetic["block_atoms"][0]["atoms"]
    values = {"document_context": inputs["document_context"], "source_blocks": json_text([block]),
              "source_atom": json_text(source), "target_atom": json_text(target),
              "candidate_edge": json_text(edge), "relation_ontology": RELATION_ONTOLOGY}
    edge_key = digest({"version": ENDPOINT_REVIEW_VERSION, "inputs": values})
    verdict = {"input_digest": edge_key, "status": "ASSESSED", "version": ENDPOINT_REVIEW_VERSION,
               "failed_attempts": [], "verdict": {**{key: edge[key] for key in ("source_id", "target_id", "relation")},
                   "verdict": "SUPPORTED", "rationale": "The explicit gap motivates the stated research objective.",
                   "source_evidence_span_ids": ["paper:b1:s1"], "target_evidence_span_ids": ["paper:b1:s2"]}}
    write_json(edges / "edges" / f"{edge_key}.json", verdict)
    round_record = {"round": 0, "reference": reference, "graph_review": graph, "edge_reviews": [verdict],
                    "source_graph_review_gate_passed": True}
    parent_key = digest({"version": VERIFIED_REFERENCE_VERSION, "inputs": inputs})
    parent = {"version": VERIFIED_REFERENCE_VERSION, "inputs_digest": digest(inputs),
              "atomic_reference_digest": digest(base), "draft_record_digest": digest(draft),
              "draft_reference_digest": digest(reference), "identifier_map": mapping, "reference": reference,
              "graph_review": graph, "candidate_access": False, "source_graph_review_gate_passed": True,
              "rounds": [{"round": 0, "round_digest": digest(round_record), "edges": 1,
                          "source_graph_review_gate_passed": True}]}
    parent_path = parent_root / "references" / f"{parent_key}.json"
    write_json(parent_path, parent)
    write_json(parent_root / "rounds" / parent_key / "000.json", round_record)

    def no_call(*args, **kwargs):
        raise AssertionError("Exact source parent reuse must make no model calls")

    monkeypatch.setattr(ReceiptLM, "_durable_response", no_call)
    builder = CachedVerifiedReferenceBuilder(tmp_path / "output", actual_model="gemini-3.1-pro",
        atomic_source=atomic, edge_source=edges, legacy_draft=draft_root,
        legacy_verified=[(parent_root, draft_root)])
    return builder, inputs, reference, parent_path, edges / "edges" / f"{edge_key}.json", atomic / "blocks" / f"{block_key}.json"


def test_reuse_revalidates_all_source_lineage_without_model_calls(tmp_path, monkeypatch):
    builder, inputs, expected, parent, _, _ = prepared_parent(tmp_path, monkeypatch)
    original = parent.read_bytes()
    assert builder.build(inputs) == expected
    assert builder.build(inputs) == expected
    assert parent.read_bytes() == original
    saved = json.loads(next((builder.output / "references").glob("*.json")).read_text(encoding="utf-8"))
    assert saved["origin"] == "EXACT_REVALIDATED_VERIFIED_SOURCE_PARENT"
    assert saved["new_semantic_inference_calls"] == 0


def test_source_parent_reuse_rejects_tampered_endpoint_cache(tmp_path, monkeypatch):
    builder, inputs, _, _, edge_path, _ = prepared_parent(tmp_path, monkeypatch)
    saved = json.loads(edge_path.read_text(encoding="utf-8"))
    saved["verdict"]["verdict"] = "UNSUPPORTED"
    write_json(edge_path, saved)
    with pytest.raises(SourceContractError, match="cache/input changed"):
        builder.build(inputs)


def test_changed_source_reference_never_adopts_old_verified_graph(tmp_path, monkeypatch):
    builder, inputs, _, _, _, atomic_path = prepared_parent(tmp_path, monkeypatch)
    saved = json.loads(atomic_path.read_text(encoding="utf-8"))
    saved["reference"]["claims"][0]["qualifications"] = ["New source-only qualification requires review"]
    write_json(atomic_path, saved)
    calls = []

    def fallback(self, actual_inputs):
        calls.append(actual_inputs)
        return {"requires_new_review": True}

    monkeypatch.setattr(MappedVerifiedReferenceBuilder, "build", fallback)
    assert builder.build(inputs) == {"requires_new_review": True}
    assert calls == [inputs]
    assert not list((builder.output / "references").glob("*.json"))


def test_replay_rejects_changed_parent_correction_round(tmp_path, monkeypatch):
    builder, inputs, _, parent_path, _, _ = prepared_parent(tmp_path, monkeypatch)
    builder.build(inputs)
    round_path = parent_path.parent.parent / "rounds" / parent_path.stem / "000.json"
    saved = json.loads(round_path.read_text(encoding="utf-8"))
    saved["edge_reviews"][0]["verdict"]["verdict"] = "UNSUPPORTED"
    write_json(round_path, saved)
    with pytest.raises(SourceContractError, match="parent round changed"):
        builder.build(inputs)
