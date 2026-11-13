"""Tests for BrainstormerAuditAdapter."""

from uuma.librarian_brainstormer_adapter import BrainstormerAuditAdapter


def test_brainstormer_audit_adapter_extraction() -> None:
    fake_state = {
        "project_id": "discussion_green_onion",
        "revision": 4,
        "objects": {
            "topic_01": {
                "id": "topic_01",
                "kind": "topic",
                "title": "Green Onion Farming Malaysia",
                "status": "ACTIVE",
            },
            "dec_01": {
                "id": "dec_01",
                "kind": "decision",
                "title": "Substrate Choice: Coco Peat",
                "rationale": "High water retention and local availability",
                "status": "APPROVED",
            },
            "cp_01": {
                "id": "cp_01",
                "kind": "checkpoint",
                "title": "Review nutrient requirements",
                "summary": "Assessed EC and pH thresholds",
                "status": "ARCHIVED",
            },
            "q_01": {
                "id": "q_01",
                "kind": "question",
                "title": "Optimal lighting cycle?",
                "status": "OPEN",
            },
        },
    }

    adapter = BrainstormerAuditAdapter()
    assert adapter.source_id == "brainstormer-structured-files"
    assert adapter.default_category == "Decision"

    records = adapter.extract(fake_state)
    assert len(records) == 4

    # Check approved decision
    r_dec = next(r for r in records if r.record_id == "brainstormer:decision:dec_01")
    assert r_dec.category == "Decision"
    assert r_dec.assertion_status == "confirmed"
    assert "Coco Peat" in r_dec.title
    assert r_dec.evidence[0].locator_value == "objects.dec_01"

    # Check checkpoint (history)
    r_cp = next(r for r in records if r.record_id == "brainstormer:checkpoint:cp_01")
    assert r_cp.category == "History"
    assert r_cp.assertion_status == "historical"

    # Check question (knowledge, proposed)
    r_q = next(r for r in records if r.record_id == "brainstormer:question:q_01")
    assert r_q.category == "Knowledge"
    assert r_q.assertion_status == "proposed"
