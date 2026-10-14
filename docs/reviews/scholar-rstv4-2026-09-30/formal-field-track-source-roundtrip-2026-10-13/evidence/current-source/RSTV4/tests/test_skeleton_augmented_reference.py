from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_augmented_reference import parent_covers_additions
from rstv4.skeleton_contract import digest


@pytest.mark.parametrize("defect", [None, "missing", "rationale", "evidence", "claim", "role", "candidate"])
def test_source_parent_eligibility_requires_complete_unchanged_addition_and_source(defect):
    inputs = {"document_context": "Original source", "source_blocks": "[]"}
    base = {"claims": [{"reference_id": "r0", "quote": "Actual source assertion."}],
            "roles": [{"block_id": "b0", "role": "METHOD"}], "relations": []}
    edge = {"source_reference_id": "r0", "target_reference_id": "r1", "relation": "Parallel",
            "rationale": "Exact independently reviewed source coordination.",
            "source_evidence_span_ids": ["b0:s1"], "target_evidence_span_ids": ["b1:s1"]}
    ledger = [{"edge": copy.deepcopy(edge)}]
    parent = {"inputs_digest": digest(inputs), "candidate_access": False,
              "reference": {**copy.deepcopy(base), "relations": [edge]}}
    if defect == "missing":
        parent["reference"]["relations"] = []
    elif defect == "rationale":
        edge["rationale"] = "A different source interpretation with the same endpoint/type tuple."
    elif defect == "evidence":
        edge["target_evidence_span_ids"] = ["b2:s1"]
    elif defect == "claim":
        parent["reference"]["claims"][0]["quote"] = "A changed quotation."
    elif defect == "role":
        parent["reference"]["roles"][0]["role"] = "RESULTS"
    elif defect == "candidate":
        parent["candidate_access"] = True
    assert parent_covers_additions(parent, inputs, base, ledger) is (defect is None)
