from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_graph_reference import SourceGraphEdge, alias_claims, restore_graph
from rstv4.skeleton_mapped_graph_v2 import CueValue, MappedSourceGraphReview
from rstv4.skeleton_preserved_reference import (
    PreservedGraphPredictor,
    PreservedVerifiedReferenceBuilder,
)
from test_skeleton_cached_reference import prepared_parent
from test_skeleton_graph_reference import source_case


def predictor_case():
    _, base, graph = source_case()
    _, mapping = alias_claims(base["claims"])
    aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
    edge = aliased["connections"][0]["outgoing_relations"][0]
    predictor = PreservedGraphPredictor(MappedSourceGraphReview, SimpleNamespace(constraint_edges=[edge]))
    result = SimpleNamespace(edges={"e0": SourceGraphEdge.model_validate(edge)}, cue_resolutions={})
    predictor.predictor = lambda **values: result
    return predictor, edge, result


def test_partial_source_revision_cannot_silently_drop_unchanged_verified_edge():
    predictor, _, result = predictor_case()
    result.edges = {}
    with pytest.raises(SourceContractError, match="lost/changed unchanged verified edge"):
        predictor(repair_feedback="")


def test_retained_edge_requires_its_exact_rationale_and_endpoint_evidence():
    predictor, _, result = predictor_case()
    changed = result.edges["e0"].model_dump()
    changed["target_evidence_span_ids"] = ["paper:b1:s1"]
    result.edges["e0"] = SourceGraphEdge.model_validate(changed)
    with pytest.raises(SourceContractError, match="lost/changed unchanged verified edge"):
        predictor(repair_feedback="")


def test_valid_unchanged_edge_passes_with_no_new_inference():
    predictor, _, result = predictor_case()
    assert predictor(repair_feedback="") is result


def test_cue_diagnostic_names_actual_missing_link_record():
    predictor, _, result = predictor_case()
    result.cue_resolutions = {"paper:b1:s2:discourse": CueValue(
        classification="SUPPORTED_RELATION", relation_ids=[], rationale="The actual cue is unresolved.")}
    with pytest.raises(SourceContractError, match="paper:b1:s2:discourse"):
        predictor(repair_feedback="")


def test_rejected_relation_cannot_recur_with_the_same_type_and_direction():
    predictor, edge, _ = predictor_case()
    predictor.owner.constraint_edges = []
    rejected = {**{key: edge[key] for key in ("source_reference_id", "target_reference_id", "relation")},
                "source_review": {"verdict": "UNSUPPORTED", "rationale": "The actual type is not supported."}}
    with pytest.raises(SourceContractError, match="Rejected source tuple recurred"):
        predictor(repair_feedback="Actual endpoint source criticism: " + json_text([rejected]))


def test_full_parent_reuse_preserves_explicit_edge_ledger_and_all_rounds(tmp_path, monkeypatch):
    _, inputs, expected, parent, _, _ = prepared_parent(tmp_path, monkeypatch)
    builder = PreservedVerifiedReferenceBuilder(tmp_path / "preserved-output", actual_model="gemini-3.1-pro",
        atomic_source=tmp_path / "atomic", edge_source=tmp_path / "edges", legacy_draft=tmp_path / "draft-parent",
        legacy_verified=[(tmp_path / "verified-parent", tmp_path / "draft-parent")])
    before = parent.read_bytes()
    assert builder.build(inputs) == expected
    assert len(builder.drafts.ledger) == 1
    assert builder.drafts.ledger[0]["edge"]["relation"] == "Cause"
    assert builder.build(inputs) == expected
    assert parent.read_bytes() == before
