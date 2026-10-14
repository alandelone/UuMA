from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

import dspy
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import ReceiptLM, write_json
from rstv4.skeleton_experiment import (
    ClaimMatch,
    Experiment,
    ReferenceClaim,
    aggregate_reports,
    compose_guidance,
    failed_assessment,
    score_assessment,
)


def reference() -> dict:
    return {
        "claims": [{"reference_id": "r1", "block_id": "b", "intent": "Objective_Finding"}],
        "relations": [], "roles": [{"block_id": "b", "role": "Result_Performance"}],
    }


def candidate() -> dict:
    return {
        "block_atoms": [{"block_id": "b", "atoms": [{"atom_id": "b:a1"}]}],
        "relations": [], "intents": [{"atom_id": "b:a1", "primary": "Objective_Finding"}],
        "roles": [{"block_id": "b", "role": "Result_Performance"}],
    }


def assessment() -> dict:
    return {
        "matches": [{"reference_id": "r1", "atom_id": "b:a1", "meaning_preserved": True,
                     "qualifications_preserved": True}],
        "relation_matches": [], "unsupported_atom_ids": [], "unsupported_relation_indices": [],
        "reference_defects": [],
    }


def test_failed_windows_remain_in_semantic_denominators() -> None:
    successful = score_assessment(reference(), candidate(), assessment())
    report = aggregate_reports([successful, failed_assessment(reference(), "omitted block")])
    assert report["layer1_coverage"] == 0.5
    assert report["qualification_recall"] == 0.5
    assert report["layer4_accuracy"] == 0.5
    assert report["contract_failures"] == 1
    assert not report["semantic_gate_passed_against_model_reference"]


def test_unsupported_match_does_not_count_as_coverage() -> None:
    value = assessment()
    value["unsupported_atom_ids"] = ["b:a1"]
    report = score_assessment(reference(), candidate(), value)
    assert report["layer1_coverage"] == 0.0
    assert report["unsupported_claim_rate"] == 1.0


def test_missing_reference_decisions_cannot_pass_the_critic_contract() -> None:
    value = assessment()
    value["matches"] = []
    with pytest.raises(SourceContractError, match="every reference claim"):
        score_assessment(reference(), candidate(), value)


def test_critic_cannot_claim_a_match_to_an_invented_atom() -> None:
    value = assessment()
    value["matches"][0]["atom_id"] = "made-up"
    with pytest.raises(SourceContractError, match="absent candidate atom"):
        score_assessment(reference(), candidate(), value)


def test_conditions_are_scored_separately_from_claim_coverage() -> None:
    value = assessment()
    value["matches"][0]["qualifications_preserved"] = False
    report = score_assessment(reference(), candidate(), value)
    assert report["layer1_coverage"] == 1.0
    assert report["qualification_recall"] == 0.0


def test_reference_annotator_schema_requires_source_ids() -> None:
    assert "source_span_ids" in ReferenceClaim.model_json_schema()["required"]


def test_reflection_preserves_the_extraction_task_and_rejects_meta_chat() -> None:
    base = "Split source-supported claims. Retain every condition and source ID."
    result = compose_guidance(base, ["Preserve may and negation explicitly in every proposition."])
    assert result.startswith(base + "\n\n")
    with pytest.raises(SourceContractError, match="direct extraction rules"):
        compose_guidance(base, ["Please provide the next source block so I can help you."])


def critic_prediction(atom_id: str) -> dspy.Prediction:
    return dspy.Prediction(
        matches=[ClaimMatch(reference_id="r1", atom_id=atom_id, meaning_preserved=True,
                            qualifications_preserved=True, rationale="source comparison")],
        relation_matches=[], unsupported_atom_ids=[], unsupported_relation_indices=[],
        reference_defects=[], feedback="source checked",
    )


def test_critic_repair_receives_the_bad_id_and_real_candidates(tmp_path: Path) -> None:
    experiment = object.__new__(Experiment)
    experiment.output, experiment.teacher = tmp_path, None
    calls = []

    def assessor(**kwargs):
        calls.append(kwargs["repair_feedback"])
        return critic_prediction("b:a99" if len(calls) == 1 else "b:a1")

    experiment.assessor = assessor
    report = experiment.assess({}, reference(), candidate())
    assert report["score"] == 1.0
    assert "b:a99" in calls[1] and "b:a1" in calls[1]
    assert "COMPLETE evaluation" in calls[1]


def test_unrepaired_judge_failure_is_separate_and_keeps_uncertainty(tmp_path: Path) -> None:
    experiment = object.__new__(Experiment)
    experiment.output, experiment.teacher = tmp_path, None
    experiment.assessor = lambda **kwargs: critic_prediction("b:a99")
    report = experiment.assess({}, reference(), candidate())
    summary = aggregate_reports([report])
    assert summary["candidate_contract_failures"] == 0
    assert summary["evaluation_contract_failures"] == 1
    assert summary["layer1_coverage"] == 0.0
    assert summary["unassessed_atoms"] == 1
    assert summary["unsupported_claim_rate_upper_bound"] == 1.0
    assert not summary["semantic_gate_passed_against_model_reference"]


def test_resume_reads_the_original_durable_run_without_resubmitting(tmp_path: Path) -> None:
    lm = ReceiptLM("standard", tmp_path)
    write_json(tmp_path / "runs" / "key.json", {"id": "owned-run", "status": "running"})
    calls = []

    def request(path: str, body=None, **kwargs):
        calls.append((path, body))
        return {"id": "owned-run", "status": "completed", "attempts": 1,
                "response": {"model": "actual", "choices": []}}

    lm._request_json = request
    response = lm._durable_response("key", {"model": "standard"})
    assert calls == [("/runs/owned-run", None)]
    assert response["router"]["durable_run_id"] == "owned-run"
    assert "api_key" not in lm.dump_state()


def test_new_durable_request_uses_stable_idempotency_key(tmp_path: Path) -> None:
    lm = ReceiptLM("standard", tmp_path)
    calls = []

    def request(path: str, body=None, **kwargs):
        calls.append((path, body, kwargs))
        return {"id": "owned-run", "status": "completed", "attempts": 1,
                "response": {"model": "actual", "choices": []}}

    lm._request_json = request
    lm._durable_response("frozen-key", {"model": "standard", "messages": []})
    assert calls[0][2]["idempotency_key"] == "paperskeleton-frozen-key"
    assert calls[0][1]["max_attempts"] == 3
    assert calls[1][0] == "/runs/owned-run"
