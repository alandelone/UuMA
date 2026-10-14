from __future__ import annotations

import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_graph_reference import (
    alias_claims,
    discourse_cues,
    restore_graph,
    validate_graph,
)
from rstv4.skeleton_mapped_graph_v2 import mapped_graph, restore_mapped_graph
from test_skeleton_graph_reference import source_case


def test_cue_explanations_and_claim_order_survive_sorted_json_serialization():
    block, reference, graph = source_case()
    graph["cue_resolutions"][0]["relation_keys"][0]["rationale"] = "This is the separate explanation of the explicit discourse cue."
    graph["connections"].reverse()
    _, mapping = alias_claims(reference["claims"])
    aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
    encoded = json.loads(json.dumps(mapped_graph(aliased), sort_keys=True))
    restored = restore_mapped_graph(encoded, mapping, discourse_cues([block]))
    assert restored == graph
    assert validate_graph(reference, [block], discourse_cues([block]), restored)


@pytest.mark.parametrize("mutation", ["unknown_explanation", "missing_explanation", "duplicated_order"])
def test_lossless_fields_cannot_hide_missing_or_invented_graph_records(mutation):
    block, reference, graph = source_case()
    _, mapping = alias_claims(reference["claims"])
    aliased = restore_graph(graph, {original: alias for alias, original in mapping.items()})
    encoded = mapped_graph(aliased)
    cue = next(iter(encoded["cue_resolutions"].values()))
    if mutation == "unknown_explanation":
        cue["relation_rationales"]["e9"] = "An invented edge explanation."
    elif mutation == "missing_explanation":
        cue["relation_ids"].append("e9")
    else:
        encoded["connection_order"] = ["r0", "r0"]
    with pytest.raises(SourceContractError):
        restore_mapped_graph(encoded, mapping, discourse_cues([block]))

