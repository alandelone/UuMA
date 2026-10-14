from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

import dspy
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_mapped_graph_v2 import CueValue
from rstv4.skeleton_partition_reference_v3 import (
    ProtocolIndependentCoveragePredictor,
    cue_protocol_errors,
)


def inputs():
    return {"discourse_cues": json.dumps([{"cue_id": "p:b:s1:discourse"}]),
            "eligible_cue_edges": json.dumps({"p:b:s1:discourse": []})}


def decision(classification, ids=None):
    return {"p:b:s1:discourse": {"classification": classification,
            "relation_ids": ids or [], "relation_rationales": {},
            "rationale": "Both propositions are contained in the supplied claim."}}


def test_supported_cue_cannot_be_accepted_without_an_actual_eligible_edge():
    original = decision("SUPPORTED_RELATION")
    assert cue_protocol_errors(inputs(), original)
    assert original["p:b:s1:discourse"]["classification"] == "SUPPORTED_RELATION"


def test_protocol_repair_keeps_model_uncertainty_instead_of_writing_a_scientific_label(tmp_path):
    reviewer = ProtocolIndependentCoveragePredictor(tmp_path)
    calls = []
    outputs = [decision("SUPPORTED_RELATION"), decision("AMBIGUOUS")]

    def predict(**values):
        calls.append(values)
        output = outputs[len(calls) - 1]
        return dspy.Prediction(cue_resolutions={key: CueValue.model_validate(value)
                                               for key, value in output.items()})

    final, attempts = reviewer._bounded("cues", predict, inputs(),
                                        "cue_resolutions", cue_protocol_errors)
    assert final == outputs[1]
    assert attempts[0]["output"] == outputs[0]
    assert attempts[1]["protocol_errors"] == []
    assert calls[0]["protocol_repair_feedback"] == ""
    assert "p:b:s1:discourse" in calls[1]["protocol_repair_feedback"]
    assert "draft_graph" not in calls[1] and "plan" not in calls[1]


def test_persistent_invalid_independent_output_stops_after_three_preserved_attempts(tmp_path: Path):
    reviewer = ProtocolIndependentCoveragePredictor(tmp_path)
    count = 0

    def predict(**values):
        nonlocal count
        count += 1
        return dspy.Prediction(cue_resolutions={key: CueValue.model_validate(value)
                                               for key, value in decision("SUPPORTED_RELATION").items()})

    with pytest.raises(SourceContractError, match="exhausted bounded protocol repair"):
        reviewer._bounded("cues", predict, inputs(), "cue_resolutions", cue_protocol_errors)
    assert count == 3
    failures = list((tmp_path / "independent-coverage-failures").glob("*.json"))
    assert len(failures) == 3
    assert all(json.loads(path.read_text(encoding="utf-8"))["output"] == decision("SUPPORTED_RELATION")
               for path in failures)
