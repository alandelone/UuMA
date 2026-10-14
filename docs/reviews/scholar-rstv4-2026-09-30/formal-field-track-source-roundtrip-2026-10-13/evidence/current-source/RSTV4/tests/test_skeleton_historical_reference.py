from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_augmented_reference_v3 import AugmentedVerifiedReferenceBuilder
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_endpoint_review import ENDPOINT_REVIEW_VERSION, RELATION_ONTOLOGY
from rstv4.skeleton_graph_reference import restore_graph
from rstv4.skeleton_historical_reference import HistoricalVerifiedReferenceBuilder
from rstv4.skeleton_mapped_graph_v2 import MAPPED_GRAPH_VERSION, mapped_graph
from rstv4.skeleton_verified_reference import reference_edge_inputs
from test_skeleton_cached_reference import prepared_parent


def historical_case(tmp_path, monkeypatch):
    old, inputs, expected, parent_path, edge_path, atomic_path = prepared_parent(tmp_path, monkeypatch)
    parent = json.loads(parent_path.read_text())
    parent_root, draft_root = old.legacy_verified[0]
    draft_path = next((draft_root / "references").glob("*.json"))
    draft = json.loads(draft_path.read_text())
    old_graph = copy.deepcopy(draft["graph_review"])
    for connection in old_graph["connections"]:
        for edge in connection["outgoing_relations"]:
            edge["relation"] = "Support"
    for cue in old_graph["cue_resolutions"]:
        for edge in cue["relation_keys"]:
            edge["relation"] = "Support"
    old_ref = copy.deepcopy(expected)
    for edge in old_ref["relations"]:
        edge["relation"] = "Support"
    mapping = parent["identifier_map"]
    encoded = mapped_graph(restore_graph(old_graph, {original: alias for alias, original in mapping.items()}))
    draft.update(version=MAPPED_GRAPH_VERSION, reference=old_ref, graph_review=old_graph,
                 mapped_graph=encoded, origin="UNIQUE_KEY_SOURCE_GRAPH")
    for stage in draft["stages"].values():
        stage.update(graph=old_graph, mapped_graph=encoded)
    write_json(draft_path, draft)
    blocks = json.loads(inputs["source_blocks"])
    synthetic = reference_edge_inputs(old_ref, blocks)
    edge = synthetic["relations"][0]
    source, target = synthetic["block_atoms"][0]["atoms"]
    values = {"document_context": inputs["document_context"], "source_blocks": json_text(blocks),
              "source_atom": json_text(source), "target_atom": json_text(target),
              "candidate_edge": json_text(edge), "relation_ontology": RELATION_ONTOLOGY}
    key = digest({"version": ENDPOINT_REVIEW_VERSION, "inputs": values})
    rejected = json.loads(edge_path.read_text())
    rejected.update(input_digest=key)
    rejected["verdict"].update(relation="Support", verdict="UNSUPPORTED",
                               rationale="The gap motivates the objective; it does not prove it.")
    write_json(old.edges.output / "edges" / f"{key}.json", rejected)
    initial = {"round": 0, "reference": old_ref, "graph_review": old_graph,
               "edge_reviews": [rejected], "source_graph_review_gate_passed": False}
    final = json.loads((parent_root / "rounds" / parent_path.stem / "000.json").read_text())
    final["round"] = 1
    write_json(parent_root / "rounds" / parent_path.stem / "000.json", initial)
    write_json(parent_root / "rounds" / parent_path.stem / "001.json", final)
    parent.update(draft_record_digest=digest(draft), draft_reference_digest=digest(old_ref),
                  rounds=[{"round": number, "round_digest": digest(record), "edges": 1,
                           "source_graph_review_gate_passed": record["source_graph_review_gate_passed"]}
                          for number, record in enumerate((initial, final))])
    write_json(parent_path, parent)
    builder = HistoricalVerifiedReferenceBuilder(tmp_path / "historical-output", actual_model="gemini-3.1-pro",
        atomic_source=old.drafts.atomic.original.output, edge_source=old.edges.output,
        legacy_verified=[(parent_root, draft_root)], mapped_draft_parents=[draft_root])
    return builder, inputs, expected, parent_path, draft_path, edge_path, atomic_path


def test_historical_replay_retains_rejected_draft_and_current_final_edge_without_inference(tmp_path, monkeypatch):
    builder, inputs, expected, parent, draft, _, _ = historical_case(tmp_path, monkeypatch)
    before = parent.read_bytes(), draft.read_bytes()
    assert builder.build(inputs) == expected
    assert builder.build(inputs) == expected
    assert (parent.read_bytes(), draft.read_bytes()) == before
    final = json.loads(next((builder.output / "references").glob("*.json")).read_text())
    own_draft = json.loads(next((builder.output / "draft-source-graph/references").glob("*.json")).read_text())
    assert own_draft["reference"]["relations"][0]["relation"] == "Support"
    assert final["reference"]["relations"][0]["relation"] == "Cause"
    assert final["current_verified_edge_preservation"]["ledger"][0]["edge"]["relation"] == "Cause"
    assert final["new_semantic_inference_calls"] == 0 and len(final["rounds"]) == 2


def test_historical_replay_rejects_tampering_of_an_earlier_rejected_round(tmp_path, monkeypatch):
    builder, inputs, _, parent, _, _, _ = historical_case(tmp_path, monkeypatch)
    initial_path = parent.parent.parent / "rounds" / parent.stem / "000.json"
    changed = json.loads(initial_path.read_text())
    changed["edge_reviews"][0]["verdict"]["verdict"] = "SUPPORTED"
    write_json(initial_path, changed)
    with pytest.raises(SourceContractError, match="correction round changed"):
        builder.build(inputs)


def test_historical_replay_rejects_a_changed_actual_endpoint_cache(tmp_path, monkeypatch):
    builder, inputs, _, _, _, cache, _ = historical_case(tmp_path, monkeypatch)
    changed = json.loads(cache.read_text())
    changed["verdict"]["verdict"] = "UNSUPPORTED"
    write_json(cache, changed)
    with pytest.raises(SourceContractError, match="cache/input changed"):
        builder.build(inputs)


def test_changed_qualification_does_not_enter_historical_replay(tmp_path, monkeypatch):
    builder, inputs, _, _, _, _, atomic_path = historical_case(tmp_path, monkeypatch)
    changed = json.loads(atomic_path.read_text())
    changed["reference"]["claims"][0]["qualifications"] = ["New source qualification"]
    write_json(atomic_path, changed)
    calls = []
    monkeypatch.setattr(AugmentedVerifiedReferenceBuilder, "build",
                        lambda self, actual: calls.append(actual) or {"needs_new_review": True})
    assert builder.build(inputs) == {"needs_new_review": True}
    assert calls == [inputs] and not list((builder.output / "references").glob("*.json"))
