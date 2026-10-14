"""Preserve literal parsed table fields as source requirements, without guessing cells."""

from __future__ import annotations

import copy
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_verified_reference import VerifiedReferenceBuilder

TABLE_REQUIREMENT_VERSION = "source-table-literal-field-requirements-v1"


class TableRows(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text = text
        self.line_starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self.line_starts.append(index + 1)
        self.rows: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.cell: list[str] | None = None

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            if self.current is not None:
                raise SourceContractError("Nested/unclosed table rows need parser review")
            self.current = {"start": self.absolute_offset(), "cells": [], "header": False}
        elif tag in {"td", "th"} and self.current is not None:
            self.cell = []
            self.current["header"] |= tag == "th"

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current is not None and self.cell is not None:
            self.current["cells"].append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.current is not None:
            self.current["end"] = self.absolute_offset() + len("</tr>")
            self.rows.append(self.current)
            self.current = None


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
