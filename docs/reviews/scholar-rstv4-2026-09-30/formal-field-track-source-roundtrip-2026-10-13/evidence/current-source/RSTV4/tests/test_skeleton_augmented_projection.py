from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_augmented_reference_v2 import parent_covers_additions
from rstv4.skeleton_augmented_reference_v3 import (
    parent_covers_additions as retention_covers_additions,
)
from rstv4.skeleton_contract import digest
from rstv4.skeleton_experiment import ReferenceRelation


@pytest.mark.parametrize("defect", [None, "canonical_missing", "full_missing", "rationale",
                                    "evidence", "claim", "role", "candidate"])
@pytest.mark.parametrize("predicate", [parent_covers_additions, retention_covers_additions])
def test_augmented_parent_requires_exact_canonical_and_full_graph_projection(defect, predicate):
    inputs = {"document_context": "Original source", "source_blocks": "[]"}
    base = {"claims": [{"reference_id": "r0", "quote": "Actual source assertion."}],
            "roles": [{"block_id": "b0", "role": "METHOD"}], "relations": []}
    edge = {"source_reference_id": "r0", "target_reference_id": "r1", "relation": "Parallel",
            "rationale": "Exact independently reviewed source coordination.",
            "source_evidence_span_ids": ["b0:s1"], "target_evidence_span_ids": ["b1:s1"]}
    ledger = [{"edge": copy.deepcopy(edge)}]
    parent = {"inputs_digest": digest(inputs), "candidate_access": False,
              "reference": {**copy.deepcopy(base), "relations": [
                  {key: edge[key] for key in ReferenceRelation.model_fields}]},
              "graph_review": {"connections": [{"outgoing_relations": [edge]}]}}
    if defect == "canonical_missing":
        parent["reference"]["relations"] = []
    elif defect == "full_missing":
        parent["graph_review"]["connections"] = []
    elif defect == "rationale":
        edge["rationale"] = "A changed explanation for the same endpoint/type tuple."
    elif defect == "evidence":
        edge["target_evidence_span_ids"] = ["b2:s1"]
    elif defect == "claim":
        parent["reference"]["claims"][0]["quote"] = "A changed quotation."
    elif defect == "role":
        parent["reference"]["roles"][0]["role"] = "RESULTS"
    elif defect == "candidate":
        parent["candidate_access"] = True
    assert predicate(parent, inputs, base, ledger) is (defect is None)
