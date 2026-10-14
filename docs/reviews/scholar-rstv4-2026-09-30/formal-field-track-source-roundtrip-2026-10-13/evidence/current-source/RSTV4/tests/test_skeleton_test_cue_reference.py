"""Scientific-source boundaries and immutable compile safeguards, without network calls."""
from __future__ import annotations

import copy
import json

import pytest
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_cue_diagnosis import partition_identity, validate_cue_partition
from rstv4.skeleton_test_cue_reference import TestSourceCueRegistry as SourceCueRegistry


@pytest.fixture
def source_case():
    claims = [{"reference_id": "r0", "source_span_ids": ["b:s1"]},
              {"reference_id": "r1", "source_span_ids": ["b:s2"]}]
    inputs = {"source_cue": json.dumps({"cue_id": "b:s2:discourse", "source_span_id": "b:s2"}),
              "reference_claims": json.dumps(claims),
              "source_blocks": json.dumps([{"source_spans": [{"span_id": "b:s1"}, {"span_id": "b:s2"}]}])}
    output = {"cue_id": "b:s2:discourse", "classification": "INTER_CLAIM_RELATION",
              "first_proposition": "Costs must decline.", "second_proposition": "Costs are low at this site.",
              "first_reference_id": "r0", "second_reference_id": "r1",
              "first_evidence_span_ids": ["b:s1"], "second_evidence_span_ids": ["b:s2"],
              "relation": "Contrast", "rationale": "The two source propositions explicitly compare different economic conditions.",
              "uncertainty": "Uncalibrated model judgment."}
    return inputs, output


@pytest.mark.parametrize("field,value", [
    ("cue_id", "other"), ("first_reference_id", "absent"),
    ("first_evidence_span_ids", ["b:s2"]), ("second_evidence_span_ids", ["invented"]),
    ("relation", "UNKNOWN"), ("second_reference_id", "r0"),
    ("classification", "WITHIN_ONE_CLAIM"),
])
def test_source_partition_rejects_wrong_identity_partition_or_endpoint(source_case, field, value):
    inputs, output = source_case
    output[field] = value
    with pytest.raises(SourceContractError):
        validate_cue_partition(inputs, output)


def test_unresolved_source_decision_is_retained_without_forced_edge(source_case):
    inputs, output = source_case
    output.update(classification="UNRESOLVED", relation=None, uncertainty="The antecedent is ambiguous.")
    original = copy.deepcopy(output)
    assert validate_cue_partition(inputs, output) == original
    assert output == original


def test_independent_endpoint_disagreement_does_not_become_agreement(source_case):
    _, output = source_case
    other = {**output, "relation": "Elaboration"}
    assert partition_identity(other) != partition_identity(output)
    assert output["relation"] == "Contrast"


@pytest.mark.parametrize("contamination", ["heldout", "digest"])
def test_test_only_registry_rejects_changed_or_contaminated_compile(tmp_path, contamination):
    instructions = {"layer1": "Original frozen instruction"}
    record = {"instructions": instructions, "instruction_digest": digest(instructions),
              "test_papers_accessed_during_compile": 0}
    if contamination == "heldout":
        record["test_papers_accessed_during_compile"] = 1
    else:
        record["instruction_digest"] = "changed"
    with pytest.raises(SourceContractError):
        SourceCueRegistry(tmp_path, compile_record=record, seed_reports=[])


def test_frozen_test_successor_cannot_start_optimization():
    from rstv4.skeleton_mapped_experiment_v19 import FrozenCompileTestExperiment

    # No constructor, corpus or model call: this capability itself is forbidden.
    instance = object.__new__(FrozenCompileTestExperiment)
    with pytest.raises(RuntimeError, match="cannot compile"):
        instance.optimize()
