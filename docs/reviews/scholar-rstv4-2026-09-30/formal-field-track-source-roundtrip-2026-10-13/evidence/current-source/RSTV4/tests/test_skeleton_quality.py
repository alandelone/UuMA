from __future__ import annotations

import copy
from pathlib import Path

import pytest
from rstv4.paperpool_evaluation import evaluate_records
from rstv4.skeleton_audit import (
    RecordingGateway,
    diagnose_result,
    replay_native_handler,
    select_blocks,
)


@pytest.mark.parametrize("layer", [2, 3, 4])
def test_missing_reference_labels_cannot_measure_accuracy(layer: int) -> None:
    with pytest.raises(ValueError, match="requires a nonempty label"):
        evaluate_records([{
            "paper_id": "p1", "task": f"skeleton_layer_{layer}",
            "expected": {}, "prediction": {},
        }])


@pytest.mark.parametrize("layer", [2, 3, 4])
def test_missing_prediction_is_a_miss(layer: int) -> None:
    report = evaluate_records([{
        "paper_id": "p1", "task": f"skeleton_layer_{layer}",
        "expected": {"label": "Method"}, "prediction": {},
    }])
    metric = f"layer{layer}_" + ("accuracy" if layer == 4 else "macro_f1")
    assert report["metrics"][metric] == 0.0
    assert report["passed"] is False


@pytest.mark.parametrize("layer,key", [(2, "discourse_relation"), (3, "intent"), (4, "role")])
def test_native_classification_fields_are_scored(layer: int, key: str) -> None:
    report = evaluate_records([{
        "paper_id": "p1", "task": f"skeleton_layer_{layer}",
        "expected": {"label": "Method"}, "prediction": {key: "Method"},
    }])
    metric = f"layer{layer}_" + ("accuracy" if layer == 4 else "macro_f1")
    assert report["metrics"][metric] == 1.0


def test_conflicting_role_and_label_are_not_silently_selected() -> None:
    with pytest.raises(ValueError, match="Conflicting classification fields"):
        evaluate_records([{
            "paper_id": "p1", "task": "skeleton_layer_4",
            "expected": {"label": "Method"},
            "prediction": {"label": "Method", "role": "Conclusion"},
        }])


def test_missing_factual_reference_cannot_prove_layer1_coverage() -> None:
    with pytest.raises(ValueError, match="requires nonempty facts"):
        evaluate_records([{"paper_id": "p1", "task": "skeleton_layer_1"}])


def test_malformed_layer1_output_counts_as_zero_coverage() -> None:
    report = evaluate_records([{
        "paper_id": "p1", "task": "skeleton_layer_1",
        "expected": {"facts": ["The sample has 12 households."]},
        "prediction": {"facts": {"invented": "wrong container"}},
    }])
    assert report["metrics"]["layer1_coverage"] == 0.0


def test_native_replay_preserves_call_receipts_and_does_not_open_catalog(tmp_path: Path) -> None:
    class Gateway:
        def analyze(self, task: str, payload: dict) -> dict:
            return {
                "role": "Method",
                "_contract": {"actual_model": "fixture-model", "prompt_version": task},
            }

    blocks = [{
        "block_id": "b1", "page_number": 3, "section": "Method", "text": "Located evidence.",
    }]
    original = copy.deepcopy(blocks)
    journal = tmp_path / "calls.jsonl"
    first = replay_native_handler(blocks, RecordingGateway(Gateway(), journal))
    assert len(first["calls"]) == 4
    assert first["models"] == ["fixture-model"]
    assert first["units"][0]["page_number"] == 3
    assert blocks == original
    assert not (tmp_path / "data" / "catalog.db").exists()
    for call in first["calls"]:
        assert call["result"]["_contract"]["actual_model"] == "fixture-model"
    assert first["diagnostics"]["l4_receives_section"] is False
    second = replay_native_handler(blocks, RecordingGateway(Gateway(), journal))
    assert all(call["reused"] for call in second["calls"])
    assert len(journal.read_text(encoding="utf-8").splitlines()) == 4


def test_audit_sampling_is_bounded_and_keeps_source_locations() -> None:
    blocks = [{
        "sequence": index, "page_number": index + 1, "text": "x" * 300, "block_type": "TEXT",
    } for index in range(7)]
    selected = select_blocks(blocks, 3)
    assert [block["sequence"] for block in selected] == [0, 3, 6]
    assert [block["page_number"] for block in selected] == [1, 4, 7]


def test_audit_flags_nested_triplets_lost_by_canonical_publication() -> None:
    findings = diagnose_result([{
        "block_id": "b1",
        "layer1": {"propositions": [{"triplets": [
            {"subject": "storage", "predicate": "may improve", "object": "performance"},
            {"subject": "technology", "predicate": "can be explored", "object": None},
        ]}]},
        "layer4": {"role": "Future_Work"},
    }], [])
    losses = findings["nested_triplets_ignored_by_publication"]
    assert losses[0]["nested_valid_triplets"] == 1
    assert losses[0]["block_id"] == "b1"
