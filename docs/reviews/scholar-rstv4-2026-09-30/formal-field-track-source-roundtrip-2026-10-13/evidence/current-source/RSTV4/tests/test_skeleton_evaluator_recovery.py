from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_evaluator_recovery import alias_candidate, unalias_review


def candidate() -> dict:
    return {
        "block_atoms": [{"block_id": "b", "atoms": [
            {"atom_id": "paper:long:b:a1", "statement": "Cost is conditional on scenario A.",
             "quote": "Cost is conditional on scenario A.", "source_span_ids": ["b:s1"]},
            {"atom_id": "paper:long:b:a2", "statement": "Authors are Alice and Bob.",
             "quote": "Authors are Alice and Bob.", "source_span_ids": ["b:s2"]},
        ]}],
        "intents": [{"atom_id": "paper:long:b:a1", "primary": "Objective_Finding"},
                    {"atom_id": "paper:long:b:a2", "primary": "Formal"}],
        "relations": [{"source_id": "paper:long:b:a1", "target_id": "paper:long:b:a2",
                       "relation": "Support"}],
        "roles": [{"block_id": "b", "role": "Result_Performance"}],
    }


def test_aliases_are_bijective_and_change_only_identifiers() -> None:
    original = candidate()
    before = copy.deepcopy(original)
    encoded, aliases = alias_candidate(original)
    assert original == before
    assert aliases == {"c0": "paper:long:b:a1", "c1": "paper:long:b:a2"}
    assert encoded["block_atoms"][0]["atoms"][0]["statement"] == original["block_atoms"][0]["atoms"][0]["statement"]
    assert encoded["block_atoms"][0]["atoms"][0]["source_span_ids"] == ["b:s1"]
    assert encoded["relations"][0]["source_id"] == "c0"
    assert encoded["intents"][1]["atom_id"] == "c1"
    assert encoded["roles"] == original["roles"]
    review = {"matches": [{"reference_id": "r1", "atom_id": "c0"},
                          {"reference_id": "r2", "atom_id": None}],
              "atom_verdicts": [{"atom_id": "c1", "verdict": "SUPPORTED"}]}
    decoded = unalias_review(review, aliases)
    assert decoded["matches"][0]["atom_id"] == "paper:long:b:a1"
    assert decoded["matches"][1]["atom_id"] is None
    assert decoded["atom_verdicts"][0]["atom_id"] == "paper:long:b:a2"


def test_alias_conversion_never_guesses_an_invented_identifier() -> None:
    _, aliases = alias_candidate(candidate())
    with pytest.raises(SourceContractError, match="invented"):
        unalias_review({"matches": [{"atom_id": "c99"}], "atom_verdicts": []}, aliases)


def test_ambiguous_or_dangling_candidate_identifiers_are_rejected() -> None:
    value = candidate()
    value["block_atoms"][0]["atoms"][1]["atom_id"] = "paper:long:b:a1"
    with pytest.raises(SourceContractError, match="duplicate"):
        alias_candidate(value)
    value = candidate()
    value["relations"][0]["target_id"] = "missing"
    with pytest.raises(SourceContractError, match="absent"):
        alias_candidate(value)
