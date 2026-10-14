"""Source-located, backend-neutral PaperSkeleton extraction contract."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTEXT_VERSION = "document-window-v2"
CONTRACT_VERSION = "paperskeleton-required-source-spans-v4"

MacroRole = Literal[
    "Abstract", "Motivation_Intro", "Related_Work", "Core_Methodology",
    "Empirical_Experiment", "Result_Performance", "Deep_Discussion",
    "Global_Conclusion", "Front_Matter", "Acknowledgment", "Funding", "References", "UNKNOWN",
]
Intent = Literal[
    "Fact_Background", "Research_Gap", "Paper_Objective", "Proposed_Idea",
    "Method_Overview", "Method_Detail", "Method_Justification", "Evaluation_Metric",
    "Figure_Intro", "Objective_Finding", "Comparison", "Explanation", "Limitation",
    "Boundary_Condition", "Implication", "Conclusion", "Future_Work", "Formal", "UNKNOWN",
]
RelationType = Literal[
    "Cause", "Contrast", "Elaboration", "Support", "Condition", "Sequential",
    "Parallel", "Coreference", "Citation", "Topic_Shift", "UNKNOWN",
]


class ExtractionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Triplet(ExtractionRecord):
    subject: str
    predicate: str
    object: str


class ObjectAnchor(ExtractionRecord):
    kind: Literal["Figure", "Table", "Equation", "Citation"]
    label: str


class Atom(ExtractionRecord):
    atom_id: str = Field(description="Local identifier; canonical ID is assigned by the program")
    statement: str
    quote: str = Field(description="Verbatim, contiguous supporting text from this block")
    source_span_ids: list[str] = Field(description="REQUIRED consecutive source span IDs from this block")
    epistemic_status: Literal[
        "AUTHOR_REPORT", "AUTHOR_HYPOTHESIS", "AUTHOR_INTERPRETATION", "BACKGROUND", "UNKNOWN",
    ]
    qualifications: list[str] = Field(description="Conditions, uncertainty, negation, quantities/units")
    triplets: list[Triplet]
    objects: list[ObjectAnchor]


class BlockAtoms(ExtractionRecord):
    block_id: str
    atoms: list[Atom]


class DiscourseRelation(ExtractionRecord):
    source_id: str
    target_id: str
    relation: RelationType
    rationale: str


class BlockIntents(ExtractionRecord):
    atom_id: str
    primary: Intent
    secondary: list[Intent]
    rationale: str


class BlockRole(ExtractionRecord):
    block_id: str
    role: MacroRole
    confidence: float = Field(ge=0, le=1)
    rationale: str


class ArgumentLink(ExtractionRecord):
    source_id: str
    target_id: str
    relation: Literal["addresses", "evaluates", "reports", "interprets", "limits", "UNKNOWN"]
    rationale: str


class SourceContractError(ValueError):
    """The output cannot be tied to the supplied source; never silently publish it."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def normalized_text(text: str) -> str:
    # MinerU discretionary hyphens split words; retain raw text separately for provenance.
    text = re.sub("\u00ad\\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def located_span(source: str, quote: str) -> tuple[int, int] | None:
    """Find the quoted text after whitespace/discretionary-hyphen normalization."""
    normalized = normalized_text(source)
    needle = normalized_text(quote)
    start = normalized.find(needle) if needle else -1
    return None if start < 0 else (start, start + len(needle))


def quote_failure(source: str, quote: str, label: str) -> str:
    """Provide exact source for repair, without accepting a fuzzy or paraphrased citation."""
    normalized = normalized_text(source)
    needle = normalized_text(quote)
    anchor = difflib.SequenceMatcher(None, needle, normalized, autojunk=False).find_longest_match()
    start = max(0, anchor.b - anchor.a - 30)
    end = min(len(normalized), start + len(needle) + 100)
    return (
        f"Unlocated {label}. The citation must preserve ALL characters, including LaTeX and "
        "spacing around math punctuation. Quote received: " + repr(quote) +
        ". Nearby exact normalized source (select a contiguous excerpt from it): "
        + repr(normalized[start:end])
    )


def source_spans(block: dict[str, Any], *, max_chars: int = 550) -> list[dict[str, Any]]:
    """Index exact raw source slices; sentence/table boundaries improve citation selection."""
    text = block["text"]
    boundaries = {0, len(text)}
    for match in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9(])|(?<=</tr>)\s*", text):
        boundaries.add(match.end())
    ordered = sorted(boundaries)
    spans = []
    for start, end in pairwise(ordered):
        while start < end:
            stop = min(start + max_chars, end)
            if stop < end:
                space = text.rfind(" ", start + max_chars // 2, stop)
                if space > start:
                    stop = space + 1
            spans.append({
                "span_id": f"{block['block_id']}:s{len(spans) + 1}",
                "start": start, "end": stop, "text": text[start:stop],
            })
            start = stop
    return spans


def with_source_spans(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**block, "source_spans": source_spans(block)} for block in blocks]


def resolve_source_quote(block: dict[str, Any], ids: list[str]) -> str:
    spans = block.get("source_spans") or []
    by_id = {span["span_id"]: index for index, span in enumerate(spans)}
    if not ids or any(span_id not in by_id for span_id in ids):
        raise SourceContractError("Every proposition needs existing source span IDs in its own block")
    positions = [by_id[span_id] for span_id in ids]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise SourceContractError("Source span IDs must be unique, ordered and contiguous")
    return block["text"][spans[positions[0]]["start"]:spans[positions[-1]]["end"]]


def spans_for_existing_quote(block: dict[str, Any], quote: str) -> list[str]:
    """Migrate an already exact source quote; no fuzzy quote is accepted."""
    if located_span(block["text"], quote) is None:
        raise SourceContractError(quote_failure(block["text"], quote, "legacy quote"))
    spans = block["source_spans"]
    for size in range(1, len(spans) + 1):
        for start in range(len(spans) - size + 1):
            selected = spans[start:start + size]
            text = block["text"][selected[0]["start"]:selected[-1]["end"]]
            if located_span(text, quote) is not None:
                return [span["span_id"] for span in selected]
    raise SourceContractError("Existing quote cannot be mapped to indexed source spans")


def canonical_atoms(
    records: list[BlockAtoms], blocks: list[dict[str, Any]],
) -> list[BlockAtoms]:
    by_id = {block["block_id"]: block for block in blocks}
    ids = [record.block_id for record in records]
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise SourceContractError("L1 must account for every supplied block exactly once")
    ordered = {record.block_id: record for record in records}
    results = []
    for block in blocks:
        record = ordered[block["block_id"]].model_copy(deep=True)
        if (block.get("block_type", "TEXT") == "TEXT" and len(block["text"]) > 240
                and not record.atoms):
            raise SourceContractError(f"L1 omitted substantive block {record.block_id}")
        for index, atom in enumerate(record.atoms, 1):
            atom.atom_id = f"{record.block_id}:a{index}"
            if "source_spans" in block:
                try:
                    atom.quote = resolve_source_quote(block, atom.source_span_ids)
                except SourceContractError as exc:
                    available = [span["span_id"] for span in block["source_spans"]]
                    raise SourceContractError(
                        f"{atom.atom_id}: {exc}. Supplied IDs: {atom.source_span_ids!r}; "
                        f"available IDs in this block: {available!r}",
                    ) from exc
            if located_span(block["text"], atom.quote) is None:
                raise SourceContractError(quote_failure(block["text"], atom.quote, f"quote in {atom.atom_id}"))
            if not atom.statement.strip():
                raise SourceContractError(f"Empty proposition in {atom.atom_id}")
        results.append(record)
    return results


def validate_layers(
    atoms: list[BlockAtoms], relations: list[DiscourseRelation],
    intents: list[BlockIntents], roles: list[BlockRole], blocks: list[dict[str, Any]],
) -> None:
    ids = {atom.atom_id for block in atoms for atom in block.atoms}
    for relation in relations:
        if relation.source_id not in ids or relation.target_id not in ids:
            raise SourceContractError("L2 relation points to an unknown proposition")
        if relation.source_id == relation.target_id:
            raise SourceContractError("L2 cannot create a self relation")
    intent_ids = [intent.atom_id for intent in intents]
    if set(intent_ids) != ids or len(intent_ids) != len(ids):
        raise SourceContractError("L3 must give one primary intent per proposition")
    block_ids = {block["block_id"] for block in blocks}
    role_ids = [role.block_id for role in roles]
    if set(role_ids) != block_ids or len(role_ids) != len(block_ids):
        raise SourceContractError("L4 must give one macro role per supplied block")


def build_document_context(blocks: list[dict[str, Any]], title: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    previous = None
    for block in blocks:
        section = block.get("section")
        if section != previous and section:
            sections.append({
                "section": section, "first_block_id": block["block_id"],
                "page_number": block.get("page_number"),
            })
        previous = section
    return {"title": title, "document_outline": sections, "context_version": CONTEXT_VERSION}


def chunk_document(
    blocks: list[dict[str, Any]], *, max_chars: int = 6500, max_blocks: int = 12,
) -> list[list[dict[str, Any]]]:
    """Cover every block in order; long blocks keep located sub-block identities."""
    if max_chars < 500 or max_blocks < 1:
        raise ValueError("Invalid context chunk limits")
    expanded = []
    for block in blocks:
        text = block["text"]
        if len(text) <= max_chars:
            expanded.append(dict(block))
            continue
        offset = 0
        part = 1
        while offset < len(text):
            end = min(offset + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind(" ", offset + max_chars // 2, end)
                if boundary > offset:
                    end = boundary + 1
            expanded.append({
                **block, "block_id": f"{block['block_id']}:part{part}", "text": text[offset:end],
                "parent_block_id": block["block_id"], "source_char_start": offset,
                "source_char_end": end,
            })
            offset, part = end, part + 1
    chunks = []
    pending: list[dict[str, Any]] = []
    size = 0
    for block in expanded:
        if pending and (size + len(block["text"]) > max_chars or len(pending) >= max_blocks):
            chunks.append(pending)
            pending, size = [], 0
        pending.append(block)
        size += len(block["text"])
    if pending:
        chunks.append(pending)
    return chunks


def chunk_context(
    context: dict[str, Any], all_blocks: list[dict[str, Any]], chunk: list[dict[str, Any]],
) -> dict[str, Any]:
    def parent(block: dict[str, Any]) -> str:
        return block.get("parent_block_id", block["block_id"])
    positions = {block["block_id"]: index for index, block in enumerate(all_blocks)}
    first, last = positions[parent(chunk[0])], positions[parent(chunk[-1])]
    neighbors = all_blocks[max(0, first - 2):first] + all_blocks[last + 1:last + 3]
    return {**context, "neighboring_blocks": [{
        "block_id": block["block_id"], "section": block.get("section"),
        "text": block["text"][:1500],
    } for block in neighbors]}


def canonical_units(
    blocks: list[dict[str, Any]], atoms: list[BlockAtoms], relations: list[DiscourseRelation],
    intents: list[BlockIntents], roles: list[BlockRole],
) -> list[dict[str, Any]]:
    by_block = {record.block_id: record for record in atoms}
    by_intent = {intent.atom_id: intent for intent in intents}
    by_role = {role.block_id: role for role in roles}
    units = []
    for block in blocks:
        propositions = by_block[block["block_id"]].atoms
        ids = {atom.atom_id for atom in propositions}
        units.append({
            "block_id": block["block_id"], "page_number": block.get("page_number"),
            "section": block.get("section"), "raw_text": block["text"],
            "source_location": block.get("location", {}),
            "parent_block_id": block.get("parent_block_id"),
            "source_char_start": block.get("source_char_start"),
            "source_char_end": block.get("source_char_end"),
            "layer1": {
                "propositions": [{
                    **atom.model_dump(),
                    "source_span": located_span(block["text"], atom.quote),
                    "source_span_basis": "whitespace_and_soft_hyphen_normalized_block_text",
                } for atom in propositions],
                "triplets": [triplet.model_dump() for atom in propositions for triplet in atom.triplets],
            },
            "layer2": {"relations": [
                relation.model_dump() for relation in relations
                if relation.source_id in ids or relation.target_id in ids
            ]},
            "layer3": {"intents": [by_intent[atom.atom_id].model_dump() for atom in propositions]},
            "layer4": by_role[block["block_id"]].model_dump(),
        })
    return units
