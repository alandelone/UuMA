from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_graph_reference import SourceGraphEdge
from rstv4.skeleton_mapped_graph_v2 import CueValue
from rstv4.skeleton_transactional_reference import EdgeRepair
from rstv4.skeleton_transactional_reference_v2 import (
    SpecificOmissionGraphPredictor,
    omission_diagnostic,
)
from test_skeleton_transactional_reference import repair_case


def test_exact_omission_diagnostic_tracks_declared_graph_not_previous_list():
    graph, _, patch = repair_case()
    patch["repairs"]["e1"].update(action="REMOVE", replacement=None)
    patch["empty_claim_rationales"]["r0"] = "Incorrect old source explanation."
    before = copy.deepcopy((graph, patch))
    diagnostic = omission_diagnostic({"original_graph": graph, "patch": patch})
    assert diagnostic["required_empty_claim_ids"] == ["r1", "r2"]
    assert diagnostic["missing_claim_ids"] == ["r1"]
    assert diagnostic["unexpected_claim_ids"] == ["r0"]
    assert (graph, patch) == before


def test_real_predictor_boundary_preserves_bad_proposal_and_names_exact_missing_id(tmp_path):
    graph, judgments, patch = repair_case()
    patch["empty_claim_rationales"] = {}
    result = SimpleNamespace(
        repairs={key: EdgeRepair.model_validate(value) for key, value in patch["repairs"].items()},
        additional_edges={key: SourceGraphEdge.model_validate(value) for key, value in patch["additional_edges"].items()},
        cue_resolutions={key: CueValue.model_validate(value) for key, value in patch["cue_resolutions"].items()},
        empty_claim_rationales={}, corrections=patch["corrections"],
    )
    predictor = SpecificOmissionGraphPredictor(tmp_path)
    predictor.predictor = lambda **values: result
    with pytest.raises(SourceContractError, match='missing_claim_ids.*r2'):
        predictor(draft_graph=json_text(graph), repair_feedback=json_text(list(judgments.values())))
    files = list((tmp_path / "correction-patches").glob("*.json"))
    assert len(files) == 1
    assert 'PROPOSED_NOT_VERIFIED' in files[0].read_text(encoding="utf-8")
