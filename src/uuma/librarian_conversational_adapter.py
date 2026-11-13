"""Conversational Source Adapter for Librarian LSIP.

Handles conversational sources:
- Antigravity sessions (transcript.jsonl)
- Codex rollouts (rollout-*.jsonl)
- Hermes agent state messages (state.db messages table)

Includes episode/task segmentation, anti-hallucination evidence verification,
and structured fact/decision extraction with exact quote grounding.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .librarian_adapter_base import (
    AssertionStatus,
    CandidateEvidence,
    CandidateRecord,
    LibrarianDeterministicAdapter,
    MemoryCategory,
    PrivacyTier,
)


@dataclass
class ConversationTurn:
    """A single turn in a conversational interaction."""
    role: str  # 'user' | 'assistant' | 'system' | 'tool'
    content: str
    ordinal: int
    timestamp: str = ""
    locator: str = ""


@dataclass
class ConversationEpisode:
    """A coherent conversational episode (e.g. user prompt to completed task)."""
    episode_id: str
    title: str
    turns: list[ConversationTurn] = field(default_factory=list)
    raw_text: str = ""
    source_ref: str = ""
    actor: str = "user"


def verify_evidence_against_text(evidence: CandidateEvidence, raw_text: str) -> bool:
    """Anti-hallucination verification: Ensure exact_quote is a verbatim substring of raw_text.

    Computes and verifies the SHA-256 hash of the exact quote.
    """
    if not evidence.exact_quote or len(evidence.exact_quote.strip()) < 3:
        return False

    quote = evidence.exact_quote.strip()
    # Check verbatim substring (or normalized space substring)
    if quote not in raw_text:
        # Try normalizing whitespace
        norm_quote = " ".join(quote.split())
        norm_text = " ".join(raw_text.split())
        if norm_quote not in norm_text:
            return False

    # Check hash integrity
    computed_hash = hashlib.sha256(evidence.exact_quote.encode("utf-8")).hexdigest()
    return not (evidence.quote_hash and evidence.quote_hash != computed_hash)


def segment_antigravity_transcript(transcript_content: str, source_ref: str = "") -> list[ConversationEpisode]:
    """Parse Antigravity transcript.jsonl into coherent task episodes."""
    episodes: list[ConversationEpisode] = []
    current_turns: list[ConversationTurn] = []
    current_title = "Antigravity Task"
    episode_idx = 0

    lines = transcript_content.strip().splitlines()
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        step_idx = entry.get("step_index", idx)
        src = entry.get("source", "")
        entry_type = entry.get("type", "")
        content = entry.get("content", "")
        created_at = entry.get("created_at", "")

        # A new USER_INPUT starts a new episode if we already have turns
        if entry_type == "USER_INPUT" and src == "USER_EXPLICIT":
            if current_turns:
                ep_text = "\n".join(f"[{t.role}]: {t.content}" for t in current_turns)
                ep_id = f"ep_agy_{episode_idx}_{hashlib.sha256(ep_text[:100].encode()).hexdigest()[:8]}"
                episodes.append(ConversationEpisode(
                    episode_id=ep_id,
                    title=current_title,
                    turns=list(current_turns),
                    raw_text=ep_text,
                    source_ref=source_ref,
                ))
                current_turns.clear()
                episode_idx += 1

            # Extract user request clean snippet as title
            clean_user = content.split("</USER_REQUEST>")[0].replace("<USER_REQUEST>", "").strip()
            first_line = clean_user.splitlines()[0] if clean_user.splitlines() else "User Task"
            current_title = (first_line[:60] + "...") if len(first_line) > 60 else first_line

            current_turns.append(ConversationTurn(
                role="user",
                content=clean_user,
                ordinal=step_idx,
                timestamp=created_at,
                locator=f"step:{step_idx}",
            ))
        elif entry_type == "PLANNER_RESPONSE":
            thinking = entry.get("thinking", "")
            turn_text = content
            if thinking:
                turn_text = f"[Thinking]: {thinking}\n{content}".strip()
            current_turns.append(ConversationTurn(
                role="assistant",
                content=turn_text,
                ordinal=step_idx,
                timestamp=created_at,
                locator=f"step:{step_idx}",
            ))
        else:
            # Generic tool execution or system message
            if content:
                current_turns.append(ConversationTurn(
                    role="tool",
                    content=content[:500],
                    ordinal=step_idx,
                    timestamp=created_at,
                    locator=f"step:{step_idx}",
                ))

    # Append trailing episode
    if current_turns:
        ep_text = "\n".join(f"[{t.role}]: {t.content}" for t in current_turns)
        ep_id = f"ep_agy_{episode_idx}_{hashlib.sha256(ep_text[:100].encode()).hexdigest()[:8]}"
        episodes.append(ConversationEpisode(
            episode_id=ep_id,
            title=current_title,
            turns=list(current_turns),
            raw_text=ep_text,
            source_ref=source_ref,
        ))

    return episodes


def segment_codex_rollout(rollout_content: str, source_ref: str = "") -> list[ConversationEpisode]:
    """Parse Codex rollout-*.jsonl into coherent episodes."""
    episodes: list[ConversationEpisode] = []
    current_turns: list[ConversationTurn] = []
    current_title = "Codex Task"
    episode_idx = 0

    lines = rollout_content.strip().splitlines()
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        ordinal = entry.get("ordinal", idx)
        entry_type = entry.get("type", "")
        payload = entry.get("payload", {})
        timestamp = entry.get("timestamp", "")

        role = ""
        msg_text = ""

        if entry_type == "response_item":
            item_type = payload.get("type", "")
            if item_type == "message":
                role = payload.get("role", "")
                content_items = payload.get("content", [])
                if isinstance(content_items, list):
                    msg_text = "\n".join(
                        c.get("text", "") for c in content_items if isinstance(c, dict) and "text" in c
                    ).strip()
                elif isinstance(content_items, str):
                    msg_text = content_items.strip()
        elif entry_type == "user_msg":
            role = "user"
            msg_text = payload.get("text", "").strip()
        elif entry_type == "agent_msg":
            role = "assistant"
            msg_text = payload.get("text", "").strip()

        if role == "user" and msg_text:
            if current_turns:
                ep_text = "\n".join(f"[{t.role}]: {t.content}" for t in current_turns)
                ep_id = f"ep_codex_{episode_idx}_{hashlib.sha256(ep_text[:100].encode()).hexdigest()[:8]}"
                episodes.append(ConversationEpisode(
                    episode_id=ep_id,
                    title=current_title,
                    turns=list(current_turns),
                    raw_text=ep_text,
                    source_ref=source_ref,
                ))
                current_turns.clear()
                episode_idx += 1

            first_line = msg_text.splitlines()[0] if msg_text.splitlines() else "Codex Task"
            current_title = (first_line[:60] + "...") if len(first_line) > 60 else first_line

            current_turns.append(ConversationTurn(
                role="user",
                content=msg_text,
                ordinal=ordinal,
                timestamp=timestamp,
                locator=f"ordinal:{ordinal}",
            ))
        elif role == "assistant" and msg_text:
            current_turns.append(ConversationTurn(
                role="assistant",
                content=msg_text,
                ordinal=ordinal,
                timestamp=timestamp,
                locator=f"ordinal:{ordinal}",
            ))
        elif entry_type == "event_msg":
            ev_type = payload.get("type", "")
            if ev_type in ("task_started", "task_completed"):
                current_turns.append(ConversationTurn(
                    role="system",
                    content=f"Event: {ev_type}",
                    ordinal=ordinal,
                    timestamp=timestamp,
                    locator=f"ordinal:{ordinal}",
                ))

    if current_turns:
        ep_text = "\n".join(f"[{t.role}]: {t.content}" for t in current_turns)
        ep_id = f"ep_codex_{episode_idx}_{hashlib.sha256(ep_text[:100].encode()).hexdigest()[:8]}"
        episodes.append(ConversationEpisode(
            episode_id=ep_id,
            title=current_title,
            turns=list(current_turns),
            raw_text=ep_text,
            source_ref=source_ref,
        ))

    return episodes


class ConversationalSourceAdapter(LibrarianDeterministicAdapter):
    """Adapter for conversational sources (Antigravity, Codex, Hermes) with anti-hallucination evidence gate."""

    def __init__(
        self,
        source_id: str,
        default_category: MemoryCategory = "Experience",
        privacy_tier: PrivacyTier = "internal",
        extractor_fn: Callable[[ConversationEpisode], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._source_id = source_id
        self._category = default_category
        self._privacy_tier = privacy_tier
        self._extractor_fn = extractor_fn or self._default_pattern_extractor

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def default_category(self) -> MemoryCategory:
        return self._category

    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        """Extract verified semantic records from a transcript or rollout file.

        `source_input` may be a file Path, str content, or tuple (content, filename).
        """
        source_ref = ""
        content = ""

        if isinstance(source_input, Path):
            source_ref = str(source_input)
            content = source_input.read_text(encoding="utf-8", errors="replace")
        elif isinstance(source_input, tuple):
            content, source_ref = source_input
        else:
            content = str(source_input)
            source_ref = kwargs.get("source_ref", f"{self._source_id}:stream")

        # 1. Segment into episodes based on source format
        if "codex" in self._source_id:
            episodes = segment_codex_rollout(content, source_ref=source_ref)
        else:
            episodes = segment_antigravity_transcript(content, source_ref=source_ref)

        results: list[CandidateRecord] = []

        # 2. Extract and verify candidate records for each episode
        for ep in episodes:
            raw_claims = self._extractor_fn(ep)
            for idx, item in enumerate(raw_claims):
                exact_quote = item.get("exact_quote", "").strip()
                locator_type = item.get("locator_type", "jsonl_line")
                locator_value = item.get("locator_value", f"ep:{ep.episode_id}")

                evidence = CandidateEvidence(
                    locator_type=locator_type,
                    locator_value=locator_value,
                    exact_quote=exact_quote,
                )

                # 3. Anti-Hallucination Gate: MUST verify verbatim against raw episode text
                if not verify_evidence_against_text(evidence, ep.raw_text):
                    continue  # Reject hallucinated or unmatched quote!

                category: MemoryCategory = item.get("category", self._category)
                status: AssertionStatus = item.get("assertion_status", "confirmed")
                project = item.get("project", "unassigned")
                title = item.get("title", ep.title)
                summary = item.get("summary", title)
                full_content = item.get("full_content", summary)
                entities = item.get("entities", [self._source_id])

                rec_id = f"rec_{self._source_id}_{ep.episode_id}_{idx}"
                results.append(CandidateRecord(
                    record_id=rec_id,
                    version_id="v1",
                    source_id=self._source_id,
                    category=category,
                    project=project,
                    title=title,
                    summary=summary,
                    full_content=full_content,
                    original_status="captured",
                    original_ref=f"{source_ref}#{evidence.locator_value}",
                    assertion_status=status,
                    privacy_tier=self._privacy_tier,
                    readers=["librarian", "orchestrator"],
                    evidence=[evidence],
                    entities=entities,
                ))

        return results

    def _default_pattern_extractor(self, episode: ConversationEpisode) -> list[dict[str, Any]]:
        """Fallback deterministic extractor identifying high-value quotes from turns."""
        claims: list[dict[str, Any]] = []

        # Look for assistant resolutions, decisions, or fixes
        for turn in episode.turns:
            if turn.role != "assistant" or not turn.content:
                continue

            # Look for lines indicating a resolution or key fact
            lines = [ln.strip() for ln in turn.content.splitlines() if ln.strip()]
            for line in lines:
                lower = line.lower()
                if (
                    any(kw in lower for kw in ("fix", "solution", "decided", "decision", "implemented", "resolved"))
                    and len(line) >= 15
                ):
                    claims.append({
                        "title": f"Resolution in {episode.title[:40]}",
                        "summary": line[:150],
                        "full_content": f"### Context\n{episode.title}\n\n### Finding\n{line}",
                        "category": "Experience" if "fix" in lower or "resolved" in lower else "Decision",
                        "assertion_status": "confirmed",
                        "exact_quote": line,
                        "locator_type": "jsonl_turn",
                        "locator_value": turn.locator or f"ordinal:{turn.ordinal}",
                        "entities": [self._source_id],
                    })
                    break

        # If no explicit pattern match, but episode has substantial turns, ground on first user request
        if not claims and episode.turns:
            user_turn = next((t for t in episode.turns if t.role == "user" and len(t.content) >= 10), None)
            if user_turn:
                quote = user_turn.content.strip().splitlines()[0]
                if len(quote) >= 10:
                    claims.append({
                        "title": f"Interaction: {episode.title[:50]}",
                        "summary": quote[:150],
                        "full_content": f"### User Task\n{quote}",
                        "category": "History",
                        "assertion_status": "confirmed",
                        "exact_quote": quote,
                        "locator_type": "jsonl_turn",
                        "locator_value": user_turn.locator or f"ordinal:{user_turn.ordinal}",
                        "entities": [self._source_id],
                    })

        return claims
