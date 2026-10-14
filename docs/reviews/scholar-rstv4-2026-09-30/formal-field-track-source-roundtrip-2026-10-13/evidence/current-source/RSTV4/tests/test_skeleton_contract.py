from __future__ import annotations

from itertools import pairwise

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import (
    Atom,
    BlockAtoms,
    BlockIntents,
    BlockRole,
    DiscourseRelation,
    SourceContractError,
    Triplet,
    canonical_atoms,
    canonical_units,
    chunk_context,
    chunk_document,
    located_span,
    resolve_source_quote,
    spans_for_existing_quote,
    validate_layers,
    with_source_spans,
)


def atom(quote: str = "Output may increase under clear skies.") -> Atom:
    return Atom(
        atom_id="temporary", statement=quote, quote=quote, source_span_ids=[],
        epistemic_status="AUTHOR_HYPOTHESIS",
        qualifications=["may", "under clear skies"],
        triplets=[Triplet(subject="Output", predicate="may increase under", object="clear skies")],
        objects=[],
    )


def test_source_ids_are_required_in_the_schema_given_to_the_model() -> None:
    assert "source_span_ids" in Atom.model_json_schema()["required"]
    value = atom().model_dump()
    del value["source_span_ids"]
    with pytest.raises(ValidationError, match="source_span_ids"):
        Atom.model_validate(value)


def test_chunking_covers_long_blocks_without_gaps_or_duplicates() -> None:
    text = "some long research claim. " * 200
    blocks = [{"block_id": "a", "text": text}, {"block_id": "b", "text": "Short."}]
    chunks = chunk_document(blocks, max_chars=500, max_blocks=2)
    parts = [block for chunk in chunks for block in chunk if block.get("parent_block_id") == "a"]
    assert "".join(part["text"] for part in parts) == text
    assert parts[0]["source_char_start"] == 0
    assert parts[-1]["source_char_end"] == len(text)
    assert all(left["source_char_end"] == right["source_char_start"]
               for left, right in pairwise(parts))
    assert [block["block_id"] for chunk in chunks for block in chunk].count("b") == 1
    assert all(sum(len(block["text"]) for block in chunk) <= 500 for chunk in chunks)


def test_part_context_uses_parent_position_and_retains_outline() -> None:
    blocks = [{"block_id": str(index), "text": "x" * 800} for index in range(5)]
    chunks = chunk_document(blocks, max_chars=500)
    middle = next(chunk for chunk in chunks if chunk[0].get("parent_block_id") == "2")
    context = chunk_context({"document_outline": ["Methods"]}, blocks, middle)
    assert context["document_outline"] == ["Methods"]
    assert {block["block_id"] for block in context["neighboring_blocks"]} == {"0", "1", "3", "4"}


def test_unlocated_quote_and_missing_block_prevent_publication() -> None:
    blocks = [{"block_id": "b", "text": "Output may increase under clear skies."}]
    with pytest.raises(SourceContractError, match="Unlocated quote"):
        canonical_atoms([BlockAtoms(block_id="b", atoms=[atom("Output always increases.")])], blocks)
    with pytest.raises(SourceContractError, match="every supplied block"):
        canonical_atoms([], blocks)


def test_canonical_units_preserve_qualifications_and_flat_publishable_triplets() -> None:
    blocks = [{"block_id": "b", "text": "Output may increase under clear skies.", "page_number": 2,
               "section": "3. Results", "location": {"source_page": 2}}]
    atoms = canonical_atoms([BlockAtoms(block_id="b", atoms=[atom()])], blocks)
    intents = [BlockIntents(atom_id="b:a1", primary="Boundary_Condition", secondary=[], rationale="may")]
    roles = [BlockRole(block_id="b", role="Result_Performance", confidence=0.9, rationale="section")]
    validate_layers(atoms, [], intents, roles, blocks)
    unit = canonical_units(blocks, atoms, [], intents, roles)[0]
    assert unit["layer1"]["triplets"] == [atoms[0].atoms[0].triplets[0].model_dump()]
    assert unit["layer1"]["propositions"][0]["qualifications"] == ["may", "under clear skies"]
    assert unit["layer1"]["propositions"][0]["source_span"] == (0, len(blocks[0]["text"]))
    assert unit["source_location"] == {"source_page": 2}


def test_unknown_relation_endpoint_and_missing_intent_fail_closed() -> None:
    blocks = [{"block_id": "b", "text": "Output may increase under clear skies."}]
    atoms = canonical_atoms([BlockAtoms(block_id="b", atoms=[atom()])], blocks)
    roles = [BlockRole(block_id="b", role="Core_Methodology", confidence=0.8, rationale="scope")]
    relations = [DiscourseRelation(source_id="invented", target_id="b:a1", relation="Cause", rationale="bad")]
    with pytest.raises(SourceContractError, match="unknown proposition"):
        validate_layers(atoms, relations, [], roles, blocks)
    with pytest.raises(SourceContractError, match="one primary intent"):
        validate_layers(atoms, [], [], roles, blocks)


def test_span_basis_handles_pdf_whitespace_and_discretionary_hyphens() -> None:
    assert located_span("renew\u00ad\nable    energy", "renewable energy") == (0, 16)


def test_supplying_the_same_block_twice_is_rejected() -> None:
    blocks = [{"block_id": "b", "text": "Short claim."}]
    records = [BlockAtoms(block_id="b", atoms=[]), BlockAtoms(block_id="b", atoms=[])]
    with pytest.raises(SourceContractError, match="every supplied block"):
        canonical_atoms(records, blocks)


def test_source_span_ids_resolve_to_exact_math_text_without_model_transcription() -> None:
    text = r"PV uses $3\mathrm{kW}$ ) as assumed. The load may vary."
    blocks = with_source_spans([{"block_id": "b", "text": text}])
    value = atom("PV uses $3kW$) as assumed.")
    value.source_span_ids = [blocks[0]["source_spans"][0]["span_id"]]
    records = canonical_atoms([BlockAtoms(block_id="b", atoms=[value])], blocks)
    assert records[0].atoms[0].quote == text[:blocks[0]["source_spans"][0]["end"]]
    assert located_span(text, records[0].atoms[0].quote) is not None


def test_unknown_or_noncontiguous_source_ids_are_not_accepted_as_quotes() -> None:
    block = with_source_spans([{"block_id": "b", "text": "First. Second. Third."}])[0]
    with pytest.raises(SourceContractError, match="existing source span"):
        resolve_source_quote(block, ["invented"])
    ids = [span["span_id"] for span in block["source_spans"]]
    with pytest.raises(SourceContractError, match="ordered and contiguous"):
        resolve_source_quote(block, [ids[0], ids[2]])
    with pytest.raises(SourceContractError, match="ordered and contiguous"):
        resolve_source_quote(block, [ids[1], ids[0]])


def test_repair_failure_locates_the_atom_and_available_source_ids() -> None:
    block = with_source_spans([{"block_id": "b", "text": "Output may increase."}])[0]
    value = atom()
    value.source_span_ids = ["invented"]
    with pytest.raises(SourceContractError, match="b:a1.*available IDs.*b:s1"):
        canonical_atoms([BlockAtoms(block_id="b", atoms=[value])], [block])


def test_legacy_quote_migration_still_rejects_paraphrased_source() -> None:
    block = with_source_spans([{"block_id": "b", "text": "Output may increase. Only under clear skies."}])[0]
    ids = spans_for_existing_quote(block, "Output may increase.")
    assert "Output may increase." in resolve_source_quote(block, ids)
    with pytest.raises(SourceContractError, match="Unlocated legacy quote"):
        spans_for_existing_quote(block, "Output always increases.")
