from __future__ import annotations

import json

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_context_reference import ContextSourceReferenceBuilder, citation_context
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_dspy import ReceiptLM
from test_skeleton_graph_reference import source_case


def test_context_uses_actual_ordered_spans_and_distinct_annotation_review(tmp_path, monkeypatch):
    block, reference, _ = source_case()
    contract = json.loads(citation_context(block))
    assert [item["span_id"] for item in contract["ordered_spans"]] == [
        span["span_id"] for span in block["source_spans"]
    ]
    calls = []

    def response(self, key, body):
        calls.append((key, body))
        result = {"claims": reference["claims"], "role": reference["roles"][0]}
        if "draft_reference" in body["messages"][1]["content"]:
            result["corrections"] = []
        return {"model": "gemini-3.1-pro", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": json.dumps(result)}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ReceiptLM, "_durable_response", response)
    builder = ContextSourceReferenceBuilder(tmp_path, actual_model="gemini-3.1-pro")
    builder.lm.excluded_routes = []
    assert builder.block("Development context", block) == reference
    assert len(calls) == 2 and calls[0][0] != calls[1][0]
    assert "citation_contract" in calls[0][1]["messages"][1]["content"]
    assert builder.block("Development context", block) == reference
    assert len(calls) == 2
    path = next((tmp_path / "blocks").glob("*.json"))
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["citation_contract_digest"] = "changed"
    path.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(SourceContractError, match="citation context changed"):
        builder.block("Development context", block)
