"""Unit tests for Conversational Source Adapter and Anti-Hallucination Gate."""

from __future__ import annotations

import json

from uuma.librarian_adapter_base import CandidateEvidence
from uuma.librarian_conversational_adapter import (
    ConversationalSourceAdapter,
    segment_antigravity_transcript,
    segment_codex_rollout,
    verify_evidence_against_text,
)


def test_verify_evidence_against_text_matches_and_rejects():
    raw = "The system was updated to support Gemini 3.8 Flash model via oauth."
    
    # Exact quote
    good_ev = CandidateEvidence(
        locator_type="text_slice",
        locator_value="char:0-68",
        exact_quote="Gemini 3.8 Flash model via oauth",
    )
    assert verify_evidence_against_text(good_ev, raw) is True

    # Hallucinated quote
    bad_ev = CandidateEvidence(
        locator_type="text_slice",
        locator_value="char:0-50",
        exact_quote="Claude 3.5 Sonnet model via api key",
    )
    assert verify_evidence_against_text(bad_ev, raw) is False

    # Empty quote
    empty_ev = CandidateEvidence(
        locator_type="text_slice",
        locator_value="char:0-0",
        exact_quote="  ",
    )
    assert verify_evidence_against_text(empty_ev, raw) is False


def test_segment_antigravity_transcript():
    sample_transcript = "\n".join([
        json.dumps({
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "content": "<USER_REQUEST>\nFix catalog backward compatibility\n</USER_REQUEST>",
            "created_at": "2026-11-12T10:00:00Z"
        }),
        json.dumps({
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "thinking": "We should keep catalog.json as a dual-write mirror.",
            "content": "Implemented dual write to librarian_semantic_catalog.json and catalog.json.",
            "created_at": "2026-11-12T10:01:00Z"
        }),
        json.dumps({
            "step_index": 2,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "content": "<USER_REQUEST>\nSecond task: inspect Yonc graph\n</USER_REQUEST>",
            "created_at": "2026-11-12T10:05:00Z"
        }),
    ])

    episodes = segment_antigravity_transcript(sample_transcript, source_ref="test_transcript.jsonl")
    assert len(episodes) == 2
    assert "Fix catalog" in episodes[0].title
    assert len(episodes[0].turns) == 2
    assert "Second task" in episodes[1].title


def test_segment_codex_rollout():
    sample_rollout = "\n".join([
        json.dumps({
            "type": "session_meta",
            "payload": {"session_id": "01a1cdb3-test", "cwd": "/repo"}
        }),
        json.dumps({
            "ordinal": 1,
            "type": "user_msg",
            "payload": {"text": "Refactor test suite for high speed"}
        }),
        json.dumps({
            "ordinal": 2,
            "type": "agent_msg",
            "payload": {"text": "Fixed: all tests run concurrently with pytest-xdist."}
        }),
    ])

    episodes = segment_codex_rollout(sample_rollout, source_ref="rollout.jsonl")
    assert len(episodes) == 1
    assert "Refactor test suite" in episodes[0].title
    assert len(episodes[0].turns) == 2


def test_conversational_adapter_extract_and_grounding():
    sample_rollout = "\n".join([
        json.dumps({
            "type": "session_meta",
            "payload": {"session_id": "01a1cdb3-test", "cwd": "/repo"}
        }),
        json.dumps({
            "ordinal": 1,
            "type": "user_msg",
            "payload": {"text": "Upgrade SQLite database to WAL mode"}
        }),
        json.dumps({
            "ordinal": 2,
            "type": "agent_msg",
            "payload": {"text": "Fixed: SQLite database enabled PRAGMA journal_mode=WAL successfully."}
        }),
    ])

    adapter = ConversationalSourceAdapter("codex-sessions", default_category="Experience")
    records = adapter.extract(sample_rollout, source_ref="rollout-test.jsonl")

    assert len(records) >= 1
    rec = records[0]
    assert rec.source_id == "codex-sessions"
    assert rec.category == "Experience"
    assert "Fixed: SQLite database enabled PRAGMA journal_mode=WAL" in rec.evidence[0].exact_quote
    assert rec.evidence[0].quote_hash != ""
