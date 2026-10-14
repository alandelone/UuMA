"""Preserve literal parsed table fields as source requirements, without guessing cells."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_table_reference import TableRows as OriginalTableRows
from rstv4.skeleton_verified_reference import VerifiedReferenceBuilder

TABLE_REQUIREMENT_VERSION = "source-table-literal-empty-orphan-structure-v2"


class TableRows(OriginalTableRows):
    """Record only an empty orphan <tr> directly preceding a table close."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.structural_recoveries: list[dict[str, Any]] = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.current is not None:
            start, end = self.current["start"], self.absolute_offset()
            raw = self.text[start:end]
            if (self.cell is None and not self.current["cells"]
                    and self.current["header"] is False
                    and re.fullmatch(r"<tr>\s*", raw, flags=re.IGNORECASE)):
                self.structural_recoveries.append({
                    "disposition": "EMPTY_ORPHAN_TABLE_STRUCTURE",
                    "source_char_start": start, "source_char_end": end,
                    "raw_text": raw, "raw_text_digest": digest(raw),
                    "table_close_offset": end,
                    "scientific_data_discarded": False,
                })
                self.current = None
        super().handle_endtag(tag)


def table_requirements(
    block: dict[str, Any], reference: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Add exact source-cell requirements to claims anchored to those actual rows.

    This does not reconstruct merged columns, supply units absent from the parser, or
    change scientific statements. Ambiguous literal values remain visible. A numeric
    data row without any located reference claim is a source coverage failure.
    """
    result = copy.deepcopy(reference)
    if "<table" not in block["text"].lower():
        return result, []
    parser = TableRows(block["text"])
    parser.feed(block["text"])
    parser.close()
    if parser.current is not None:
        raise SourceContractError("Incomplete parsed HTML table needs source review")
    spans = {span["span_id"]: span for span in block["source_spans"]}
    ledger = []
    for row_index, row in enumerate(parser.rows, 1):
        anchors = {span_id for span_id, span in spans.items()
                   if span["start"] < row["end"] and row["start"] < span["end"]}
        claims = [claim for claim in result["claims"] if anchors.intersection(claim["source_span_ids"])]
        if not claims and not row["header"] and row["cells"] and row["cells"][0].strip().isdigit():
            raise SourceContractError(f"Numeric table data row {row_index} has no located reference claim")
        for cell_index, value in enumerate(row["cells"], 1):
            if not value:
                continue
            requirement = (
                f"Literal parsed table row {row_index}, cell {cell_index}: {value}. "
                "Preserve the stated field and its row association; do not infer an unstated unit "
                "or move ambiguous content to a different row."
            )
            for claim in claims:
                if requirement not in claim["qualifications"]:
                    claim["qualifications"].append(requirement)
            ledger.append({
                "row": row_index, "cell": cell_index, "raw_value": value,
                "source_span_ids": sorted(anchors),
                "reference_ids": [claim["reference_id"] for claim in claims],
                "disposition": "REFERENCE_REQUIREMENT" if claims else "UNCLAIMED_TABLE_STRUCTURE",
                "header_tag": row["header"],
            })
    ledger.extend(parser.structural_recoveries)
    return result, ledger


class TableAtomicReference:
    def __init__(self, original: Any, output: Path) -> None:
        self.original, self.output = original, output

    def block(self, context: str, block: dict[str, Any]) -> dict[str, Any]:
        original = self.original.block(context, block)
        updated, ledger = table_requirements(block, original)
        if ledger:
            key = digest({"version": TABLE_REQUIREMENT_VERSION, "context": context, "block": block})
            path = self.output / f"{key}.json"
            record = {"version": TABLE_REQUIREMENT_VERSION, "original_reference_digest": digest(original),
                      "reference": updated, "ledger": ledger, "source_block_digest": digest(block),
                      "scientific_statements_changed": False, "candidate_access": False}
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != record:
                raise SourceContractError("Literal table requirement lineage changed")
            if not path.exists():
                write_json(path, record)
        return updated


class TableVerifiedReferenceBuilder(VerifiedReferenceBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.drafts.atomic = TableAtomicReference(self.drafts.atomic, output / "table-field-ledgers")
