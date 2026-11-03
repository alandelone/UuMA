import io
import json

import pytest

from uuma.wisdom_critic import WisdomCritic


def context():
    return {
        "question": "What pressure and interval does the software example require?",
        "answer": {"answer": "10 kPa at 5 second intervals.",
                   "citations": [{"source_id": "s1", "chunk_id": "c1"}]},
        "evidence": [{"ref": "c1", "text": "Software fixture: 10 kPa, interval 5 s.",
                      "source_id": "s1", "locator": "fixture://example", "location": "p1"}],
    }


def verdict(**changes):
    return {
        "verdict": "SUFFICIENT", "rationale": "Both requested settings are evidenced.",
        "requirements": [{"requirement": "pressure and interval", "status": "covered",
                          "supporting_refs": ["c1"]}],
        "remaining_questions": [], "material_conflicts_resolved": True,
    } | changes


def response(monkeypatch, value, finish="stop"):
    calls = []

    def request(req, **kwargs):
        calls.append(json.loads(req.data))
        return io.BytesIO(json.dumps({
            "model": "gemini-4-argon", "id": "critic-1", "usage": {"total_tokens": 123},
            "choices": [{"message": {"content": json.dumps(value)}, "finish_reason": finish}],
        }).encode())

    monkeypatch.setattr("uuma.wisdom_critic.urlopen", request)
    return calls


def assess(critic=None, data=None, **budget):
    return (critic or WisdomCritic(base_url="http://example/v1")).assess(
        data or context(), **({"remaining_tokens": 50_000, "remaining_seconds": 30} | budget),
    )


def test_critic_audits_independent_model_and_evidenced_coverage(monkeypatch):
    calls = response(monkeypatch, verdict())
    receipt = assess()
    assert receipt["status"] == "REVIEWED" and receipt["verdict"] == "SUFFICIENT"
    assert receipt["actual_model"] == "gemini-4-argon"
    assert receipt["tokens_used"] == 123 and not receipt["usage_estimated"]
    assert receipt["evidence_refs"] == ["c1"]
    assert all(receipt[k] for k in ["input_sha256", "prompt_sha256", "output_sha256"])
    assert calls[0]["model"] == "complex" and calls[0]["max_tokens"] == 2048
    assert len(calls[0]["messages"]) == 2 and "tools" not in calls[0]


@pytest.mark.parametrize("change", [
    {"requirements": [{"requirement": "interval", "status": "covered",
                       "supporting_refs": ["invented"]}]},
    {"requirements": [{"requirement": "interval", "status": "partial",
                       "supporting_refs": ["c1"]}]},
    {"material_conflicts_resolved": False},
    {"remaining_questions": ["What is the interval?"]},
])
def test_critic_rejects_missing_conflicting_or_fabricated_coverage(monkeypatch, change):
    response(monkeypatch, verdict(**change))
    receipt = assess()
    assert receipt["verdict"] == "CONTINUE" and receipt["status"] == "UNAVAILABLE"
    assert receipt["tokens_used"] == 123


def test_critic_requires_current_answer_to_cite_evidence(monkeypatch):
    response(monkeypatch, verdict())
    data = context()
    data["answer"]["citations"] = []
    assert assess(data=data)["verdict"] == "CONTINUE"


def test_truncated_response_cannot_close_research(monkeypatch):
    response(monkeypatch, verdict(), finish="length")
    assert assess()["status"] == "UNAVAILABLE"


def test_unlocated_excerpt_cannot_certify_coverage(monkeypatch):
    response(monkeypatch, verdict())
    data = context()
    data["evidence"][0]["location"] = None
    receipt = assess(data=data)
    assert receipt["verdict"] == "CONTINUE"
    assert receipt["proposal"]["verdict"] == "SUFFICIENT"


def test_timeout_and_budget_limit_do_not_certify_completeness(monkeypatch):
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(True)
        raise TimeoutError("private connection detail")

    monkeypatch.setattr("uuma.wisdom_critic.urlopen", unavailable)
    receipt = assess()
    assert receipt["error_type"] == "TimeoutError" and receipt["verdict"] == "CONTINUE"
    assert "private connection" not in json.dumps(receipt) and receipt["tokens_used"] > 0
    assert assess(remaining_tokens=500)["status"] == "BUDGET_LIMIT"
    assert len(calls) == 1


def test_context_bounds_mark_omissions():
    data = context()
    data["evidence"] *= 100
    for item in data["evidence"]:
        item["text"] = "source " * 10_000
    packed = WisdomCritic._pack(data, 5000)
    assert packed["context_truncated"]
    assert len(json.dumps(packed, ensure_ascii=False)) < 5100
